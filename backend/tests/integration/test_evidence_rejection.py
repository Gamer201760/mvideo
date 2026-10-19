import asyncio
import json
from pathlib import Path

import pytest

from app.domain.inference import Completion, StructuredRequest, Usage
from app.repository.sqlite.uow import SqliteUnitOfWork
from tests.integration.stand_client import client_for


class ContradictingModel:
    def __init__(self, attribute: str, value: str, quote: str, unit: str = "") -> None:
        self.attribute, self.value, self.quote, self.unit = attribute, value, quote, unit

    async def complete(self, request: StructuredRequest) -> Completion:
        fields = json.loads(request.prompt)["f"]
        field = fields.index(self.attribute) if self.attribute in fields else self.attribute
        return Completion(
            {
                "c": [
                    {
                        "i": 0,
                        "k": 0,
                        "a": [{"f": field, "v": self.value, "u": self.unit, "q": self.quote}],
                        "r": [],
                    }
                ]
            },
            Usage("test-port"),
        )


@pytest.mark.parametrize(
    ("attribute", "value", "unit", "description", "quote"),
    [
        ("Цвет", "синий", "", "Цвет: красный", "Цвет: красный"),
        ("Бренд", "красный", "", "Цвет красный", "красный"),
        ("Бренд", "красный", "", "Цвет красный", "Цвет красный"),
        ("Модель", "ABC", "", "Модель не ABC", "ABC"),
        ("Модель", "ABC", "", "Модель не ABC", "Модель не ABC"),
        ("Модель", "ABC", "", "Модель: не ABC", "ABC"),
        ("NFC", "Да", "", "NFC не поддерживается", "поддерживается"),
        ("Вес", "500", "кг", "Вес: 500 г", "500 г"),
        ("Время работы", "20", "ч", "Время работы: до 20 ч", "20"),
        ("Вес", "500", "г", "Вес упаковки: 500 г", "500 г"),
        ("Материал", "сталь", "", "Корпус пластиковый", "Корпус пластиковый"),
        ("NFC", "Да", "", "Bluetooth: Да", "Bluetooth: Да"),
        ("NFC", "Нет", "", "Bluetooth отсутствует", "Bluetooth отсутствует"),
        ("Вес", "5", "кг", "Вес: 1 кг; Нагрузка: 5 кг", "Нагрузка: 5 кг"),
        ("Температура", "5", "°с", "Температура: −5 °с", "5 °с"),
        ("Вес", "500", "г", "Другая модель, вес 500 г", "500 г"),
        ("Вес", "5", "кг", "Нагрузка 5 кг", "5 кг"),
        ("Цвет", "Да", "", "Цвет: Да", "Да"),
        ("Время работы", "20–10 ч", "", "Время работы: 20–10 ч", "20–10 ч"),
        ("Модель", "AB 12", "", "Модель: AB-12", "AB-12"),
        (
            "NFC",
            "Да",
            "",
            "NFC поддерживается только с дополнительным модулем",
            "NFC поддерживается",
        ),
    ],
)
def test_rejected_model_values_are_not_returned_or_queued(
    database: Path, attribute: str, value: str, unit: str, description: str, quote: str
) -> None:
    async def run() -> None:
        model = ContradictingModel(attribute, value, quote, unit)
        async with client_for(database, model) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "category_id": 761,
                    "title": "Смартфон",
                    "description": description,
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["values"] == body["extra_values"] == []
            assert len(body["rejections"]) == 1
            rejection = body["rejections"][0]
            assert rejection["attribute"] == attribute
            assert rejection["evidence"] == quote
            assert rejection["reason"]
            if attribute == "Цвет":
                assert attribute in body["missing"]
            assert (await client.get("/api/v1/review")).json()["items"] == []
        async with SqliteUnitOfWork(database) as transaction:
            assert await transaction.aliases.all() == []

    asyncio.run(run())


@pytest.mark.parametrize(
    ("attribute", "value", "unit", "title", "description", "quote"),
    [
        ("Цвет", "красный", "", "Телефон", "Без NFC красный корпус", "красный"),
        (
            "NFC",
            "Да",
            "",
            "Телефон",
            "NFC поддерживается и Bluetooth отсутствует",
            "NFC поддерживается",
        ),
        ("Вес", "500", "г", "Телефон B", "У модели B вес 500 г", "500 г"),
        ("Вес", "200", "г", "Телефон", "Вес 200 г, вес упаковки 500 г", "200 г"),
        ("Модель", "AB-12", "", "Телефон", "Модель: AB-12", "AB-12"),
    ],
)
def test_valid_independent_statements_reach_the_response(
    database: Path, attribute: str, value: str, unit: str, title: str, description: str, quote: str
) -> None:
    async def run() -> None:
        model = ContradictingModel(attribute, value, quote, unit)
        async with client_for(database, model) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "category_id": 761,
                    "title": title,
                    "description": description,
                },
            )
            assert response.status_code == 200
            body = response.json()
            values = body["values"] + body["extra_values"]
            found = next(item for item in values if item["attribute"] == attribute)
            assert found["value"] == f"{value} {unit}".strip()
            assert found["evidence"] == quote
            assert body["rejections"] == []

    asyncio.run(run())
