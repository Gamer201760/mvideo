from array import array
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.usecase.baseline_ports import BaselineSource, GoldRecord


@dataclass(slots=True)
class FeatureTable:
    width: int
    numeric: array[float] = field(default_factory=lambda: array("f"))
    categorical: list[tuple[str, ...]] = field(default_factory=list)
    labels: array[int] = field(default_factory=lambda: array("b"))

    @property
    def rows(self) -> int:
        return len(self.categorical)

    def add(self, numeric: Sequence[float], categorical: tuple[str, ...], label: int) -> None:
        self.numeric.extend(numeric)
        self.categorical.append(categorical)
        self.labels.append(label)


class RankerSource(BaselineSource, Protocol):
    def gold_where(
        self, splits: frozenset[str], attributes: frozenset[str], modulo: int
    ) -> Mapping[int, Sequence[GoldRecord]]: ...


class ScoreModel(Protocol):
    def fit(self, train: FeatureTable, names: Sequence[str], categorical: Sequence[str]) -> None: ...

    def predict(self, table: FeatureTable) -> Sequence[float]: ...

    def importances(self) -> Mapping[str, float]: ...


class Calibrator(Protocol):
    def fit(self, scores: Sequence[float], labels: Sequence[bool]) -> None: ...

    def transform(self, scores: Sequence[float]) -> Sequence[float]: ...
