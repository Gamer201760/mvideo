from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.usecase.review_card import ReviewCard

RunStatus = Literal["running", "completed", "failed", "interrupted"]


@dataclass(frozen=True, slots=True)
class ExtractionRun:
    id: str
    card: ReviewCard
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    result_json: str | None = None


class RunRepository(Protocol):
    async def add(self, run: ExtractionRun) -> None: ...
    async def get(self, identifier: str) -> ExtractionRun | None: ...
    async def page(self, offset: int, limit: int) -> tuple[list[ExtractionRun], int]: ...
    async def finish(
        self, identifier: str, status: RunStatus, now: datetime, result: str | None
    ) -> None: ...
    async def interrupt(self, now: datetime) -> None: ...
