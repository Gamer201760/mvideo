import asyncio
from pathlib import Path

from app.domain.attribute_flow import CatalogField
from app.repository.sqlite.uow import SqliteUnitOfWork
from app.seed import seed
from tests.integration.stand_client import NewCategoryModel, client_for


def test_new_category_fields_and_reviews_survive_restart_and_reseed(database: Path) -> None:
    async def run() -> None:
        async with client_for(database, NewCategoryModel()) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "title": "Беспилотник Север",
                    "description": "Дальность полета: 12 км",
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            identifier = body["category"]["category_id"]
            assert identifier < 0
            value = body["values"][0]
            assert value["attribute"] == "Дальность полета"
            assert body["text"][value["start"] : value["end"]] == value["evidence"]
            assert value["review_id"]
        await seed(database)
        await seed(database)
        async with client_for(database) as client:
            categories = (await client.get("/api/v1/stand")).json()["categories"]
            restored = [c for c in categories if c["category_id"] == identifier]
            assert len(restored) == 1
            assert restored[0]["path"] == "Техника / Беспилотники"
            assert "Дальность полета" in restored[0]["attributes"]
            reviews = (await client.get("/api/v1/review")).json()["items"]
            assert any(i["category_id"] == identifier for i in reviews)

    asyncio.run(run())


def test_uncommitted_catalog_update_is_not_persisted(database: Path) -> None:
    async def run() -> None:
        async with SqliteUnitOfWork(database) as unit:
            await unit.catalog.register(
                "Transient / Category", [CatalogField("Width", "numeric", "mm")]
            )
        async with SqliteUnitOfWork(database) as unit:
            assert all(c.path != "Transient / Category" for c in await unit.catalog.all())

    asyncio.run(run())
