import uuid
from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidIds:
    def new(self) -> str:
        return uuid.uuid4().hex
