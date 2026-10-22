import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from app.adapter.llm.gateway import GatewayModel
from app.adapter.llm.gateway_retry import GatewayRetry
from app.main import create_app
from app.settings import Settings
from tests.integration.stand_client import client_for

CARD = {
    "engine": "hybrid",
    "category_id": 761,
    "title": "Смартфон fallback",
    "description": "Цвет: синий",
}


@asynccontextmanager
async def fallback_client(database: Path, model: GatewayModel) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(
            database=database,
            rules_first=False,
            gateway_key="test-key",
            batch_size=1,
            concurrency=1,
        ),
        model=model,
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


def test_gateway_exhaustion_returns_grounded_partial_result_and_persists_fallback_reason(
    database: Path,
) -> None:
    async def run() -> None:
        attempts = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503, text="private upstream credentials")

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=GatewayRetry(base_delay_s=0),
            transport=httpx.MockTransport(respond),
        )
        async with fallback_client(database, model) as client:
            response = await client.post("/api/v1/extract", json=CARD)
            assert response.status_code == 200, response.text
            result = response.json()
            assert attempts == 2
            assert result["fallback_reason"] == "model_unavailable"
            assert result["missing"]
            color = next(v for v in result["values"] if v["attribute"] == "Цвет")
            assert color["value"] == "синий"
            assert result["text"][color["start"] : color["end"]] == color["evidence"] == "синий"
            assert "private" not in response.text
            saved = (await client.get("/api/v1/runs")).json()["items"][0]
            assert saved["status"] == "completed"
        async with client_for(database) as client:
            assert (await client.get(f"/api/v1/runs/{saved['id']}")).json()["result"] == result

    asyncio.run(run())


def test_batch_keeps_healthy_result_separate_from_local_fallback_and_counts_wire_attempts(
    database: Path,
) -> None:
    async def run() -> None:
        attempts = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                return httpx.Response(429, text="private provider overload")
            payload = json.loads(json.loads(request.content)["messages"][1]["content"])
            output = {
                "c": [
                    {"i": i, "k": c["k"][0], "a": c.get("h", []), "r": []}
                    for i, c in enumerate(payload["c"])
                ]
            }
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(output)}}
                    ]
                },
            )

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=GatewayRetry(base_delay_s=0),
            transport=httpx.MockTransport(respond),
        )
        async with fallback_client(database, model) as client:
            items = [
                {
                    "id": str(i),
                    "category_id": CARD["category_id"],
                    "title": f"Телефон {i}",
                    "description": CARD["description"],
                }
                for i in range(2)
            ]
            response = await client.post("/api/v1/extract/batch", json={"items": items})
            assert response.status_code == 200, response.text
            body = response.json()
            first, second = body["items"]
            assert first["status"] == second["status"] == "completed"
            assert first["result"]["fallback_reason"] == "model_rate_limited"
            assert second["result"]["fallback_reason"] is None
            assert body["summary"]["provider_requests"] == attempts == 3
            assert body["summary"]["succeeded"] == 2 and body["summary"]["failed"] == 0
            assert body["summary"]["input_tokens"] is None
            for item in body["items"]:
                result = item["result"]
                assert result["missing"]
                assert result["values"][0]["value"] == "синий"
                saved = (await client.get(f"/api/v1/runs/{item['run_id']}")).json()
                assert saved["status"] == "completed" and saved["result"] == result

    asyncio.run(run())


def test_invalid_primary_output_stays_a_failure_with_failed_history(database: Path) -> None:
    async def run() -> None:
        attempts = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": '{"c":[],"extra":true}'}}
                    ]
                },
            )

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=GatewayRetry(base_delay_s=0),
            transport=httpx.MockTransport(respond),
        )
        async with fallback_client(database, model) as client:
            response = await client.post("/api/v1/extract", json=CARD)
            assert response.status_code == 502 and attempts == 1
            assert response.json()["code"] == "invalid_model_output"
            saved = (await client.get("/api/v1/runs")).json()["items"][0]
            assert saved["status"] == "failed"
            assert (await client.get(f"/api/v1/runs/{saved['id']}")).json()["result"] is None

    asyncio.run(run())
