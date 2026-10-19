import asyncio
from pathlib import Path

import httpx
import pytest

from app.adapter.llm.gateway import GatewayModel
from app.settings import Settings
from tests.integration.stand_client import client_for


@pytest.mark.parametrize(
    "failure,status,code",
    [
        ("timeout", 504, "model_timeout"),
        ("connect", 503, "model_unavailable"),
        ("overload", 503, "model_rate_limited"),
        ("unavailable", 503, "model_unavailable"),
        ("invalid", 502, "invalid_model_output"),
        ("protocol", 502, "invalid_model_output"),
    ],
)
def test_gateway_failure_survives_transport_flow_api_and_failed_history(
    database: Path, failure: str, status: int, code: str
) -> None:
    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if failure == "timeout":
                raise httpx.ReadTimeout("private provider text", request=request)
            if failure == "connect":
                raise httpx.ConnectError("private provider text", request=request)
            if failure == "protocol":
                raise httpx.RemoteProtocolError("private provider text", request=request)
            upstream = {"overload": 429, "unavailable": 503}.get(failure, 200)
            return httpx.Response(upstream, text="private provider text")

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            "private-key",
            transport=httpx.MockTransport(respond),
        )
        card = {
            "engine": "hybrid",
            "category_id": 761,
            "title": "Смартфон",
            "description": "Цвет: синий",
        }
        async with client_for(
            database, model, settings=Settings(database=database, rules_first=False)
        ) as client:
            response = await client.post("/api/v1/extract", json=card)
            assert response.status_code == status
            assert response.json()["code"] == code
            assert "private" not in response.text and "gateway.example" not in response.text
            assert calls == 1
            runs = (await client.get("/api/v1/runs")).json()["items"]
            assert len(runs) == 1 and runs[0]["status"] == "failed"
            saved = await client.get(f"/api/v1/runs/{runs[0]['id']}")
            assert saved.json()["result"] is None

    asyncio.run(run())


def test_timeout_in_one_gateway_group_keeps_successful_groups_and_records_usage(
    database: Path,
) -> None:
    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ReadTimeout("private provider text", request=request)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": '{"c":[{"i":0,"k":0,"a":[],"r":[]}]}'},
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                },
            )

        model = GatewayModel(
            "https://gateway.example/v1", "default", transport=httpx.MockTransport(respond)
        )
        settings = Settings(database=database, rules_first=False, batch_size=1, concurrency=1)
        items = [{"id": str(i), "category_id": 761, "title": f"Смартфон {i}"} for i in range(2)]
        async with client_for(database, model, settings=settings) as client:
            response = await client.post("/api/v1/extract/batch", json={"items": items})
            assert response.status_code == 200
            body = response.json()
            assert [i["id"] for i in body["items"]] == ["0", "1"]
            assert body["items"][0]["error"]["code"] == "model_timeout"
            assert body["items"][1]["status"] == "completed"
            assert body["summary"]["succeeded"] == body["summary"]["failed"] == 1
            assert body["summary"]["provider_requests"] == calls == 2
            assert body["summary"]["input_tokens"] is None
            assert "private" not in response.text
            for item in body["items"]:
                saved = await client.get(f"/api/v1/runs/{item['run_id']}")
                assert saved.json()["status"] == item["status"]

    asyncio.run(run())
