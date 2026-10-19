import asyncio
import json
from pathlib import Path

import pytest

from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.errors import ModelFailure
from app.domain.inference import Completion, StructuredRequest
from app.settings import Settings
from tests.integration.stand_client import client_for


class RecordingModel(LocalRulesModel):
    def __init__(self) -> None:
        self.requests: list[StructuredRequest] = []

    async def complete(self, request: StructuredRequest) -> Completion:
        self.requests.append(request)
        payload = json.loads(request.prompt)
        if any("fail-group" in card["t"] for card in payload["c"]):
            raise ModelFailure("private upstream details")
        result = await super().complete(request)
        result.output["c"].reverse()
        return result


def card(index: int, color: str = "синий") -> dict[str, object]:
    return {
        "id": f"sku-{index}",
        "title": f"Смартфон packet-{index}",
        "category_id": 761,
        "description": f"Цвет: {color}",
    }


def test_batch_mapping_statistics_history_and_persistence(database: Path) -> None:
    async def run() -> None:
        model = RecordingModel()
        cards = [card(i, "синий" if i % 2 else "черный") for i in range(10)]
        async with client_for(database, model) as client:
            response = await client.post("/api/v1/extract/batch", json={"items": cards})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["summary"]["succeeded"] == 10
            assert body["summary"]["failed"] == 0
            assert body["summary"]["provider_requests"] == len(model.requests) == 3
            assert body["summary"]["provider_cards"] == 10
            assert body["summary"]["input_tokens"] is None
            assert body["summary"]["provider"] == "local_rules"
            assert [row["id"] for row in body["items"]] == [row["id"] for row in cards]
            for index, row in enumerate(body["items"]):
                assert row["status"] == "completed" and row["error"] is None
                color = row["result"]["values"][0]
                assert color["value"] == ("синий" if index % 2 else "черный")
                text = row["result"]["text"]
                assert text[color["start"] : color["end"]] == color["evidence"]
            identifier = body["items"][0]["run_id"]
        async with client_for(database) as client:
            history = await client.get(f"/api/v1/runs/{identifier}")
            assert history.status_code == 200
            assert history.json()["input"]["title"] == cards[0]["title"]
            assert history.json()["status"] == "completed"

    asyncio.run(run())


def test_failed_group_does_not_discard_other_groups_or_leak_provider_error(database: Path) -> None:
    async def run() -> None:
        model = RecordingModel()
        cards = [card(i) for i in range(8)]
        cards[0]["title"] = "Смартфон fail-group"
        async with client_for(database, model) as client:
            response = await client.post("/api/v1/extract/batch", json={"items": cards})
            assert response.status_code == 200
            body = response.json()
            assert body["summary"]["succeeded"] == body["summary"]["failed"] == 4
            assert len(model.requests) == 2
            assert "private upstream details" not in response.text
            assert all(row["result"] is None for row in body["items"][:4])
            assert all(row["result"] is not None for row in body["items"][4:])
            for row in body["items"]:
                saved = await client.get(f"/api/v1/runs/{row['run_id']}")
                assert saved.json()["status"] == row["status"]

    asyncio.run(run())


def test_unknown_category_is_an_item_error_before_model_dispatch(database: Path) -> None:
    async def run() -> None:
        model = RecordingModel()
        bad = {**card(1), "category_id": 9999999}
        async with client_for(database, model) as client:
            response = await client.post("/api/v1/extract/batch", json={"items": [bad, card(2)]})
            assert response.status_code == 200
            body = response.json()
            assert body["items"][0]["error"]["code"] == "unknown_category"
            assert body["items"][1]["status"] == "completed"
            assert body["summary"]["provider_cards"] == 1
            assert body["summary"]["rules_only_cards"] == 0

    asyncio.run(run())


@pytest.mark.parametrize(
    "items",
    [
        [],
        [card(0), card(0)],
        [card(i) for i in range(101)],
        [{**card(i), "description": "X" * 20000} for i in range(13)],
    ],
)
def test_invalid_batch_is_rejected_without_inference_or_history(
    database: Path, items: list[dict[str, object]]
) -> None:
    async def run() -> None:
        model = RecordingModel()
        async with client_for(database, model) as client:
            response = await client.post("/api/v1/extract/batch", json={"items": items})
            assert response.status_code == 422
            assert model.requests == []
            assert (await client.get("/api/v1/runs")).json()["total"] == 0

    asyncio.run(run())


def test_batch_uses_configured_character_limit_without_truncation(database: Path) -> None:
    async def run() -> None:
        model = RecordingModel()
        settings = Settings(database=database, max_batch_chars=1000)
        async with client_for(database, model, settings=settings) as client:
            response = await client.post(
                "/api/v1/extract/batch",
                json={"items": [{**card(1), "description": "X" * 3000}, card(2)]},
            )
            body = response.json()
            assert body["items"][0]["error"]["code"] == "model_input_too_large"
            assert all(len(request.prompt) <= 1000 for request in model.requests)

    asyncio.run(run())
