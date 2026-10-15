from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime

import pytest

from app.domain.card_text import SellerParam
from app.domain.fusion import BASELINE, KNOWN, NEW, RANKER, FusionRules, Rule
from app.domain.review import (
    REVIEW_CONFIDENCE,
    REVIEW_SOURCE,
    ReviewAction,
    ReviewStatus,
    StandUnavailable,
    UnknownCategory,
)
from app.repository.memory.review import MemoryAliasRepository, MemoryReviewRepository
from app.usecase.baseline_ports import CardRecord, GoldRecord, RequiredRecord
from app.usecase.extract_card import BaselineChooser, ExtractCard
from app.usecase.interface import LogValue
from app.usecase.lexicon_builder import TrainValue
from app.usecase.ranker_ports import FeatureTable
from app.usecase.review_queue import ReviewQueue
from app.usecase.stand_catalog import StandCatalog
from app.usecase.stand_chooser import FusedChooser, FusionPolicy
from app.usecase.stand_pack import BuildStandPack, StandPackConfig
from app.usecase.stand_ports import CardInput, StandPack

PHONE = 761
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
DESCRIPTION = "Смартфон с ярким экраном и большой батареей 5000 мАч. " * 6


class StandSource:
    def train_values(self, attributes: frozenset[str]) -> Iterator[TrainValue]:
        for _ in range(3):
            yield TrainValue(PHONE, "Бренд", "Samsung", None)
            yield TrainValue(PHONE, "Цвет", "черный", None)
            yield TrainValue(PHONE, "Емкость аккумулятора", "5000", "мАч")

    def required(self) -> Sequence[RequiredRecord]:
        return [RequiredRecord(PHONE, "Бренд", 10.0), RequiredRecord(PHONE, "Цвет", 2.0)]

    def category_stats(self) -> Mapping[int, tuple[int, int]]:
        return {PHONE: (100, 2)}

    def seller_cards(self) -> Mapping[str, int]:
        return {}

    def gold(self, splits: frozenset[str]) -> Mapping[int, Sequence[GoldRecord]]:
        return {}

    def cards(self, splits: frozenset[str] | None, batch: int) -> Iterator[list[CardRecord]]:
        yield [CardRecord(7, PHONE, "М.Видео", "Смартфон Samsung черный", DESCRIPTION,
                          (SellerParam("Цвет", "черный"),), "test")]


class Names:
    def names(self) -> Mapping[int, tuple[str, str]]:
        return {PHONE: ("Смартфоны", "Смартфоны и связь / Смартфоны")}


class PackSink:
    def __init__(self) -> None:
        self.pack: StandPack | None = None

    def save(self, pack: StandPack) -> int:
        self.pack = pack
        return 1


class SilentLogger:
    def info(self, event: str, **fields: LogValue) -> None:
        pass

    def warning(self, event: str, **fields: LogValue) -> None:
        pass

    def error(self, event: str, *, exc: BaseException | None = None, **fields: LogValue) -> None:
        pass


class FixedClock:
    def now(self) -> datetime:
        return NOW


class CountingIds:
    def __init__(self) -> None:
        self._next = 0

    def new(self) -> str:
        self._next += 1
        return f"id-{self._next}"


def build_pack(threshold: float) -> StandPack:
    sink = PackSink()
    usecase = BuildStandPack(StandSource(), Names(), sink, SilentLogger())
    usecase.run(StandPackConfig(threshold=threshold, focus_examples=1), NOW)
    assert sink.pack is not None
    return sink.pack


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def card(category: int | None = PHONE) -> CardInput:
    return CardInput(title="Смартфон Samsung Galaxy", description="Корпус черного цвета",
                     seller_params=(SellerParam("Цвет", "черный"),), category_id=category)


def services(pack: StandPack | None) -> tuple[ExtractCard, ReviewQueue]:
    reviews, aliases, clock = MemoryReviewRepository(), MemoryAliasRepository(), FixedClock()
    extract = ExtractCard(pack, aliases, reviews, BaselineChooser(), clock, CountingIds())
    return extract, ReviewQueue(reviews, aliases, clock)


