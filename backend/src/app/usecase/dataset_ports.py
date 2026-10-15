from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.catalog import Category, GoldValue, Offer, OfferCard
from app.domain.requirement import CategoryUsage, RequiredAttribute
from app.domain.split import Split


@dataclass(frozen=True, slots=True)
class QueryStat:
    category_id: int
    query: str
    clicks: int


@dataclass(frozen=True, slots=True)
class TextStats:
    cards: int
    cards_with_text: int
    cards_in_catalog: int
    cards_with_spec_block: int


class CatalogSource(Protocol):
    def items(self) -> Iterator[Category | Offer]: ...


class DescriptionSource(Protocol):
    def sku_ids(self) -> set[int]: ...


class ClickSource(Protocol):
    def sku_clicks(self) -> dict[int, int]: ...

    def category_queries(self, sku_category: Mapping[int, int]) -> Iterator[QueryStat]: ...


class DatasetStore(Protocol):
    def write_categories(
        self, categories: Sequence[Category], paths: Mapping[int, str]
    ) -> None: ...

    def add_offer(self, card: OfferCard, gold: Sequence[GoldValue]) -> None: ...

    def close_offers(self) -> None: ...

    def gold_values(self, attributes: frozenset[str]) -> Iterator[GoldValue]: ...

    def write_clicks(
        self, sku_clicks: Mapping[int, int], sku_category: Mapping[int, int]
    ) -> None: ...

    def write_category_usage(self, usages: Sequence[CategoryUsage]) -> None: ...

    def write_splits(self, splits: Mapping[int, Split]) -> None: ...

    def write_required(self, required: Sequence[RequiredAttribute]) -> None: ...

    def attach_texts(self) -> TextStats: ...

    def write_stats(self, stats: Mapping[str, object]) -> None: ...
