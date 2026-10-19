from collections.abc import Sequence
from dataclasses import replace

import aiosqlite

from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.domain.category_path import category_path
from app.repository.sqlite.records import category, encode


class SqliteCatalog:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._db = connection

    async def all(self) -> list[CatalogCandidate]:
        async with self._db.execute("SELECT payload FROM categories ORDER BY id") as cursor:
            rows = await cursor.fetchall()
        return [category(row[0]) for row in rows]

    async def seed(self, categories: Sequence[CatalogCandidate]) -> None:
        await self._db.executemany(
            "INSERT INTO categories(id,path,payload) VALUES(?,?,?) ON CONFLICT DO NOTHING",
            [(c.category_id, c.path, encode(c)) for c in categories],
        )

    async def register(self, path: str, fields: Sequence[CatalogField]) -> CatalogCandidate:
        path = category_path(path)
        if not fields:
            raise ValueError("Invalid category")
        async with self._db.execute(
            "SELECT payload FROM categories WHERE path=?", (path,)
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            previous = category(row[0])
            merged = {f.attribute.casefold(): f for f in previous.fields}
            for field in fields:
                merged.setdefault(field.attribute.casefold(), field)
            result = replace(previous, fields=tuple(merged.values()))
        else:
            async with self._db.execute("SELECT MIN(id) FROM categories") as cursor:
                minimum = await cursor.fetchone()
            identifier = min(0, minimum[0] or 0) - 1 if minimum else -1
            result = CatalogCandidate(identifier, path, 0, tuple(fields))
        await self._db.execute(
            "INSERT INTO categories(id,path,payload) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
            (result.category_id, path, encode(result)),
        )
        return result
