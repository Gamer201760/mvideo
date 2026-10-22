import asyncio
import json
from pathlib import Path

import pytest

from app.domain.inference import Completion, StructuredRequest, Usage
from tests.integration.stand_client import client_for


class GroundedPhoneModel:
    def __init__(self, named: bool) -> None:
        self.named = named

    async def complete(self, request: StructuredRequest) -> Completion:
        fields = json.loads(request.prompt)["f"]
        return Completion(
            {
                "c": [
                    {
                        "i": 0,
                        "k": 0,
                        "r": [],
                        "a": [
                            {
                                "f": "Модель" if self.named else fields.index("Модель"),
                                "v": "L1",
                                "u": "",
                                "q": "L1",
                                "r": 0,
                            },
                            {
                                "f": "Цвет" if self.named else fields.index("Цвет"),
                                "v": "синий",
                                "u": "",
                                "q": "синего",
                                "r": 0,
                            },
                            {
                                "f": "Встроенная память (ROM)"
                                if self.named
                                else fields.index("Встроенная память (ROM)"),
                                "v": "128 ГБ",
                                "u": "ГБ",
                                "q": "128 ГБ",
                                "r": 0,
                            },
                        ],
                    }
                ]
            },
            Usage("test-port"),
        )


@pytest.mark.parametrize("named", [False, True])
def test_grounded_phone_fields_survive_model_representation_and_history(
    database: Path, named: bool
) -> None:
    async def run() -> None:
        async with client_for(database, GroundedPhoneModel(named)) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "category_id": 761,
                    "title": "Смартфон Ладога L1",
                    "description": "Корпус синего цвета. Встроенная память составляет 128 ГБ. Емкость аккумулятора не указана.",
                },
            )
            assert response.status_code == 200
            result = response.json()
            assert {value["attribute"] for value in result["values"]} == {
                "Модель",
                "Цвет",
                "Встроенная память (ROM)",
            }
            assert result["extra_values"] == [] and result["rejections"] == []
            assert "Емкость аккумулятора" in result["missing"]
            assert (
                "Цвет" not in result["missing"]
                and "Встроенная память (ROM)" not in result["missing"]
            )
            for value in result["values"]:
                assert result["text"][value["start"] : value["end"]] == value["evidence"]
            run_id = (await client.get("/api/v1/runs")).json()["items"][0]["id"]
        async with client_for(database) as client:
            saved = (await client.get(f"/api/v1/runs/{run_id}")).json()
            assert saved["status"] == "completed" and saved["result"] == result

    asyncio.run(run())
