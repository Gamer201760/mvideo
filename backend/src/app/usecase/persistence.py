from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol, Self

from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.domain.review import Alias, ReviewItem
from app.usecase.review_card import CardRepository, ReviewCard
from app.usecase.run_ports import RunRepository
from app.usecase.stand_ports import AliasRepository, CardInput, ReviewRepository


class CatalogRepository(Protocol):
    async def all(self) -> list[CatalogCandidate]: ...
    async def register(self, path: str, fields: Sequence[CatalogField]) -> CatalogCandidate: ...
    async def seed(self, categories: Sequence[CatalogCandidate]) -> None: ...


class UnitOfWork(Protocol):
    reviews: ReviewRepository
    aliases: AliasRepository
    catalog: CatalogRepository
    cards: CardRepository
    runs: RunRepository

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None: ...
    async def commit(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]


class ReviewDecisions(Protocol):
    async def add(
        self, card: CardInput, attribute: str, value: str, evidence: str, now: datetime
    ) -> ReviewItem: ...

    async def card(self, item_id: str) -> ReviewCard: ...

    async def resolve(
        self,
        item_id: str,
        action: str,
        value: str | None,
        now: datetime,
        *,
        override: bool = False,
        expected_value: str | None = None,
    ) -> ReviewItem: ...


class ReviewAliases(Protocol):
    async def all(self) -> list[Alias]: ...
