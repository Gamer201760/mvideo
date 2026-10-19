import asyncio
import json
from pathlib import Path

from app.domain.inference import Completion, StructuredRequest, Usage
from tests.integration.stand_client import client_for


class UnexpectedCall:
    async def complete(self, request: StructuredRequest) -> Completion:
        raise AssertionError("A fully parsed card must not invoke the model")


def test_complete_card_uses_rules_and_keeps_quotes_and_reviews(database: Path) -> None:
    async def run() -> None:
        async with client_for(database, UnexpectedCall()) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "category_id": 761,
                    "title": "Смартфон Север S1",
                    "description": (
                        "Бренд: Север\nМодель: S1\nВстроенная память (ROM): 128 ГБ\n"
                        "Диагональ: 6.6 дюйма\nЕмкость аккумулятора: 5000 мАч\nЦвет: черный"
                    ),
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert len(body["values"]) == 6
            assert body["missing"] == []
            for value in body["values"]:
                assert body["text"][value["start"] : value["end"]] == value["evidence"]
                assert value["review_id"] is not None
                assert value["acceptance"] in {"automatic", "review"}
                assert value["source"] != "review"
            assert any(value["acceptance"] == "automatic" for value in body["values"])

    asyncio.run(run())


class ModelWithMaterial:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: StructuredRequest) -> Completion:
        self.calls += 1
        payload = json.loads(request.prompt)
        card = payload["c"][0]
        return Completion(
            {
                "c": [
                    {
                        "i": 0,
                        "k": card["k"][0],
                        "r": [],
                        "a": [
                            *card["h"],
                            {"f": "Материал", "v": "пластик", "u": "", "q": "Материал: пластик"},
                        ],
                    }
                ]
            },
            Usage("test"),
        )


def test_extra_description_field_is_preserved_by_calling_model(database: Path) -> None:
    async def run() -> None:
        model = ModelWithMaterial()
        async with client_for(database, model) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "category_id": 761,
                    "title": "Смартфон Север S1",
                    "description": (
                        "Бренд: Север\nМодель: S1\nВстроенная память (ROM): 128 ГБ\n"
                        "Диагональ: 6.6 дюйма\nЕмкость аккумулятора: 5000 мАч\nЦвет: черный\n"
                        "Материал: пластик"
                    ),
                },
            )
            assert response.status_code == 200
            assert model.calls == 1
            body = response.json()
            assert len(body["values"]) == 6
            material = next(v for v in body["extra_values"] if v["attribute"] == "Материал")
            assert material["value"] == "пластик"
            assert material["evidence"] == "Материал: пластик"

    asyncio.run(run())
