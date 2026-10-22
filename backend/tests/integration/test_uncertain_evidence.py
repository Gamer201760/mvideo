import asyncio
from pathlib import Path

import pytest

from tests.integration.stand_client import client_for


@pytest.mark.parametrize("engine", ["rules", "hybrid"])
@pytest.mark.parametrize(
    ("attribute", "description"),
    [
        ("Мощность", "Мощность: примерно 100 Вт"),
        ("Мощность", "Мощность: максимум 100 Вт"),
        ("Цвет", "Цвет: возможно красный"),
        ("Цвет", "Цвет: красный или синий"),
    ],
)
def test_uncertain_rules_never_reach_automatic_acceptance_or_pending_queue(
    database: Path, engine: str, attribute: str, description: str
) -> None:
    async def run() -> None:
        async with client_for(database) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": engine,
                    "category_id": 1001,
                    "title": "Чайник",
                    "description": description,
                },
            )
            assert response.status_code == 200
            result = response.json()
            assert all(
                v["attribute"] != attribute for v in result["values"] + result["extra_values"]
            )
            assert attribute in result["missing"]
            pending = (await client.get("/api/v1/review", params={"status": "pending"})).json()
            assert pending["total"] == 0
            run_id = (await client.get("/api/v1/runs")).json()["items"][0]["id"]
        async with client_for(database) as client:
            assert (await client.get(f"/api/v1/runs/{run_id}")).json()["result"] == result

    asyncio.run(run())


@pytest.mark.parametrize("engine", ["rules", "hybrid"])
@pytest.mark.parametrize("raw", ["green", "зеленая", "зеленый", "зелёный"])
def test_color_aliases_reach_http_with_one_canon_and_original_offsets(
    database: Path, engine: str, raw: str
) -> None:
    async def run() -> None:
        async with client_for(database) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": engine,
                    "category_id": 1001,
                    "title": "Чайник",
                    "description": f"Цвет: {raw}",
                },
            )
            assert response.status_code == 200
            result = response.json()
            color = next(v for v in result["values"] if v["attribute"] == "Цвет")
            assert color["value"] == "зеленый"
            assert result["text"][color["start"] : color["end"]] == color["evidence"] == raw
            assert color["acceptance"] == "automatic"
            assert result["rejections"] == []

    asyncio.run(run())
