import json
from dataclasses import asdict
from datetime import datetime

import aiosqlite

from app.domain.card_text import SellerParam
from app.usecase.review_card import ReviewCard
from app.usecase.run_ports import ExtractionRun, RunStatus
from app.usecase.stand_ports import CardInput


class SqliteRuns:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._db = connection

    async def add(self, run: ExtractionRun) -> None:
        await self._db.execute(
            "INSERT INTO extraction_runs(id,engine,status,started_at,input_json) VALUES(?,?,?,?,?)",
            (
                run.id,
                run.card.engine,
                run.status,
                run.started_at.isoformat(),
                json.dumps(asdict(run.card.input), ensure_ascii=False),
            ),
        )

    async def get(self, identifier: str) -> ExtractionRun | None:
        async with self._db.execute(
            "SELECT id,engine,status,started_at,finished_at,input_json,result_json FROM extraction_runs WHERE id=?",
            (identifier,),
        ) as cursor:
            row = await cursor.fetchone()
        return _run(row) if row is not None else None

    async def page(self, offset: int, limit: int) -> tuple[list[ExtractionRun], int]:
        async with self._db.execute("SELECT COUNT(*) FROM extraction_runs") as cursor:
            count = await cursor.fetchone()
        assert count is not None
        async with self._db.execute(
            "SELECT id,engine,status,started_at,finished_at,input_json,NULL FROM extraction_runs ORDER BY started_at DESC,id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_run(row) for row in rows], count[0]

    async def finish(
        self, identifier: str, status: RunStatus, now: datetime, result: str | None
    ) -> None:
        await self._db.execute(
            "UPDATE extraction_runs SET status=?,finished_at=?,result_json=? WHERE id=? AND status='running'",
            (status, now.isoformat(), result, identifier),
        )

    async def interrupt(self, now: datetime) -> None:
        await self._db.execute(
            "UPDATE extraction_runs SET status='interrupted',finished_at=? WHERE status='running'",
            (now.isoformat(),),
        )


def _run(row: aiosqlite.Row) -> ExtractionRun:
    data = json.loads(row[5])
    data["seller_params"] = tuple(SellerParam(**param) for param in data["seller_params"])
    return ExtractionRun(
        row[0],
        ReviewCard(CardInput(**data), row[1]),
        row[2],
        datetime.fromisoformat(row[3]),
        datetime.fromisoformat(row[4]) if row[4] else None,
        row[6],
    )
