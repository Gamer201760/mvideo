from typing import Protocol

from app.domain.errors import StorageBusy, StorageFailure, StorageUnavailable


class ReadinessProbe(Protocol):
    async def check(self) -> None: ...


class Readiness:
    def __init__(self, probe: ReadinessProbe) -> None:
        self._probe = probe

    async def check(self) -> None:
        try:
            await self._probe.check()
        except StorageBusy:
            raise
        except StorageFailure:
            raise StorageUnavailable() from None
