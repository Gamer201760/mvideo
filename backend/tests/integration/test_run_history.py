import asyncio
from pathlib import Path

from app.adapter.system.clock import SystemClock, UuidIds
from app.domain.inference import Completion, StructuredRequest
from app.repository.sqlite.uow import SqliteUnitOfWork
from app.usecase.review_card import ReviewCard
from app.usecase.run_history import RunHistory
from app.usecase.stand_ports import CardInput
from tests.integration.stand_client import ColorModel, client_for


def test_history_retains_input_result_and_failure_after_restart(database: Path) -> None:
    async def run() -> None:
        card = {
            "engine": "hybrid",
            "category_id": 761,
            "title": "Смартфон Север",
            "description": "Цвет: синий",
            "seller_params": [{"name": "Регион", "value": "Первый", "unit": None}],
        }
        async with client_for(database) as client:
            result = await client.post("/api/v1/extract", json=card)
            assert result.status_code == 200
            failed = await client.post(
                "/api/v1/extract", json={**card, "engine": "rules", "category_id": -1}
            )
            assert failed.status_code == 422
        async with client_for(database) as client:
            page = (await client.get("/api/v1/runs?limit=1")).json()
            assert page["total"] == 2
            assert page["items"][0]["status"] == "failed"
            assert page["items"][0]["finished_at"] is not None
            failure = (await client.get(f"/api/v1/runs/{page['items'][0]['id']}")).json()
            assert failure["result"] is None
            page = (await client.get("/api/v1/runs?offset=1&limit=1")).json()
            saved = page["items"][0]
            assert saved["status"] == "completed"
            detail = (await client.get(f"/api/v1/runs/{saved['id']}")).json()
            assert detail["input"] == card
            assert detail["result"] == result.json()
            assert (await client.get("/api/v1/runs/missing")).status_code == 404
            assert (await client.get("/api/v1/runs?limit=101")).status_code == 422
            assert (await client.get("/api/v1/runs?offset=-1")).status_code == 422

    asyncio.run(run())


def test_history_shows_active_requests(database: Path) -> None:
    async def run() -> None:
        started, release = asyncio.Event(), asyncio.Event()

        class WaitingModel(ColorModel):
            async def complete(self, request: StructuredRequest) -> Completion:
                started.set()
                await release.wait()
                return await super().complete(request)

        async with client_for(database, WaitingModel()) as client:
            task = asyncio.create_task(
                client.post(
                    "/api/v1/extract",
                    json={
                        "engine": "hybrid",
                        "category_id": 761,
                        "title": "Смартфон Север",
                        "description": "Цвет: синий",
                    },
                )
            )
            await asyncio.wait_for(started.wait(), timeout=5)
            try:
                page = (await client.get("/api/v1/runs")).json()
                active = page["items"][0]
                assert active["status"] == "running"
                assert active["finished_at"] is None
            finally:
                release.set()
            assert (await task).status_code == 200
            detail = (await client.get(f"/api/v1/runs/{active['id']}")).json()
            assert detail["status"] == "completed"
            assert detail["result"] is not None

    asyncio.run(run())


def test_startup_recovers_unfinished_requests(database: Path) -> None:
    async def run() -> None:
        history = RunHistory(lambda: SqliteUnitOfWork(database), SystemClock(), UuidIds())
        identifier = await history.begin(
            ReviewCard(
                CardInput(title="Unfinished", description="", category_id=None, seller_params=()),
                "rules",
            )
        )
        async with client_for(database) as client:
            detail = (await client.get(f"/api/v1/runs/{identifier}")).json()
            assert detail["status"] == "interrupted"
            assert detail["result"] is None
            assert detail["input"]["title"] == "Unfinished"

    asyncio.run(run())
