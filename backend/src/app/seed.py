import asyncio
from pathlib import Path

from app.adapter.dataset.demo_catalog import seed_categories
from app.repository.sqlite.uow import SqliteUnitOfWork
from app.settings import load_settings


async def seed(database: Path) -> None:
    categories = await asyncio.to_thread(seed_categories)
    async with SqliteUnitOfWork(database) as unit:
        await unit.catalog.seed(categories)
        await unit.commit()


if __name__ == "__main__":
    asyncio.run(seed(load_settings().database))
