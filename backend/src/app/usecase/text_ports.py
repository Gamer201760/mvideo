from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.inference import Vector
from app.usecase.baseline_ports import CardRecord, RequiredRecord
from app.usecase.ranker_ports import Calibrator
from app.usecase.twin_ports import GoldRow


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    sku_id: int
    category_id: int
    title: str
    values: Mapping[str, str]


class CatalogSearch(Protocol):
    @property
    def kind(self) -> str: ...

    async def search(self, texts: Sequence[str], k: int) -> list[list[tuple[int, float]]]: ...


@dataclass(frozen=True, slots=True)
class CategoryModel:
    calibrator: Calibrator
    threshold: float


@dataclass(frozen=True, slots=True)
class TextIndex:
    entries: Sequence[CatalogEntry]
    names: Mapping[int, str]
    models: Mapping[str, CategoryModel]
    embedding_model: str
    dimensions: int


class Spending(Protocol):
    def spent_rub(self) -> float: ...

    def paid_calls(self) -> int: ...


class TextCorpus(Protocol):
    def required(self) -> Sequence[RequiredRecord]: ...

    def cards(self, splits: frozenset[str] | None, batch: int) -> Iterator[list[CardRecord]]: ...

    def gold_rows(
        self, splits: frozenset[str], attributes: frozenset[str]
    ) -> Iterator[Sequence[GoldRow]]: ...


class TextIndexSink(Protocol):
    def start(self, entries: Sequence[CatalogEntry], names: Mapping[int, str],
              embedding_model: str, dimensions: int) -> None: ...

    def add_vectors(self, vectors: Sequence[Vector]) -> None: ...

    def finish(self) -> None: ...

    def save_model(self, kind: str, calibrator: Calibrator, threshold: float,
                   report: Mapping[str, object]) -> None: ...
