from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.category_guess import CategoryGuess, Ranked


@dataclass(frozen=True, slots=True)
class CategoryCard:
    sku_id: int
    catalog_category: int | None
    split: str | None
    text: str


@dataclass(frozen=True, slots=True)
class ClickVote:
    sku_id: int
    click_category: int
    clicks: int


class CategoryCorpus(Protocol):
    def required_categories(self) -> frozenset[int]: ...

    def category_names(self) -> Mapping[int, str]: ...

    def labelled(self, splits: frozenset[str]) -> Iterator[CategoryCard]: ...

    def click_votes(self) -> Iterator[ClickVote]: ...

    def cards(self, batch: int) -> Iterator[list[CategoryCard]]: ...


class CategoryClassifier(Protocol):
    def fit(self, texts: Sequence[str], labels: Sequence[int]) -> None: ...

    def rank(self, texts: Sequence[str], k: int) -> list[Ranked]: ...


class CategorySink(Protocol):
    def write(self, guesses: Sequence[CategoryGuess]) -> None: ...

    def close(self) -> None: ...

    def report(self, report: Mapping[str, object], markdown: str) -> None: ...
