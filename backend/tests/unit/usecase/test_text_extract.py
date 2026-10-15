from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from app.domain.inference import Completion, StructuredRequest, Usage
from app.domain.lexicon import LexiconEntry
from app.domain.profile import AttributeProfile, Kind
from app.domain.text_reading import EmptyText
from app.repository.memory.review import MemoryAliasRepository, MemoryReviewRepository
from app.usecase.baseline_ports import RequiredRecord
from app.usecase.extract_card import BaselineChooser, ExtractCard
from app.usecase.stand_ports import StandCategory, StandPack
from app.usecase.text_extract import ExtractText
from app.usecase.text_ports import CatalogEntry, CategoryModel, TextIndex

PHONE = 761
IRON = 469
PAGE = (
    "<html><nav>Каталог</nav><h1>Смартфон Samsung Galaxy A55</h1>"
    "<script>var x = 'синий';</script>"
    "<p>Корпус черного цвета, серия Galaxy A.</p><footer>© Магазин</footer></html>"
)


class Identity:
    def fit(self, scores: Sequence[float], labels: Sequence[bool]) -> None:
        return None

    def transform(self, scores: Sequence[float]) -> Sequence[float]:
        return list(scores)


class FixedSearch:
    kind = "fixed"

    def __init__(self, hits: list[tuple[int, float]]) -> None:
        self._hits = hits
        self.queries: list[str] = []

    async def search(self, texts: Sequence[str], k: int) -> list[list[tuple[int, float]]]:
        self.queries.extend(texts)
        return [self._hits[:k] for _ in texts]


class TitleModel:
    def __init__(self, title: str) -> None:
        self._title = title

    async def complete(self, request: StructuredRequest) -> Completion:
        return Completion({"title": self._title}, Usage(model="fake"))


class Clock:
    def now(self) -> datetime:
        return datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


class Ids:
    def __init__(self) -> None:
        self._next = 0

    def new(self) -> str:
        self._next += 1
        return f"r{self._next}"


def stand_pack() -> StandPack:
    profiles = {
        "Бренд": AttributeProfile("Бренд", Kind.CATEGORICAL, "", ("бренд",)),
        "Цвет": AttributeProfile("Цвет", Kind.CATEGORICAL, "", ("цвет",)),
        "Серия": AttributeProfile("Серия", Kind.CATEGORICAL, "", ("сери",)),
    }
    return StandPack(
        built_at="2026-10-15T12:00:00+00:00", threshold=0.35, profiles=profiles,
        entries=[LexiconEntry("Бренд", ("samsung",), "samsung", "Samsung"),
                 LexiconEntry("Цвет", ("черный",), "черный", "черный")],
        priors={(PHONE, "Бренд"): {"samsung": 1.0}, (PHONE, "Цвет"): {"черный": 1.0}},
        required=[RequiredRecord(PHONE, "Бренд", 10.0), RequiredRecord(PHONE, "Цвет", 2.0),
                  RequiredRecord(PHONE, "Серия", 1.0)],
        categories=[StandCategory(category_id=PHONE, name="Смартфоны", path="Смартфоны")],
        examples=[],
    )


def text_index() -> TextIndex:
    return TextIndex(
        entries=[
            CatalogEntry(1, PHONE, "смартфон samsung galaxy a35", {"Серия": "Galaxy A"}),
            CatalogEntry(2, PHONE, "смартфон samsung galaxy a15", {"Серия": "Galaxy A",
                                                                  "Цвет": "синий"}),
            CatalogEntry(3, IRON, "утюг philips gc1740", {}),
        ],
        names={PHONE: "Смартфоны", IRON: "Утюги"},
        models={"fixed": CategoryModel(Identity(), 0.6)},
        embedding_model="fake", dimensions=2,
    )


def usecase(hits: list[tuple[int, float]], title: str | None = None) -> ExtractText:
    cards = ExtractCard(stand_pack(), MemoryAliasRepository(), MemoryReviewRepository(),
                        BaselineChooser(), Clock(), Ids())
    language = TitleModel(title) if title is not None else None
    return ExtractText(text_index(), FixedSearch(hits), cards, language)


PHONE_HITS = [(0, 0.9), (1, 0.88), (2, 0.5)]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_page_gets_category_title_and_values_quoted_in_the_source() -> None:
    result = await usecase(PHONE_HITS, "Смартфон Samsung Galaxy A55").execute(PAGE)

    assert result.category_id == PHONE
    assert result.title == "Смартфон Samsung Galaxy A55"
    assert result.title_source == "llm"
    values = {v.attribute: v for v in result.values}
    assert values["Бренд"].value == "Samsung"
    assert values["Цвет"].value == "черный"
    assert values["Серия"].value == "Galaxy A"
    assert values["Серия"].source == "neighbor"
    for value in values.values():
        assert PAGE[value.start:value.end].casefold() == value.evidence.casefold()


@pytest.mark.anyio
async def test_values_without_a_fragment_in_the_text_are_not_accepted() -> None:
    result = await usecase(PHONE_HITS, "Смартфон Samsung Galaxy S99").execute(
        "Смартфон Samsung Galaxy A55. Отличный экран.")

    assert result.title == "Смартфон Samsung Galaxy A55"
    assert result.title_source == "rule"
    assert {v.attribute for v in result.values} == {"Бренд"}
    assert {"Цвет", "Серия"} <= set(result.missing)


@pytest.mark.anyio
async def test_category_below_threshold_is_unknown() -> None:
    hits = [(0, 0.8), (2, 0.8)]

    result = await usecase(hits).execute("Samsung черный, Philips")

    assert result.category_id is None
    assert {c for c, _ in result.candidates} == {PHONE, IRON}
    assert "Серия" not in {v.attribute for v in result.values} | set(result.missing)


@pytest.mark.anyio
async def test_text_without_product_content_is_rejected() -> None:
    with pytest.raises(EmptyText):
        await usecase(PHONE_HITS).execute("<script>alert(1)</script><nav>Каталог</nav>")