def test_pack_keeps_categories_lexicon_and_examples_with_review_cases() -> None:
    pack = build_pack(threshold=0.6)

    assert [c.category_id for c in pack.categories] == [PHONE]
    assert {"Бренд", "Цвет"} <= set(pack.profiles)
    assert any(e.key == "samsung" for e in pack.entries)
    assert [e.sku_id for e in pack.examples] == [7]


@pytest.mark.anyio
async def test_values_carry_quote_spans_from_the_card() -> None:
    extract, _ = services(build_pack(threshold=0.35))

    result = await extract.execute(card())

    brand = next(v for v in result.values if v.attribute == "Бренд")
    assert brand.value == "Samsung"
    assert result.text[brand.start:brand.end] == brand.evidence


@pytest.mark.anyio
async def test_correction_turns_review_value_into_confident_one() -> None:
    extract, queue = services(build_pack(threshold=0.99))

    first = await extract.execute(card())
    pending = next(v for v in first.values if v.attribute == "Бренд")
    assert pending.in_review and pending.review_id is not None
    again = await extract.execute(card())
    assert [i.id for i in await queue.list(ReviewStatus.PENDING)].count(pending.review_id) == 1

    resolved = await queue.resolve(pending.review_id, ReviewAction.CORRECT, "Samsung Electronics")
    second = await extract.execute(card())

    assert again.values == first.values
    assert resolved.status is ReviewStatus.CORRECTED
    brand = next(v for v in second.values if v.attribute == "Бренд")
    assert (brand.value, brand.source, brand.in_review) == ("Samsung Electronics",
                                                            REVIEW_SOURCE, False)
    assert brand.confidence == REVIEW_CONFIDENCE


@pytest.mark.anyio
async def test_missing_pack_and_unknown_category_are_honest_errors() -> None:
    no_pack, _ = services(None)
    extract, _ = services(build_pack(threshold=0.35))

    with pytest.raises(StandUnavailable):
        await no_pack.execute(card())
    with pytest.raises(UnknownCategory):
        await extract.execute(card(category=1))
    with pytest.raises(StandUnavailable):
        StandCatalog(None).info()


def test_catalog_lists_required_attributes_per_category() -> None:
    info = StandCatalog(build_pack(threshold=0.35)).info()

    phone = info.categories[0]
    assert phone.name == "Смартфоны"
    assert {"Бренд", "Цвет", "Емкость аккумулятора"} <= set(phone.attributes)


class ConstantModel:
    def fit(self, train: FeatureTable, names: Sequence[str], categorical: Sequence[str]) -> None:
        pass

    def predict(self, table: FeatureTable) -> Sequence[float]:
        return [0.9] * table.rows

    def importances(self) -> Mapping[str, float]:
        return {}


class Identity:
    def fit(self, scores: Sequence[float], labels: Sequence[bool]) -> None:
        pass

    def transform(self, scores: Sequence[float]) -> Sequence[float]:
        return list(scores)


def fused(threshold: float) -> ExtractCard:
    rules = FusionRules({KNOWN: Rule(RANKER, False), NEW: Rule(RANKER, False)},
                        {("Цвет", KNOWN): Rule(BASELINE, False)})
    chooser = FusedChooser(ConstantModel(), Identity(), 0.3,
                           FusionPolicy(rules, lambda _, c: c, threshold))
    return ExtractCard(build_pack(threshold=0.35), MemoryAliasRepository(),
                       MemoryReviewRepository(), chooser, FixedClock(), CountingIds())


@pytest.mark.anyio
async def test_fused_chooser_marks_the_stage_that_supplied_each_value() -> None:
    result = await fused(0.5).execute(card())

    brand = next(v for v in result.values if v.attribute == "Бренд")
    assert (brand.value, brand.confidence, brand.sources[-1]) == ("Samsung", 0.9, RANKER)
    assert result.text[brand.start:brand.end] == brand.evidence
    color = next(v for v in result.values if v.attribute == "Цвет")
    assert color.sources[-1] == BASELINE


@pytest.mark.anyio
async def test_values_below_the_fused_threshold_go_to_review() -> None:
    result = await fused(0.95).execute(card())

    brand = next(v for v in result.values if v.attribute == "Бренд")
    assert brand.in_review and brand.review_id is not None
