from pathlib import Path
from typing import Self

import aiosqlite

from app.repository.sqlite.cards import SqliteCards
from app.repository.sqlite.catalog import SqliteCatalog
from app.repository.sqlite.review import SqliteAliases, SqliteReviews
from app.repository.sqlite.runs import SqliteRuns
from app.usecase.persistence import CatalogRepository
from app.usecase.review_card import CardRepository
from app.usecase.run_ports import RunRepository
from app.usecase.stand_ports import AliasRepository, ReviewRepository


class SqliteUnitOfWork:
    reviews: ReviewRepository
    aliases: AliasRepository
    catalog: CatalogRepository
    cards: CardRepository
    runs: RunRepository

    def __init__(self, path: Path) -> None:
        self._path = path
        self._committed = False

    async def __aenter__(self) -> Self:
        self._db = await aiosqlite.connect(self._path, timeout=10)
        try:
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA foreign_keys=ON")
            await self._db.execute("PRAGMA busy_timeout=10000")
            await self._db.execute("BEGIN IMMEDIATE")
            self.reviews = SqliteReviews(self._db)
            self.aliases = SqliteAliases(self._db)
            self.catalog = SqliteCatalog(self._db)
            self.cards = SqliteCards(self._db)
            self.runs = SqliteRuns(self._db)
        except BaseException:
            await self._db.close()
            raise
        return self

    async def commit(self) -> None:
        await self._db.commit()
        self._committed = True

    async def __aexit__(self, *exc: object) -> None:
        try:
            if not self._committed:
                await self._db.rollback()
        finally:
            await self._db.close()
