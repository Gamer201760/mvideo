from pathlib import Path
from sqlite3 import Error
from typing import Self

import aiosqlite

from app.repository.sqlite.cards import SqliteCards
from app.repository.sqlite.catalog import SqliteCatalog
from app.repository.sqlite.failures import storage_failure
from app.repository.sqlite.readiness import SqliteSchema
from app.repository.sqlite.review import SqliteAliases, SqliteReviews
from app.repository.sqlite.runs import SqliteRuns
from app.usecase.persistence import CatalogRepository
from app.usecase.readiness import ReadinessProbe
from app.usecase.review_card import CardRepository
from app.usecase.run_ports import RunRepository
from app.usecase.stand_ports import AliasRepository, ReviewRepository


class SqliteUnitOfWork:
    readiness: ReadinessProbe
    reviews: ReviewRepository
    aliases: AliasRepository
    catalog: CatalogRepository
    cards: CardRepository
    runs: RunRepository

    def __init__(self, path: Path, *, timeout_s: float = 10) -> None:
        self._path = path
        self._timeout_s = timeout_s
        self._committed = False

    async def __aenter__(self) -> Self:
        self._committed = False
        try:
            self._db = await self._connect()
        except Error as error:
            raise storage_failure(error) from None
        try:
            await self._db.execute("PRAGMA foreign_keys=ON")
            await self._begin()
            self.reviews = SqliteReviews(self._db)
            self.aliases = SqliteAliases(self._db)
            self.catalog = SqliteCatalog(self._db)
            self.cards = SqliteCards(self._db)
            self.runs = SqliteRuns(self._db)
            self.readiness = SqliteSchema(self._db)
        except BaseException as error:
            await self._db.close()
            if isinstance(error, Error):
                raise storage_failure(error) from None
            raise
        return self

    async def _connect(self) -> aiosqlite.Connection:
        return await aiosqlite.connect(self._path, timeout=self._timeout_s)

    async def _begin(self) -> None:
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("BEGIN IMMEDIATE")

    async def commit(self) -> None:
        try:
            await self._db.commit()
        except Error as error:
            raise storage_failure(error) from None
        self._committed = True

    async def __aexit__(self, *exc: object) -> None:
        try:
            try:
                if not self._committed:
                    await self._db.rollback()
            finally:
                await self._db.close()
        except Error as error:
            raise storage_failure(error) from None
        if len(exc) > 1 and isinstance(exc[1], Error):
            raise storage_failure(exc[1]) from None


class SqliteReadUnitOfWork(SqliteUnitOfWork):
    async def _connect(self) -> aiosqlite.Connection:
        return await aiosqlite.connect(
            self._path.resolve().as_uri() + "?mode=ro", uri=True, timeout=self._timeout_s
        )

    async def _begin(self) -> None:
        await self._db.execute("PRAGMA query_only=ON")
        await self._db.execute("BEGIN")
