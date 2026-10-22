import asyncio
import sqlite3
from pathlib import Path

import httpx
import pytest

from app.main import create_app
from app.settings import Settings
from tests.integration.stand_client import client_for


@pytest.mark.parametrize("engine", ["rules", "hybrid"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("threshold", [0.95, 1.0])
def test_both_engines_apply_configured_policy(
    database: Path, engine: str, enabled: bool, threshold: float
) -> None:
    async def run() -> None:
        settings = Settings(database=database, auto_accept=enabled, acceptance_threshold=threshold)
        async with client_for(database, settings=settings) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": engine,
                    "title": "Смартфон",
                    "description": "Цвет: синий",
                    "category_id": 761,
                },
            )
            assert response.status_code == 200
            result = response.json()
            assert result["threshold"] == threshold
            assert result["auto_accept_enabled"] is enabled
            color = next(v for v in result["values"] if v["attribute"] == "Цвет")
            assert color["acceptance"] == ("automatic" if enabled else "review")
            assert color["status"] == ("accepted" if enabled else "review")
            assert color["risk"]["score"] == color["confidence"] == 1
            assert result["text"][color["start"] : color["end"]] == color["evidence"]

    asyncio.run(run())


@pytest.mark.parametrize("engine", ["rules", "hybrid"])
def test_manual_decision_survives_disabled_acceptance(database: Path, engine: str) -> None:
    body = {"engine": engine, "title": "Смартфон", "description": "Цвет: синий", "category_id": 761}

    async def run() -> None:
        async with client_for(database) as client:
            result = (await client.post("/api/v1/extract", json=body)).json()
            color = next(v for v in result["values"] if v["attribute"] == "Цвет")
            response = await client.post(
                f"/api/v1/review/{color['review_id']}", json={"action": "accept"}
            )
            assert response.status_code == 200
        async with client_for(
            database, settings=Settings(database=database, auto_accept=False)
        ) as client:
            result = (await client.post("/api/v1/extract", json=body)).json()
            color = next(v for v in result["values"] if v["attribute"] == "Цвет")
            assert color["acceptance"] == "manual"
            assert color["status"] == "accepted"
            assert color["confidence"] is None
            assert color["review_id"] is not None

    asyncio.run(run())


def test_rules_storage_failure_rolls_back_card_and_all_review_values(database: Path) -> None:
    async def run() -> None:
        app = create_app(Settings(database=database))
        async with app.router.lifespan_context(app):
            with sqlite3.connect(database) as db:
                db.execute(
                    "CREATE TRIGGER reject_color BEFORE INSERT ON reviews "
                    "WHEN NEW.attribute='Цвет' BEGIN SELECT RAISE(ABORT,'test failure'); END"
                )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/v1/extract",
                    json={
                        "engine": "rules",
                        "title": "Смартфон",
                        "category_id": 761,
                        "description": "Встроенная память (ROM): 256 ГБ\nЦвет: синий",
                    },
                )
                assert response.status_code == 500
            with sqlite3.connect(database) as db:
                assert db.execute("SELECT count(*) FROM reviews").fetchone()[0] == 0
                assert db.execute("SELECT count(*) FROM review_cards").fetchone()[0] == 0
                assert db.execute("SELECT status FROM extraction_runs").fetchone()[0] == "failed"

    asyncio.run(run())
