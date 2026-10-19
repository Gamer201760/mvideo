import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.domain.review import ReviewItem, ReviewStatus
from app.repository.sqlite.uow import SqliteUnitOfWork
from app.usecase.persistent_review import PersistentReview
from tests.integration.stand_client import ColorModel, client_for

CARD: dict[str, Any] = {
    "engine": "hybrid",
    "category_id": 761,
    "title": "Смартфон Север",
    "description": "Цвет: синий",
}


def test_main_mode_review_survives_restart_before_and_after_correction(database: Path) -> None:
    async def run() -> None:
        async with client_for(database) as client:
            response = await client.post("/api/v1/extract", json=CARD)
            assert response.status_code == 200
            result = response.json()
            assert result["engine"] == "hybrid"
            color = next(v for v in result["values"] if v["attribute"] == "Цвет")
            assert color["acceptance"] == "automatic"
            identifier = color["review_id"]
            assert identifier
        async with client_for(database) as client:
            automatic = (
                await client.get("/api/v1/review", params={"status": "auto_accepted"})
            ).json()
            assert any(item["id"] == identifier for item in automatic["items"])
            decision = await client.post(
                f"/api/v1/review/{identifier}",
                json={"action": "correct", "value": "голубой"},
            )
            assert decision.status_code == 200
            repeated = (await client.post("/api/v1/extract", json=CARD)).json()
            color = next(v for v in repeated["values"] if v["attribute"] == "Цвет")
            assert color["value"] == "голубой"
            assert color["source"] == "review"
        async with client_for(database) as client:
            repeated = (await client.post("/api/v1/extract", json=CARD)).json()
            color = next(v for v in repeated["values"] if v["attribute"] == "Цвет")
            assert color["value"] == "голубой"
            assert color["source"] == "review"
            assert color["status"] == "accepted"
            assert color["review_id"] is None
            pending = (await client.get("/api/v1/review", params={"status": "pending"})).json()
            assert all(item["id"] != identifier for item in pending["items"])
            history = (await client.get("/api/v1/review", params={"status": "corrected"})).json()
            assert any(
                item["id"] == identifier and item["resolved_value"] == "голубой"
                for item in history["items"]
            )

    asyncio.run(run())


def test_review_and_alias_writes_roll_back_atomically(database: Path) -> None:
    async def run() -> None:
        item = ReviewItem(
            id="pending",
            card_key="card-a",
            category_id=761,
            title="Sample card",
            attribute="Цвет",
            value="синий",
            confidence=0.5,
            source="hybrid",
            evidence="Цвет: синий",
            status=ReviewStatus.PENDING,
            resolved_value=None,
            created_at=datetime.now(UTC),
            resolved_at=None,
        )
        async with SqliteUnitOfWork(database) as unit:
            await unit.reviews.upsert_pending(item)
            await unit.commit()
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TRIGGER reject_alias BEFORE INSERT ON aliases "
                "BEGIN SELECT RAISE(ABORT, 'forced write failure'); END"
            )
        service = PersistentReview(lambda: SqliteUnitOfWork(database))
        with pytest.raises(sqlite3.IntegrityError, match="forced write failure"):
            await service.resolve("pending", "correct", "голубой", datetime.now(UTC))
        async with SqliteUnitOfWork(database) as unit:
            assert await unit.reviews.get("pending") == item
            assert await unit.aliases.all() == []

    asyncio.run(run())


def test_review_retries_are_idempotent_and_conflicts_return_409(database: Path) -> None:
    async def run() -> None:
        async with client_for(database, ColorModel()) as client:
            extracted = await client.post("/api/v1/extract", json=CARD)
            assert extracted.status_code == 200
            review_id = extracted.json()["values"][0]["review_id"]
            decision = {"action": "correct", "value": "синий"}
            first = await client.post(f"/api/v1/review/{review_id}", json=decision)
            repeat = await client.post(f"/api/v1/review/{review_id}", json=decision)
            assert first.status_code == repeat.status_code == 200
            assert first.json() == repeat.json()
            for conflict in [{"action": "accept"}, {"action": "correct", "value": "красный"}]:
                response = await client.post(f"/api/v1/review/{review_id}", json=conflict)
                assert response.status_code == 409
            async with SqliteUnitOfWork(database) as unit:
                assert len(await unit.aliases.all()) == 1

    asyncio.run(run())


def test_human_override_survives_restart_changed_quote_and_abstention(database: Path) -> None:
    async def run() -> None:
        async with client_for(database, ColorModel()) as client:
            first = await client.post("/api/v1/extract", json=CARD)
            identifier = first.json()["values"][0]["review_id"]
            decision = await client.post(
                f"/api/v1/review/{identifier}",
                json={
                    "action": "correct",
                    "value": "голубой",
                },
            )
            assert decision.status_code == 200
        model = ColorModel()
        model.quote = "синий"
        async with client_for(database, model) as client:
            for abstain in [False, True]:
                model.abstain = abstain
                response = await client.post("/api/v1/extract", json=CARD)
                assert response.status_code == 200
                color = next(v for v in response.json()["values"] if v["attribute"] == "Цвет")
                assert color["value"] == "голубой"
                assert color["status"] == "accepted"
                assert color["source"] == "review"
                assert color["evidence"] == "Цвет: синий"
                assert color["review_id"] is None
                assert "Цвет" not in response.json()["missing"]
            reviews = (await client.get("/api/v1/review")).json()["items"]
            assert len(reviews) == 1
            assert reviews[0]["resolved_value"] == "голубой"

    asyncio.run(run())


def test_human_override_does_not_cross_card_category_or_seller_context(database: Path) -> None:
    async def run() -> None:
        async with client_for(database, ColorModel()) as client:
            response = await client.post("/api/v1/extract", json=CARD)
            identifier = response.json()["values"][0]["review_id"]
            await client.post(
                f"/api/v1/review/{identifier}",
                json={
                    "action": "correct",
                    "value": "голубой",
                },
            )
            cases: list[dict[str, Any]] = [
                {"title": "Другой смартфон"},
                {"category_id": 987},
                {"seller_params": [{"name": "Регион", "value": "Другой"}]},
            ]
            for changed in cases:
                response = await client.post("/api/v1/extract", json={**CARD, **changed})
                assert response.status_code == 200
                color = next(v for v in response.json()["values"] if v["attribute"] == "Цвет")
                assert color["source"] != "review"
                assert color["acceptance"] != "manual"
                assert color["value"] == "синий"
                assert color["review_id"] != identifier

    asyncio.run(run())


def test_concurrent_identical_decisions_create_one_alias(database: Path) -> None:
    async def run() -> None:
        async with client_for(database, ColorModel()) as client:
            extracted = await client.post("/api/v1/extract", json=CARD)
            identifier = extracted.json()["values"][0]["review_id"]

            def factory() -> SqliteUnitOfWork:
                return SqliteUnitOfWork(database)

            services = [PersistentReview(factory), PersistentReview(factory)]
            decisions = await asyncio.gather(
                *[
                    service.resolve(identifier, "correct", "голубой", datetime.now(UTC))
                    for service in services
                ]
            )
            assert decisions[0] == decisions[1]
            async with factory() as unit:
                assert len(await unit.aliases.all()) == 1
                assert (await unit.reviews.get(identifier)) == decisions[0]

    asyncio.run(run())
