from dataclasses import dataclass
from typing import Literal, Protocol

from app.usecase.stand_ports import CardInput


@dataclass(frozen=True, slots=True)
class ReviewCard:
    input: CardInput
    engine: Literal["rules", "hybrid"]


class CardRepository(Protocol):
    async def save(self, key: str, card: ReviewCard) -> None: ...
    async def get(self, key: str) -> ReviewCard | None: ...
