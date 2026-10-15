import pytest

from app.domain.candidate import Candidate
from app.domain.card_text import build_card_text
from app.domain.choice import NOT_STATED
from app.domain.decision import ChoiceAnswer, ChoiceQuestion, Decision, DecisionRequest
from app.domain.inference import Usage
from app.domain.lexicon import Lexicon
from app.domain.profile import AttributeProfile, Kind
from app.domain.scoring import Pick
from app.usecase.baseline_ports import CardRecord
from app.usecase.decision_stage import ChooseValues, StageConfig, merge
from app.usecase.extraction import CardExtraction

PHONE = 761
TEXT = build_card_text("Смартфон Samsung Galaxy A55 черный", "Серия Galaxy A. Цвет графит", ())
CARD = CardRecord(1, PHONE, "ИП", "Смартфон Samsung Galaxy A55 черный", "", (), "test")
PROFILES = {
    "Бренд": AttributeProfile("Бренд", Kind.CATEGORICAL, "", ("бренд",)),
    "Серия": AttributeProfile("Серия", Kind.CATEGORICAL, "", ("серия",)),
    "Цвет": AttributeProfile("Цвет", Kind.CATEGORICAL, "", ("цвет",)),
}


def cand(attribute: str, value: str) -> Candidate:
    start = TEXT.text.index(value)
    return Candidate(attribute, value.lower(), value, value, start, start + len(value),
                     "dictionary", TEXT.zone(start), 0.0, 0.0, 0)


BRAND = cand("Бренд", "Samsung")
SERIES = [cand("Серия", "Galaxy A55"), cand("Серия", "Galaxy A")]
BASE = CardExtraction(TEXT, PROFILES, (BRAND, *SERIES), {"Бренд": Pick(BRAND, 0.5, ("d",))},
                      {"Серия": Pick(SERIES[0], 0.2, ("d",))})


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeModel:
    def __init__(self, pick_last: bool = False, not_stated: bool = False) -> None:
        self.requests: list[DecisionRequest] = []
        self.pick_last = pick_last
        self.not_stated = not_stated

    async def decide(self, request: DecisionRequest) -> Decision:
        self.requests.append(request)
        answers = {}
        for key, question in request.questions.items():
            assert isinstance(question, ChoiceQuestion)
            names = list(question.options)
            choice = NOT_STATED if self.not_stated else names[-2 if self.pick_last else 0]
            answers[key] = ChoiceAnswer(choice, 0.9, {n: (0.9 if n == choice else 0.0)
                                                      for n in names})
        return Decision(answers, Usage("jev", 10, 100, 5, 0.00001))

    async def aclose(self) -> None:
        return None


class MemoryCache:
    def __init__(self) -> None:
        self.items: dict[str, Decision] = {}

    def get(self, fingerprint: str) -> Decision | None:
        return self.items.get(fingerprint)

    def put(self, fingerprint: str, decision: Decision) -> None:
        self.items[fingerprint] = decision


def stage(model: FakeModel, cache: MemoryCache | None = None) -> ChooseValues:
    return ChooseValues(model, Lexicon(PROFILES, [], {}), StageConfig(model_name="jev"), cache)


@pytest.mark.anyio
async def test_routes_only_uncertain_and_weak_slots() -> None:
    model = FakeModel(pick_last=True)

    result = await stage(model).choose(CARD, BASE)

    [request] = model.requests
    assert [s.attribute for s in result.slots] == ["Серия"]
    assert len(request.questions) == 1
    assert result.chosen["Серия"].candidate is not None
    assert result.chosen["Серия"].candidate.value == "Galaxy A"
    assert result.usage is not None and result.usage.cost_usd == 0.00001


@pytest.mark.anyio
async def test_merge_overrides_and_drops_by_thresholds() -> None:
    result = await stage(FakeModel(pick_last=True)).choose(CARD, BASE)

    kept = merge(BASE, result, override=0.95, min_confidence=0.35)
    replaced = merge(BASE, result, override=0.5, min_confidence=0.35)

    assert kept.review["Серия"].candidate.value == "Galaxy A55"
    assert replaced.picks["Серия"].candidate.value == "Galaxy A"
    assert "decision" in replaced.picks["Серия"].sources

    silent = await stage(FakeModel(not_stated=True)).choose(CARD, BASE)
    assert silent.chosen == {}
    assert "Серия" not in merge(BASE, silent, 0.5, 0.35, drop=0.8).review
    assert "Серия" in merge(BASE, silent, 0.5, 0.35, drop=None).review


@pytest.mark.anyio
async def test_cache_hit_skips_the_model() -> None:
    cache = MemoryCache()
    first = FakeModel()
    await stage(first, cache).choose(CARD, BASE)
    second = FakeModel()

    result = await stage(second, cache).choose(CARD, BASE)

    assert result.cached
    assert second.requests == []
