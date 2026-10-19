from app.domain.errors import RunNotFound
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.review_card import ReviewCard
from app.usecase.run_ports import ExtractionRun, RunStatus
from app.usecase.stand_ports import Clock, IdGenerator


class RunHistory:
    def __init__(self, store: UnitOfWorkFactory, clock: Clock, ids: IdGenerator) -> None:
        self._store, self._clock, self._ids = store, clock, ids

    async def begin(self, card: ReviewCard) -> str:
        run = ExtractionRun(self._ids.new(), card, "running", self._clock.now())
        async with self._store() as unit:
            await unit.runs.add(run)
            await unit.commit()
        return run.id

    async def finish(self, identifier: str, result: str | None) -> None:
        status: RunStatus = "completed" if result is not None else "failed"
        async with self._store() as unit:
            await unit.runs.finish(identifier, status, self._clock.now(), result)
            await unit.commit()

    async def get(self, identifier: str) -> ExtractionRun:
        async with self._store() as unit:
            run = await unit.runs.get(identifier)
        if run is None:
            raise RunNotFound()
        return run

    async def page(self, offset: int, limit: int) -> tuple[list[ExtractionRun], int]:
        async with self._store() as unit:
            return await unit.runs.page(offset, limit)

    async def recover(self) -> None:
        async with self._store() as unit:
            await unit.runs.interrupt(self._clock.now())
            await unit.commit()
