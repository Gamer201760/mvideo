import asyncio
import json
from pathlib import Path

import pytest

from app.domain.inference import Completion, StructuredRequest, Usage
from tests.integration.stand_client import client_for

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures/glasses-card.json").read_text())


class GlassesModel:
    def __init__(self, wrong_camera: bool = False, camera_only: bool = False) -> None:
        self.wrong_camera = wrong_camera
        self.camera_only = camera_only

    async def complete(self, request: StructuredRequest) -> Completion:
        answers = [
            {
                "f": p["attribute"],
                "v": "13"
                if self.wrong_camera and p["attribute"] == "Разрешение камеры"
                else p["value"],
                "u": p["unit"],
                "q": p["quote"],
                "r": 0,
            }
            for p in FIXTURE["proposals"]
            if not self.camera_only or p["attribute"] == "Разрешение камеры"
        ]
        return Completion(
            {
                "c": [
                    {
                        "i": 0,
                        "k": "Электроника / Носимые устройства / Умные очки с камерой",
                        "a": answers,
                        "r": [],
                    }
                ]
            },
            Usage("test-port"),
        )


@pytest.mark.parametrize(
    ("wrong_camera", "camera_only"), [(False, False), (True, False), (True, True)]
)
def test_glasses_quotes_category_completeness_and_history(
    database: Path, wrong_camera: bool, camera_only: bool
) -> None:
    expected_fields = 1 if camera_only else 11

    async def run() -> None:
        async with client_for(database, GlassesModel(wrong_camera, camera_only)) as client:
            response = await client.post(
                "/api/v1/extract",
                json={
                    "engine": "hybrid",
                    "title": FIXTURE["title"],
                    "description": FIXTURE["description"],
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert len(body["category"]["attributes"]) == expected_fields
            assert len(body["values"]) == expected_fields - int(wrong_camera)
            assert body["extra_values"] == []
            assert body["missing"] == (["Разрешение камеры"] if wrong_camera else [])
            assert len(body["rejections"]) == int(wrong_camera)
            for value in body["values"]:
                assert body["text"][value["start"] : value["end"]] == value["evidence"]
            run_id = (await client.get("/api/v1/runs")).json()["items"][0]["id"]
        async with client_for(database) as client:
            saved = (await client.get(f"/api/v1/runs/{run_id}")).json()["result"]
            assert saved == body
            category = next(
                c
                for c in (await client.get("/api/v1/stand")).json()["categories"]
                if c["category_id"] == body["category"]["category_id"]
            )
            assert len(category["attributes"]) == expected_fields

    asyncio.run(run())
