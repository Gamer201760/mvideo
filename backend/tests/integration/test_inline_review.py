import asyncio
from pathlib import Path

from tests.integration.stand_client import client_for


def test_inline_confirmation_and_explicit_override_survive_restart(database: Path) -> None:
    async def run() -> None:
        card = {
            "engine": "hybrid",
            "category_id": 761,
            "title": "Смартфон Север Inline",
            "description": "Цвет: синий",
        }
        async with client_for(database) as client:
            extracted = await client.post("/api/v1/extract", json=card)
            assert extracted.status_code == 200
            color = next(v for v in extracted.json()["values"] if v["attribute"] == "Цвет")
            identifier = color["review_id"]
            assert identifier
            url = f"/api/v1/review/{identifier}"
            accepted = await client.post(url, json={"action": "accept"})
            assert accepted.status_code == 200
            assert accepted.json()["resolved_value"] == color["value"]
            rejected = await client.post(url, json={"action": "correct", "value": "серый"})
            assert rejected.status_code == 409
            stale = await client.post(
                url,
                json={
                    "action": "correct",
                    "value": "серый",
                    "override": True,
                    "expected_value": "устаревшее значение",
                },
            )
            assert stale.status_code == 409
            changed = await client.post(
                url,
                json={
                    "action": "correct",
                    "value": "серый",
                    "override": True,
                    "expected_value": color["value"],
                },
            )
            assert changed.status_code == 200
            assert changed.json()["resolved_value"] == "серый"
        async with client_for(database) as client:
            reviews = await client.post("/api/v1/review/card", json=card)
            assert reviews.status_code == 200
            updated = next(v for v in reviews.json()["items"] if v["id"] == identifier)
            assert updated["status"] == "corrected"
            assert updated["resolved_value"] == "серый"
            extracted = await client.post("/api/v1/extract", json=card)
            color = next(v for v in extracted.json()["values"] if v["attribute"] == "Цвет")
            assert color["value"] == "серый"
            assert color["status"] == "accepted"

    asyncio.run(run())
