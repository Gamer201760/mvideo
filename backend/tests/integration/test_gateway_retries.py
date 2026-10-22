import asyncio
import json
from pathlib import Path

import httpx

from app.adapter.llm.gateway import GatewayModel
from app.adapter.llm.gateway_retry import GatewayRetry
from app.settings import Settings
from tests.integration.stand_client import client_for


def test_batch_retry_exhaustion_preserves_success_history_and_actual_wire_count(
    database: Path,
) -> None:
    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, text="private upstream details")
            if calls > 2:
                return httpx.Response(429, text="private upstream details")
            wire = json.loads(request.content)
            data = json.loads(wire["messages"][1]["content"])
            output = {
                "c": [
                    {
                        "i": 0,
                        "k": 0,
                        "r": [],
                        "a": [
                            {
                                "f": data["f"].index("Цвет"),
                                "v": "синий",
                                "u": "",
                                "q": "Цвет: синий",
                                "r": 0,
                            }
                        ],
                    }
                ]
            }
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(output)}}
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                },
            )

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            "private-key",
            retry=GatewayRetry(base_delay_s=0),
            transport=httpx.MockTransport(respond),
        )
        settings = Settings(database=database, rules_first=False, batch_size=1, concurrency=1)
        try:
            async with client_for(database, model, settings=settings) as client:
                response = await client.post(
                    "/api/v1/extract/batch",
                    json={
                        "items": [
                            {
                                "id": str(i),
                                "title": f"Смартфон {i}",
                                "description": "Цвет: синий",
                                "category_id": 761,
                            }
                            for i in range(2)
                        ]
                    },
                )
                assert response.status_code == 200, response.text
                body = response.json()
                first, second = body["items"]
                assert first["status"] == "completed"
                assert first["result"]["values"][0]["value"] == "синий"
                assert second["status"] == "failed" and second["result"] is None
                assert second["error"]["code"] == "model_rate_limited"
                assert body["summary"]["provider_requests"] == calls == 4
                assert body["summary"]["provider_cards"] == 2
                assert body["summary"]["succeeded"] == body["summary"]["failed"] == 1
                assert body["summary"]["input_tokens"] is None
                assert body["summary"]["output_tokens"] is None
                assert "private" not in response.text
                for item in body["items"]:
                    saved = (await client.get(f"/api/v1/runs/{item['run_id']}")).json()
                    assert saved["status"] == item["status"]
                    assert saved["result"] == item["result"]
        finally:
            await model.aclose()

    asyncio.run(run())
