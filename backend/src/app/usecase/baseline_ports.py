from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.card_text import SellerParam
from app.usecase.lexicon_builder import TrainValue


@dataclass(frozen=True, slots=True)
class CardRecord:
    sku_id: int
    category_id: int | None
    seller: str | None
    title: str | None
    description: str | None
    seller_params: tuple[SellerParam, ...]
    split: str | None


@dataclass(frozen=True, slots=True)
class GoldRecord:
    attribute: str
    value: str
    unit: str | None


@dataclass(frozen=True, slots=True)
class RequiredRecord:
    category_id: int
    attribute: str
    weight: float


@dataclass(frozen=True, slots=True)
class PredictedValue:
    attribute: str
    value: str
    confidence: float
    source: str
    sources: tuple[str, ...]
    evidence: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class CardPrediction:
    sku_id: int
    category_id: int | None
    split: str | None
    values: tuple[PredictedValue, ...]
    review: tuple[PredictedValue, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateRow:
    sku_id: int
    attribute: str
    key: str
    value: str
    evidence: str
    start: int
    end: int
    source: str
    zone: str
    affinity: float
    prior: float
    seller_fit: int
    slot: int
    score: float
    chosen: bool


class BaselineSource(Protocol):
    def train_values(self, attributes: frozenset[str]) -> Iterator[TrainValue]: ...

    def required(self) -> Sequence[RequiredRecord]: ...

    def category_stats(self) -> Mapping[int, tuple[int, int]]: ...

    def seller_cards(self) -> Mapping[str, int]: ...

    def gold(self, splits: frozenset[str]) -> Mapping[int, Sequence[GoldRecord]]: ...

    def cards(self, splits: frozenset[str] | None, batch: int) -> Iterator[list[CardRecord]]: ...


class PredictionSink(Protocol):
    def write(
        self, predictions: Sequence[CardPrediction], candidates: Sequence[CandidateRow]
    ) -> None: ...

    def close(self) -> None: ...


class ReportSink(Protocol):
    def write(self, report: Mapping[str, object], markdown: str) -> None: ...
