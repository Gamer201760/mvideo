import asyncio
from pathlib import Path

from app.repository.sqlite.uow import SqliteUnitOfWork
from app.settings import Settings
from tests.integration.stand_client import client_for

CARD = {
    "engine": "hybrid",
    "category_id": 761,
    "title": "Смартфон threshold",
    "description": "Цвет: синий",
}


def test_automatic_values_stay_editable_without_entering_pending_queue(database: Path) -> None:
    async def run() -> None:
        async with client_for(database) as client:
            result = (await client.post("/api/v1/extract", json=CARD)).json()
            color = result["values"][0]
            assert result["threshold"] == 0.95
            assert color["status"] == "accepted"
            assert color["acceptance"] == "automatic"
            assert color["confidence"] == 1
            assert color["source"] != "review"
            pending = await client.get("/api/v1/review", params={"status": "pending"})
            assert pending.json()["total"] == 0
            state = (await client.post("/api/v1/review/card", json=CARD)).json()
            assert state["items"][0]["status"] == "auto_accepted"
            assert state["items"][0]["resolved_value"] is None
            async with SqliteUnitOfWork(database) as unit:
                assert await unit.aliases.all() == []
            corrected = await client.post(
                f"/api/v1/review/{color['review_id']}",
                json={
                    "action": "correct",
                    "value": "серый",
                },
            )
            assert corrected.status_code == 200
        async with client_for(database) as client:
            color = (await client.post("/api/v1/extract", json=CARD)).json()["values"][0]
            assert color["value"] == "серый"
            assert color["source"] == "review"
            assert color["acceptance"] == "manual"
            assert color["confidence"] is None

    asyncio.run(run())


def test_review_only_mode_reclassifies_automatic_state_and_keeps_identifier(database: Path) -> None:
    async def run() -> None:
        async with client_for(database) as client:
            color = (await client.post("/api/v1/extract", json=CARD)).json()["values"][0]
            identifier = color["review_id"]
        async with client_for(
            database, settings=Settings(database=database, auto_accept=False)
        ) as client:
            color = (await client.post("/api/v1/extract", json=CARD)).json()["values"][0]
            assert color["status"] == "review" and color["acceptance"] == "review"
            assert color["review_id"] == identifier
            assert color["confidence"] == 1
            pending = await client.get("/api/v1/review", params={"status": "pending"})
            assert pending.json()["total"] == 1

    asyncio.run(run())


def test_unknown_field_or_missing_field_link_cannot_auto_accept(database: Path) -> None:
    async def run() -> None:
        card = {**CARD, "title": "Смартфон Север S1", "description": "Цвет: синий"}
        async with client_for(database) as client:
            result = (await client.post("/api/v1/extract", json=card)).json()
            for value in result["values"]:
                if "value_supported" not in value["risk"]["reasons"]:
                    assert value["acceptance"] == "review"

    asyncio.run(run())
