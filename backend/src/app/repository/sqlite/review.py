import aiosqlite

from app.domain.review import Alias, ReviewItem
from app.repository.sqlite.records import alias, encode, review
from app.usecase.review_query import ReviewPage, ReviewQuery


class SqliteReviews:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._db = connection

    async def upsert_pending(self, item: ReviewItem) -> ReviewItem:
        await self._db.execute(
            "INSERT INTO reviews(id,card_key,attribute,evidence,status,payload) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(card_key,attribute,evidence) DO NOTHING",
            (
                item.id,
                item.card_key,
                item.attribute,
                item.evidence,
                item.status.value,
                encode(item),
            ),
        )
        async with self._db.execute(
            "SELECT payload FROM reviews WHERE card_key=? AND attribute=? AND evidence=?",
            (item.card_key, item.attribute, item.evidence),
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        return review(row[0])

    async def get(self, item_id: str) -> ReviewItem | None:
        async with self._db.execute("SELECT payload FROM reviews WHERE id=?", (item_id,)) as cursor:
            row = await cursor.fetchone()
        return review(row[0]) if row else None

    async def save(self, item: ReviewItem) -> None:
        await self._db.execute(
            "UPDATE reviews SET status=?,payload=? WHERE id=?",
            (item.status.value, encode(item), item.id),
        )

    async def page(self, query: ReviewQuery) -> ReviewPage:
        clauses, filters = [], []
        if query.status is not None:
            clauses.append("status=?")
            filters.append(query.status.value)
        if query.card_key is not None:
            clauses.append("card_key=?")
            filters.append(query.card_key)
        if query.exclude_card_key is not None:
            clauses.append("card_key<>?")
            filters.append(query.exclude_card_key)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        async with self._db.execute("SELECT COUNT(*) FROM reviews " + where, filters) as cursor:
            count = await cursor.fetchone()
        assert count is not None
        async with self._db.execute(
            "SELECT payload FROM reviews " + where + " ORDER BY rowid LIMIT ? OFFSET ?",
            (*filters, query.limit if query.limit is not None else -1, query.offset),
        ) as cursor:
            rows = await cursor.fetchall()
        return ReviewPage([review(row[0]) for row in rows], count[0])


class SqliteAliases:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._db = connection

    async def add(self, item: Alias) -> None:
        await self._db.execute(
            "INSERT INTO aliases(card_key,category_id,attribute,evidence,payload) VALUES(?,?,?,?,?) "
            "ON CONFLICT(card_key,attribute,evidence) DO UPDATE SET payload=excluded.payload",
            (item.card_key, item.category_id, item.attribute, item.evidence, encode(item)),
        )

    async def all(self) -> list[Alias]:
        async with self._db.execute("SELECT payload FROM aliases ORDER BY rowid") as cursor:
            rows = await cursor.fetchall()
        return [alias(row[0]) for row in rows]
