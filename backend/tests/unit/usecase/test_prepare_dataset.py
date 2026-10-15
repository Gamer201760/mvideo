from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.catalog import Category, GoldValue, Offer, OfferCard, Param
from app.domain.requirement import CategoryUsage, RequiredAttribute
from app.domain.split import Split
from app.usecase.dataset import PrepareConfig, PrepareDataset
from app.usecase.dataset_ports import QueryStat, TextStats
from app.usecase.interface import LogValue

PHONES = 2
CASES = 3


def phone(sku: int, color: str, memory: str) -> Offer:
    return Offer(
        sku_id=sku,
        available=True,
        vendor="Samsung",
        model=f"S{sku}",
        name=f"Смартфон Samsung S{sku}",
        category_id=PHONES,
        params=(
            Param("Цвет", color),
            Param("Цвет_search", color),
            Param("Объем памяти_search", memory, "ГБ"),
            Param("Гарантия_search", "1 год"),
        ),
    )


class FakeCatalog:
    def items(self) -> Iterator[Category | Offer]:
        yield Category(1, None, "Телефоны")
        yield Category(PHONES, 1, "Смартфоны")
        yield Category(CASES, 1, "Чехлы")
        for sku in range(1, 41):
            yield phone(sku, "черный" if sku % 2 else "белый", "256" if sku % 3 else "128")
        yield Offer(900, True, None, None, "Чехол", CASES, (Param("Материал", "кожа"),))


class FakeDescriptions:
    def sku_ids(self) -> set[int]:
        return set(range(1, 31)) | {5000}


class FakeClicks:
    def sku_clicks(self) -> dict[int, int]:
        return {sku: 10 for sku in range(1, 21)} | {7000: 3}

    def category_queries(self, sku_category: Mapping[int, int]) -> Iterator[QueryStat]:
        yield QueryStat(PHONES, "samsung черный", 60)
        yield QueryStat(PHONES, "смартфон 256гб", 30)
        yield QueryStat(PHONES, "смартфон", 110)


@dataclass
class MemoryStore:
    cards: list[OfferCard] = field(default_factory=list)
    gold: list[GoldValue] = field(default_factory=list)
    splits: dict[int, Split] = field(default_factory=dict)
    required: list[RequiredAttribute] = field(default_factory=list)
    usage: list[CategoryUsage] = field(default_factory=list)
    stats: dict[str, object] = field(default_factory=dict)
    closed: bool = False

    def write_categories(self, categories: Sequence[Category], paths: Mapping[int, str]) -> None:
        assert paths[PHONES] == "Телефоны / Смартфоны"

    def add_offer(self, card: OfferCard, gold: Sequence[GoldValue]) -> None:
        self.cards.append(card)
        self.gold.extend(gold)

    def close_offers(self) -> None:
        self.closed = True

    def gold_values(self, attributes: frozenset[str]) -> Iterator[GoldValue]:
        return (g for g in self.gold if g.attribute in attributes)

    def write_clicks(self, sku_clicks: Mapping[int, int], sku_category: Mapping[int, int]) -> None:
        pass

    def write_category_usage(self, usages: Sequence[CategoryUsage]) -> None:
        self.usage = list(usages)

    def write_splits(self, splits: Mapping[int, Split]) -> None:
        self.splits = dict(splits)

    def write_required(self, required: Sequence[RequiredAttribute]) -> None:
        self.required = list(required)

    def attach_texts(self) -> TextStats:
        return TextStats(cards=42, cards_with_text=31, cards_in_catalog=41, cards_with_spec_block=3)

    def write_stats(self, stats: Mapping[str, object]) -> None:
        self.stats = dict(stats)


class SilentLogger:
    def info(self, event: str, **fields: LogValue) -> None:
        pass

    def warning(self, event: str, **fields: LogValue) -> None:
        pass

    def error(self, event: str, *, exc: BaseException | None = None, **fields: LogValue) -> None:
        pass


def run(config: PrepareConfig) -> MemoryStore:
    store = MemoryStore()
    PrepareDataset(FakeCatalog(), FakeDescriptions(), FakeClicks(), store, SilentLogger()).run(
        config
    )
    return store


def test_card_input_never_contains_gold_params() -> None:
    store = run(PrepareConfig(min_category_cards=10))

    assert store.closed
    assert len(store.cards) == 41
    assert all(not p.name.endswith("_search") for c in store.cards for p in c.seller_params)
    assert {g.attribute for g in store.gold} >= {"Цвет", "Объем памяти", "Бренд", "Модель"}


def test_required_attributes_ranked_and_weighted_by_query_mentions() -> None:
    store = run(PrepareConfig(min_category_cards=10, min_coverage=0.5))

    phones = {r.attribute: r for r in store.required if r.category_id == PHONES}
    assert [r.attribute for r in sorted(phones.values(), key=lambda r: r.rank)][:2] == [
        "Бренд",
        "Модель",
    ]
    assert "Гарантия" not in phones
    assert phones["Цвет"].query_share == 0.3
    assert phones["Объем памяти"].query_share == 0.15
    assert phones["Бренд"].query_share == 0.3
    assert phones["Цвет"].category_clicks == 200
    assert not [r for r in store.required if r.category_id == CASES]


def test_splits_cover_offers_and_stats_report_overlaps() -> None:
    store = run(PrepareConfig(min_category_cards=10))

    assert set(store.splits) == set(range(1, 41)) | {900}
    assert set(store.splits.values()) <= {Split.TRAIN, Split.VAL, Split.TEST}
    skus = store.stats["skus"]
    assert isinstance(skus, dict)
    assert skus["offers_and_desc"] == 30
    assert skus["offers_and_clicks"] == 20
    assert skus["all_three"] == 20
    assert skus["gold_skus"] == 40


def test_mid_sized_category_held_out_as_new() -> None:
    store = run(
        PrepareConfig(
            min_category_cards=10,
            new_category_min_cards=30,
            new_categories=1,
            protected_categories=(),
        )
    )

    assert {store.splits[s] for s in range(1, 41)} == {Split.NEW_CATEGORY}
    assert store.splits[900] != Split.NEW_CATEGORY
