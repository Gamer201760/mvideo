from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.candidate import Candidate
from app.domain.choice import (
    NOT_STATED,
    ChoiceSlot,
    Chosen,
    build_request,
    candidate_slot,
    dictionary_slot,
    mixed_slot,
    request_fingerprint,
    resolve,
)
from app.domain.choice_text import compact_state
from app.domain.decision import ChoiceAnswer, Decision, DecisionRequest
from app.domain.inference import Usage
from app.domain.lexicon import Lexicon
from app.domain.profile import Kind
from app.domain.scoring import Pick
from app.usecase.baseline_ports import CardRecord
from app.usecase.decision_ports import CategoryTree, DecisionCache
from app.usecase.extraction import CardExtraction
from app.usecase.interface import DecisionModel

DECISION_SOURCE = "decision"
WEAK_ATTRIBUTES = frozenset({
    "Процессор", "Поддержка стандартов", "Серия", "Производитель видеопроцессора",
    "Емкость аккумулятора", "Диагональ",
})
WEAK_PAIRS = frozenset({(987, "Цвет")})
PROTECTED = frozenset({"Бренд", "Модель"})
DICTIONARY_KINDS = frozenset({Kind.CATEGORICAL, Kind.BOOLEAN})


@dataclass(frozen=True, slots=True)
class StageConfig:
    model_name: str
    top_k: int = 8
    dictionary_k: int = 20
    min_confidence: float = 0.35
    route_all: bool = False
    route_below: float = 0.6
    dictionary: bool = False
    mix_k: int = 0
    weak: frozenset[str] = WEAK_ATTRIBUTES
    weak_pairs: frozenset[tuple[int, str]] = WEAK_PAIRS


@dataclass(frozen=True, slots=True)
class StageResult:
    slots: tuple[ChoiceSlot, ...]
    chosen: Mapping[str, Chosen]
    not_stated: Mapping[str, float]
    usage: Usage | None
    cached: bool
    eligible: int

    @property
    def questions(self) -> int:
        return len(self.slots)

    @property
    def dictionary_questions(self) -> int:
        return sum(1 for s in self.slots if s.from_dictionary)


def baseline_picks(base: CardExtraction) -> dict[str, Pick]:
    return {**base.review, **base.picks}


def merge(base: CardExtraction, result: StageResult | None, override: float,
          min_confidence: float, drop: float | None = None) -> CardExtraction:
    picks = baseline_picks(base)
    if result is not None:
        if drop is not None:
            for name, probability in result.not_stated.items():
                if probability >= drop:
                    picks.pop(name, None)
        for name, chosen in result.chosen.items():
            if chosen.candidate is not None and chosen.probability >= override:
                picks[name] = Pick(chosen.candidate, chosen.probability,
                                   tuple(sorted({chosen.candidate.source, DECISION_SOURCE})))
    accepted = {n: p for n, p in picks.items() if p.confidence >= min_confidence}
    review = {n: p for n, p in picks.items() if p.confidence < min_confidence}
    return CardExtraction(base.text, base.profiles, base.candidates, accepted, review)


class ChooseValues:
    def __init__(
        self, model: DecisionModel, lexicon: Lexicon, config: StageConfig,
        cache: DecisionCache | None = None, categories: CategoryTree | None = None,
    ) -> None:
        self._model = model
        self._lexicon = lexicon
        self._config = config
        self._cache = cache
        self._categories = categories
        self._names = categories.names() if categories is not None else {}

    def routed(self, card: CardRecord, name: str, keys: int, pick: Pick | None) -> bool:
        c = self._config
        if keys == 0:
            return c.dictionary
        if c.route_all:
            return True
        if name in PROTECTED:
            return pick is None
        if name in c.weak or (card.category_id, name) in c.weak_pairs:
            return True
        return keys >= 2 and (pick is None or pick.confidence < c.route_below)

    def slots(self, card: CardRecord, base: CardExtraction) -> list[ChoiceSlot]:
        by_attribute: dict[str, list[Candidate]] = {}
        for candidate in base.candidates:
            by_attribute.setdefault(candidate.attribute, []).append(candidate)
        picks = baseline_picks(base)
        slots: list[ChoiceSlot] = []
        for name, profile in sorted(base.profiles.items()):
            found = by_attribute.get(name, [])
            keys = len({c.key for c in found})
            if not self.routed(card, name, keys, picks.get(name)):
                continue
            key = f"q{len(slots)}"
            mixable = self._config.mix_k > 0 and profile.kind in DICTIONARY_KINDS
            if found and mixable:
                values = self.fallback_values(card.category_id, name)
                display = {k: self._lexicon.display(name, k) or k for k in values}
                slot = mixed_slot(name, key, found, profile, self._config.top_k, values, display,
                                  self._config.mix_k)
            elif found:
                slot = candidate_slot(name, key, found, profile, self._config.top_k)
            elif profile.kind not in DICTIONARY_KINDS:
                continue
            else:
                values = self.fallback_values(card.category_id, name)
                display = {k: self._lexicon.display(name, k) or k for k in values}
                slot = dictionary_slot(name, key, values, display, self._config.dictionary_k,
                                       profile.unit)
            if slot is not None:
                slots.append(slot)
        return slots

    def fallback_values(self, category: int | None, attribute: str) -> Mapping[str, float]:
        own = self._lexicon.category_values(category, attribute)
        if own or category is None or self._categories is None:
            return own
        level = category
        for _ in range(2):
            parent = self._categories.parent(level)
            if parent is None:
                return {}
            pooled: dict[str, float] = {}
            for sibling in self._categories.children(parent):
                for k, v in self._lexicon.category_values(sibling, attribute).items():
                    pooled[k] = pooled.get(k, 0.0) + v
            if pooled:
                return pooled
            level = parent
        return {}

    async def decide(self, fingerprint: str, request: DecisionRequest) -> tuple[Decision, bool]:
        if self._cache is not None:
            hit = self._cache.get(fingerprint)
            if hit is not None:
                return hit, True
        decision = await self._model.decide(request)
        if self._cache is not None:
            self._cache.put(fingerprint, decision)
        return decision, False

    async def choose(self, card: CardRecord, base: CardExtraction) -> StageResult:
        slots = self.slots(card, base)
        eligible = len(base.profiles)
        if not slots:
            return StageResult((), {}, {}, None, False, eligible)
        category = self._names.get(card.category_id) if card.category_id is not None else None
        state = compact_state(base.text, category, _spans(slots))
        request = build_request(state, slots)
        decision, cached = await self.decide(
            request_fingerprint(request, self._config.model_name), request)
        chosen: dict[str, Chosen] = {}
        not_stated: dict[str, float] = {}
        for slot in slots:
            answer = decision.answers.get(slot.question_key)
            if not isinstance(answer, ChoiceAnswer):
                continue
            if answer.choice == NOT_STATED:
                not_stated[slot.attribute] = answer.probabilities.get(NOT_STATED, answer.confidence)
                continue
            pick = resolve(base.text, slot, answer)
            if pick is not None:
                chosen[slot.attribute] = pick
        return StageResult(tuple(slots), chosen, not_stated, decision.usage, cached, eligible)


def _spans(slots: Sequence[ChoiceSlot]) -> list[tuple[int, int]]:
    return [(o.candidate.start, o.candidate.end) for s in slots for o in s.options
            if o.candidate is not None and o.candidate.start >= 0]
