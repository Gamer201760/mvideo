import asyncio
from datetime import UTC, datetime
from pathlib import Path

from app.domain.review import ReviewItem, ReviewStatus
from app.repository.sqlite.uow import SqliteUnitOfWork
from tests.integration.stand_client import client_for


def test_current_card_is_available_beyond_the_global_queue_limit(database: Path) -> None:
    async def run() -> None:
        async with SqliteUnitOfWork(database) as unit:
            for index in range(510):
                await unit.reviews.upsert_pending(
                    ReviewItem(
                        id=f"older-{index}",
                        card_key="other-card",
                        category_id=761,
                        title="Queue overflow",
                        attribute="Цвет",
                        value="синий",
                        confidence=0.5,
                        source="hybrid",
                        evidence=f"Color {index}",
                        status=ReviewStatus.PENDING,
                        resolved_value=None,
                        created_at=datetime.now(UTC),
                        resolved_at=None,
                    )
                )
            await unit.commit()
        card = {
            "engine": "hybrid",
            "title": "Queue overflow",
            "category_id": 761,
            "description": "Цвет: синий",
        }
        async with client_for(database) as client:
            result = await client.post("/api/v1/extract", json=card)
            assert result.status_code == 200
            identifiers = {v["review_id"] for v in result.json()["values"] if v["review_id"]}
            assert identifiers
            first = (await client.get("/api/v1/review", params={"status": "pending"})).json()
            assert len(first["items"]) == 50
            assert first["total"] == 510 + len(identifiers)
            assert identifiers.isdisjoint(i["id"] for i in first["items"])
            state = await client.post("/api/v1/review/card", json=card)
            assert state.status_code == 200
            assert {i["id"] for i in state.json()["items"]} == identifiers
            key = state.json()["card_key"]
            selected: list[str] = []
            for offset in range(0, 510, 50):
                response = await client.get(
                    "/api/v1/review",
                    params={
                        "status": "pending",
                        "offset": offset,
                        "limit": 50,
                        "exclude_card_key": key,
                    },
                )
                page = response.json()
                assert page["total"] == 510
                selected.extend(item["id"] for item in page["items"])
            assert len(selected) == len(set(selected)) == 510
            for query in [{"offset": -1}, {"limit": 0}, {"limit": 501}]:
                assert (await client.get("/api/v1/review", params=query)).status_code == 422
            identifier = next(iter(identifiers))
            saved = await client.post(
                f"/api/v1/review/{identifier}", json={"action": "correct", "value": "голубой"}
            )
            assert saved.status_code == 200
            updated = (await client.post("/api/v1/review/card", json=card)).json()
            item = next(item for item in updated["items"] if item["id"] == identifier)
            assert item["status"] == "corrected"
            assert item["resolved_value"] == "голубой"
            different = (
                await client.post(
                    "/api/v1/review/card", json={**card, "description": "Другой текст"}
                )
            ).json()
            assert different["items"] == []

    asyncio.run(run())
