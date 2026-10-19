import asyncio
import json
from pathlib import Path

from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.attribute_flow import CatalogField
from app.domain.inference import Completion, StructuredRequest, Usage
from app.repository.sqlite.uow import SqliteUnitOfWork
from app.settings import Settings
from tests.integration.stand_client import NewCategoryModel, client_for


def test_new_category_is_available_to_both_engines_immediately_and_after_restart(
    database: Path,
) -> None:
    async def run() -> None:
        card = {
            "engine": "hybrid",
            "title": "Беспилотник Север",
            "description": "Дальность полета: 12 км",
        }
        async with client_for(database, NewCategoryModel()) as client:
            count = (await client.get("/api/v1/ready")).json()["categories"]
            created = (await client.post("/api/v1/extract", json=card)).json()
            identifier = created["category"]["category_id"]
            assert identifier < 0
            rules = await client.post(
                "/api/v1/extract", json={**card, "category_id": identifier, "engine": "rules"}
            )
            assert rules.status_code == 200, rules.text
            assert rules.json()["values"][0]["value"] == "12 км"
            assert rules.json()["missing"] == []
            hybrid = await client.post("/api/v1/extract", json={**card, "category_id": identifier})
            assert hybrid.status_code == 200
            assert hybrid.json()["category"]["category_id"] == identifier
            assert (await client.get("/api/v1/ready")).json()["categories"] == count + 1
        async with client_for(database) as client:
            for engine in ["rules", "hybrid"]:
                result = await client.post(
                    "/api/v1/extract", json={**card, "engine": engine, "category_id": identifier}
                )
                assert result.status_code == 200
                assert any(
                    v["attribute"] == "Дальность полета" and v["value"] == "12 км"
                    for v in result.json()["values"]
                )
            info = (await client.get("/api/v1/stand")).json()
            assert len([c for c in info["categories"] if c["category_id"] == identifier]) == 1

    asyncio.run(run())


class AppendFieldModel(LocalRulesModel):
    async def complete(self, request: StructuredRequest) -> Completion:
        payload = json.loads(request.prompt)
        if "Особое поле" in payload["f"]:
            return await super().complete(request)
        return Completion(
            {
                "c": [
                    {
                        "i": 0,
                        "k": "Электроника / Телефоны / Смартфоны",
                        "r": [],
                        "a": [
                            {
                                "f": "Особое поле",
                                "v": "альфа",
                                "u": "",
                                "q": "Особое поле: альфа",
                                "r": 0,
                            }
                        ],
                    }
                ]
            },
            Usage("test-port"),
        )


def test_appended_field_updates_existing_category_in_all_views_without_restart(
    database: Path,
) -> None:
    async def run() -> None:
        card = {
            "engine": "hybrid",
            "title": "Смартфон",
            "category_id": 761,
            "description": "Особое поле: альфа",
        }
        async with client_for(
            database, AppendFieldModel(), settings=Settings(database=database, rules_first=False)
        ) as client:
            before = await client.post("/api/v1/extract", json={**card, "engine": "rules"})
            assert before.status_code == 200
            assert not any(v["attribute"] == "Особое поле" for v in before.json()["values"])
            initial = await client.post("/api/v1/extract", json=card)
            assert initial.status_code == 200, initial.text
            for engine in ["rules", "hybrid"]:
                result = await client.post("/api/v1/extract", json={**card, "engine": engine})
                assert result.status_code == 200, result.text
                assert any(
                    v["attribute"] == "Особое поле" and v["value"] == "альфа"
                    for v in result.json()["values"]
                )
            schema = next(
                c
                for c in (await client.get("/api/v1/stand")).json()["categories"]
                if c["category_id"] == 761
            )
            assert schema["attributes"].count("Особое поле") == 1

    asyncio.run(run())


def test_rules_keep_category_specific_units_and_dictionaries_under_concurrent_requests(
    database: Path,
) -> None:
    async def run() -> None:
        async with SqliteUnitOfWork(database) as unit:
            length = await unit.catalog.register(
                "Измерения / Длина", [CatalogField("Размер", "numeric", "см")]
            )
            mass = await unit.catalog.register(
                "Измерения / Масса", [CatalogField("Размер", "numeric", "кг")]
            )
            await unit.commit()
        async with client_for(database) as client:

            async def extract(identifier: int, value: str) -> None:
                response = await client.post(
                    "/api/v1/extract",
                    json={
                        "engine": "rules",
                        "category_id": identifier,
                        "title": "Измерение",
                        "description": f"Размер: {value}",
                    },
                )
                assert response.status_code == 200, response.text
                assert response.json()["values"][0]["value"] == value

            await asyncio.gather(
                *(
                    extract(c.category_id, value)
                    for _ in range(4)
                    for c, value in [(length, "10 см"), (mass, "2 кг")]
                )
            )

    asyncio.run(run())
