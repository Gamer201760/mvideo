import aiosqlite

from app.usecase.persistence import UnitOfWorkFactory

CHECK_SCHEMA = """
SELECT c.id,c.path,c.payload,r.id,r.card_key,r.attribute,r.evidence,r.status,r.payload,
       a.card_key,a.category_id,a.attribute,a.evidence,a.payload,k.card_key,k.payload,
       x.id,x.engine,x.status,x.started_at,x.finished_at,x.input_json,x.result_json
FROM categories c,reviews r,aliases a,review_cards k,extraction_runs x
LIMIT 0
"""


class SqliteSchema:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._db = connection

    async def check(self) -> None:
        async with self._db.execute(CHECK_SCHEMA) as cursor:
            await cursor.fetchone()


class SqliteReadiness:
    def __init__(self, factory: UnitOfWorkFactory) -> None:
        self._factory = factory

    async def check(self) -> None:
        async with self._factory() as unit:
            await unit.readiness.check()
