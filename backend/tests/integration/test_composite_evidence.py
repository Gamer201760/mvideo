import asyncio
import json
from pathlib import Path

import pytest

from app.domain.attribute_flow import CatalogField
from app.domain.inference import Completion, StructuredRequest, Usage
from app.repository.sqlite.uow import SqliteUnitOfWork
from app.settings import Settings
from tests.integration.stand_client import client_for


class FlagsModel:
    async def complete(self, request: StructuredRequest) -> Completion:
        payload = json.loads(request.prompt)
        quote = payload["c"][0]["t"].split("\n", 1)[1].strip()
        answer = {"f": payload["f"].index("Жанр"), "v": "Драма, Триллер", "u": "", "q": quote}
        return Completion({"c": [{"i": 0, "k": 0, "a": [answer], "r": []}]}, Usage("test-port"))


@pytest.mark.parametrize(
    "second_flag,accepted", [("Да", True), ("Нет", False), ("неизвестно", False)]
)
def test_composite_validation_reaches_api_and_survives_saved_history(
    database: Path, second_flag: str, accepted: bool
) -> None:
    async def run() -> None:
        async with SqliteUnitOfWork(database) as unit:
            category = await unit.catalog.register(
                "Медиа / Проверочные фильмы",
                [CatalogField("Жанр", "categorical", "", ("Драма, Триллер",))],
            )
            await unit.commit()
        description = f"Драма: Да\nТриллер: {second_flag}"
        settings = Settings(database=database, rules_first=False)
        async with client_for(database, FlagsModel(), settings=settings) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "category_id": category.category_id,
                    "title": "Диск",
                    "description": description,
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            values = body["values"] + body["extra_values"]
            if accepted:
                assert len(values) == 1
                assert values[0]["value"] == "Драма, Триллер"
                assert values[0]["evidence"] == description
                assert body["missing"] == body["rejections"] == []
            else:
                assert values == []
                assert "Жанр" in body["missing"]
                assert body["rejections"][0]["attribute"] == "Жанр"
            run_id = (await client.get("/api/v1/runs")).json()["items"][0]["id"]
        async with client_for(database) as client:
            saved = (await client.get(f"/api/v1/runs/{run_id}")).json()
            assert saved["result"] == body

    asyncio.run(run())
