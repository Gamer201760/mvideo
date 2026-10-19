import asyncio
from pathlib import Path

import pytest

from tests.integration.stand_client import client_for


@pytest.mark.parametrize("engine", ["hybrid", "rules"])
def test_review_card_replays_its_original_input_after_restart(database: Path, engine: str) -> None:
    async def run() -> None:
        card = {
            "engine": engine,
            "category_id": 761,
            "title": "Смартфон Север",
            "description": "Цвет: graphite",
            "seller_params": [{"name": "Регион", "value": "Первый", "unit": None}],
        }
        async with client_for(database) as client:
            extracted = await client.post("/api/v1/extract", json=card)
            assert extracted.status_code == 200
            color = next(v for v in extracted.json()["values"] if v["attribute"] == "Цвет")
            identifier = color["review_id"]
            assert identifier
            other = await client.post(
                "/api/v1/extract",
                json={**card, "description": "Цвет: красный"},
            )
            assert other.status_code == 200
        async with client_for(database) as client:
            saved = await client.get(f"/api/v1/review/{identifier}/card")
            assert saved.status_code == 200
            assert saved.json() == card
            decision = await client.post(
                f"/api/v1/review/{identifier}", json={"action": "correct", "value": "синий"}
            )
            assert decision.status_code == 200
            replayed = await client.post("/api/v1/extract", json=saved.json())
            color = next(v for v in replayed.json()["values"] if v["attribute"] == "Цвет")
            assert color["value"] == "синий"
            assert color["source"] == "review"
            assert color["status"] == "accepted"
            missing = await client.get("/api/v1/review/unknown/card")
            assert missing.status_code == 404

    asyncio.run(run())
