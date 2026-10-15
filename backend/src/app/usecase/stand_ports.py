from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.card_text import SellerParam
from app.domain.lexicon import LexiconEntry
from app.domain.profile import AttributeProfile
from app.domain.review import Alias, ReviewItem, ReviewStatus
from app.usecase.baseline_ports import RequiredRecord
from app.usecase.extraction import CardExtraction


@dataclass(frozen=True, slots=True, kw_only=True)
class StandCategory:
    category_id: int
    name: str
    path: str


@dataclass(frozen=True, slots=True, kw_only=True)
class StandExample:
    sku_id: int
    category_id: int
    title: str
    description: str
    seller_params: tuple[SellerParam, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class StandTwin:
    sku_id: int
    title: str
    brand: str
    model: str
    values: Mapping[str, tuple[str, str]]


@dataclass(frozen=True, slots=True, kw_only=True)
class StandPack:
    built_at: str
    threshold: float
    profiles: Mapping[str, AttributeProfile]
    entries: Sequence[LexiconEntry]
    priors: Mapping[tuple[int, str], Mapping[str, float]]
    required: Sequence[RequiredRecord]
    categories: Sequence[StandCategory]
    examples: Sequence[StandExample]
    twins: Sequence[StandTwin] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class CardInput:
    title: str
    description: str
    seller_params: tuple[SellerParam, ...]
    category_id: int | None


class StandPackSource(Protocol):
    def load(self) -> StandPack | None: ...


class StandPackSink(Protocol):
    def save(self, pack: StandPack) -> int: ...


class CandidateChooser(Protocol):
    async def choose(self, extraction: CardExtraction, threshold: float, category_id: int | None,
                     known: frozenset[str]) -> CardExtraction: ...


class ReviewRepository(Protocol):
    async def upsert_pending(self, item: ReviewItem) -> ReviewItem: ...

    async def get(self, item_id: str) -> ReviewItem | None: ...

    async def save(self, item: ReviewItem) -> None: ...

    async def list(self, status: ReviewStatus | None) -> list[ReviewItem]: ...


class AliasRepository(Protocol):
    async def add(self, alias: Alias) -> None: ...

    async def all(self) -> list[Alias]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new(self) -> str: ...
