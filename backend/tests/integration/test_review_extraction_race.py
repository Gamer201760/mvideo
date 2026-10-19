import asyncio
from pathlib import Path

from app.domain.acceptance import AcceptancePolicy
from app.domain.attribute_flow import Extraction, FieldAnswer
from app.repository.sqlite.uow import SqliteUnitOfWork
from app.usecase.flow_reviews import FlowReviews
from app.usecase.stand_ports import CardInput
from tests.integration.stand_client import client_for


def test_inflight_extraction_cannot_reopen_a_rejected_review(database: Path) -> None:
    async def run() -> None:
        body = {
            "engine": "hybrid",
            "category_id": 761,
            "title": "Смартфон",
            "description": "Цвет: синий",
        }
        async with client_for(database) as client:
            initial = (await client.post("/api/v1/extract", json=body)).json()
            value = next(v for v in initial["values"] if v["attribute"] == "Цвет")
            assert (
                await client.post(f"/api/v1/review/{value['review_id']}", json={"action": "reject"})
            ).status_code == 200
            answer = FieldAnswer(
                "Цвет",
                "supported",
                "синий",
                "",
                value["evidence"],
                value["start"],
                value["end"],
                "синий",
                "",
            )
            result = Extraction(0, 761, (answer,), (), False)
            reviews = FlowReviews(lambda: SqliteUnitOfWork(database), AcceptancePolicy())
            card = CardInput(
                title="Смартфон", description="Цвет: синий", category_id=761, seller_params=()
            )
            ids, confirmed, automatic, suppressed = await reviews.record(card, result, ())
            assert ids == confirmed == {}
            assert not automatic and suppressed == {"Цвет"}
            saved = (await client.post("/api/v1/review/card", json=body)).json()
            assert (
                next(i for i in saved["items"] if i["id"] == value["review_id"])["status"]
                == "rejected"
            )

    asyncio.run(run())
