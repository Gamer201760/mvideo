import asyncio
from pathlib import Path

import httpx
import pytest

from app.adapter.llm.gateway import GatewayModel
from app.adapter.llm.gateway_retry import GatewayRetry
from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.inference import Completion, StructuredRequest, Usage
from tests.integration.stand_client import client_for
from tests.integration.test_gateway_fallback import fallback_client


@pytest.mark.parametrize("fallback", [False, True])
def test_inline_phone_fields_remain_separate_through_local_rules_and_fallback_api(
    database: Path, fallback: bool
) -> None:
    async def run() -> None:
        primary = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=GatewayRetry(base_delay_s=0),
            transport=httpx.MockTransport(lambda _: httpx.Response(503)),
        )
        manager = (
            fallback_client(database, primary)
            if fallback
            else client_for(database, LocalRulesModel())
        )
        async with manager as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "category_id": 761,
                    "title": "Смартфон Fallback ru light 375",
                    "description": "Цвет: синий. Встроенная память: 128 ГБ.",
                },
            )
            assert response.status_code == 200
            result = response.json()
            values = {value["attribute"]: value for value in result["values"]}
            assert set(values) == {"Цвет", "Встроенная память (ROM)"}
            assert values["Цвет"]["value"] == values["Цвет"]["evidence"] == "синий"
            assert values["Встроенная память (ROM)"]["value"].casefold() == "128 гб"
            assert values["Встроенная память (ROM)"]["evidence"] == "128 ГБ"
            assert result["rejections"] == []
            assert result["fallback_reason"] == ("model_unavailable" if fallback else None)
            for value in values.values():
                assert result["text"][value["start"] : value["end"]] == value["evidence"]
            run_id = (await client.get("/api/v1/runs")).json()["items"][0]["id"]
        await primary.aclose()
        async with client_for(database) as client:
            assert (await client.get(f"/api/v1/runs/{run_id}")).json()["result"] == result

    asyncio.run(run())


def test_even_a_model_proposal_cannot_auto_accept_the_compound_color(database: Path) -> None:
    class CompoundColor:
        async def complete(self, request: StructuredRequest) -> Completion:
            value = "синий. Встроенная память: 128 ГБ."
            return Completion(
                {
                    "c": [
                        {
                            "i": 0,
                            "k": 0,
                            "r": [],
                            "a": [
                                {"f": "Цвет", "v": value, "u": "", "q": value, "r": 0},
                            ],
                        }
                    ]
                },
                Usage("test-port"),
            )

    async def run() -> None:
        async with client_for(database, CompoundColor()) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "category_id": 761,
                    "title": "Смартфон",
                    "description": "Цвет: синий. Встроенная память: 128 ГБ.",
                },
            )
            assert response.status_code == 200
            result = response.json()
            assert result["values"] == result["extra_values"] == []
            assert result["rejections"][0]["reason"] == "field_mismatch"

    asyncio.run(run())
