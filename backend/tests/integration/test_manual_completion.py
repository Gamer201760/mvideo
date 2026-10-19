import asyncio
import sqlite3
from pathlib import Path

import pytest

from tests.integration.stand_client import client_for


@pytest.mark.parametrize("engine", ["rules", "hybrid"])
def test_add_reject_restore_and_restart_keep_manual_decisions(database: Path, engine: str) -> None:
    async def run() -> None:
        card = {
            "engine": engine,
            "category_id": 761,
            "title": "Смартфон Север Completion",
            "description": "Оттенок корпуса лазурный",
        }
        addition = {
            "card": card,
            "attribute": "Цвет",
            "value": "лазурный",
            "evidence": "Оттенок корпуса лазурный",
        }
        async with client_for(database) as client:
            initial = await client.post("/api/v1/extract", json=card)
            assert initial.status_code == 200
            assert "Цвет" in initial.json()["missing"]
            added = await client.post("/api/v1/review/add", json=addition)
            assert added.status_code == 200
            item = added.json()
            assert item["status"] == "corrected"
            repeated = await client.post("/api/v1/review/add", json=addition)
            assert repeated.json() == item
            conflicting = await client.post(
                "/api/v1/review/add", json={**addition, "value": "другое значение"}
            )
            assert conflicting.status_code == 409
        async with client_for(database) as client:
            result = (await client.post("/api/v1/extract", json=card)).json()
            color = next(v for v in result["values"] if v["attribute"] == "Цвет")
            assert color["value"] == "лазурный"
            assert color["source"] == "review" and color["acceptance"] == "manual"
            assert color["confidence"] is None and color.get("risk") is None
            assert result["text"][color["start"] : color["end"]] == color["evidence"]
            assert "Цвет" not in result["missing"]
            url = f"/api/v1/review/{item['id']}"
            stale = await client.post(url, json={"action": "reject"})
            assert stale.status_code == 409
            rejected = await client.post(
                url,
                json={
                    "action": "reject",
                    "override": True,
                    "expected_value": "лазурный",
                },
            )
            assert rejected.status_code == 200
            assert rejected.json()["status"] == "rejected"
            assert rejected.json()["resolved_value"] is None
            repeated = await client.post(url, json={"action": "reject"})
            assert repeated.json() == rejected.json()
        async with client_for(database) as client:
            result = (await client.post("/api/v1/extract", json=card)).json()
            assert not any(v["attribute"] == "Цвет" for v in result["values"])
            assert "Цвет" in result["missing"]
            reviews = (await client.post("/api/v1/review/card", json=card)).json()
            assert (
                next(i for i in reviews["items"] if i["id"] == item["id"])["status"] == "rejected"
            )
            restored = await client.post("/api/v1/review/add", json=addition)
            assert restored.status_code == 200
            assert restored.json()["status"] == "corrected"
            result = (await client.post("/api/v1/extract", json=card)).json()
            assert (
                next(v for v in result["values"] if v["attribute"] == "Цвет")["value"] == "лазурный"
            )
            other = {**card, "description": "У другой карточки тот же оттенок корпуса"}
            result = (await client.post("/api/v1/extract", json=other)).json()
            assert not any(v["attribute"] == "Цвет" for v in result["values"])

    asyncio.run(run())


@pytest.mark.parametrize("engine", ["rules", "hybrid"])
def test_rejection_overrides_automatic_acceptance_without_training_an_alias(
    database: Path, engine: str
) -> None:
    async def run() -> None:
        card = {
            "engine": engine,
            "category_id": 761,
            "title": "Смартфон",
            "description": "Цвет: синий",
        }
        async with client_for(database) as client:
            initial = (await client.post("/api/v1/extract", json=card)).json()
            value = next(v for v in initial["values"] if v["attribute"] == "Цвет")
            assert value["acceptance"] == "automatic"
            url = f"/api/v1/review/{value['review_id']}"
            response = await client.post(url, json={"action": "reject"})
            assert response.status_code == 200
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT COUNT(*) FROM aliases").fetchone() == (0,)
        async with client_for(database) as client:
            result = (await client.post("/api/v1/extract", json=card)).json()
            assert not any(v["attribute"] == "Цвет" for v in result["values"])
            other = (
                await client.post("/api/v1/extract", json={**card, "title": "Другой смартфон"})
            ).json()
            assert next(v for v in other["values"] if v["attribute"] == "Цвет")["value"] == "синий"

    asyncio.run(run())


def test_manual_addition_rejects_fabricated_evidence_unknown_fields_and_unknown_cards(
    database: Path,
) -> None:
    async def run() -> None:
        card = {
            "engine": "hybrid",
            "category_id": 761,
            "title": "Смартфон",
            "description": "Лазурный корпус",
        }
        body = {
            "card": card,
            "attribute": "Цвет",
            "value": "лазурный",
            "evidence": "Лазурный корпус",
        }
        async with client_for(database) as client:
            unknown = await client.post("/api/v1/review/add", json=body)
            assert unknown.status_code == 404
            assert (await client.post("/api/v1/extract", json=card)).status_code == 200
            for patch, code in [
                ({"evidence": "нет в карточке"}, "invalid_review_evidence"),
                ({"evidence": "   "}, "invalid_review_evidence"),
                ({"attribute": "Дальность полета"}, "invalid_review_attribute"),
                ({"attribute": "color_search"}, "invalid_review_attribute"),
                ({"value": "   "}, "invalid_correction"),
            ]:
                response = await client.post("/api/v1/review/add", json={**body, **patch})
                assert response.status_code == 422
                assert response.json()["code"] == code
            assert (await client.post("/api/v1/review/card", json=card)).json()["items"] == []

    asyncio.run(run())


def test_concurrent_additions_do_not_silently_overwrite_each_other(database: Path) -> None:
    async def run() -> None:
        card = {
            "engine": "hybrid",
            "category_id": 761,
            "title": "Смартфон",
            "description": "Лазурный корпус",
        }
        body = {"card": card, "attribute": "Цвет", "evidence": "Лазурный корпус"}
        async with client_for(database) as client:
            assert (await client.post("/api/v1/extract", json=card)).status_code == 200
            results = await asyncio.gather(
                *(
                    client.post("/api/v1/review/add", json={**body, "value": value})
                    for value in ["лазурный", "голубой"]
                )
            )
            assert sorted(r.status_code for r in results) == [200, 409]
            winner = next(r.json() for r in results if r.status_code == 200)
            items = (await client.post("/api/v1/review/card", json=card)).json()["items"]
            assert len(items) == 1 and items[0] == winner

    asyncio.run(run())
