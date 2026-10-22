import asyncio
import sqlite3
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.adapter.llm.local_rules import LocalRulesModel
from app.adapter.system.clock import SystemClock, UuidIds
from app.domain.errors import StorageBusy, StorageUnavailable
from app.domain.inference import Completion, StructuredRequest
from app.domain.review import ReviewItemNotFound
from app.main import create_app
from app.repository.sqlite.facades import AliasRepository, ReviewRepository
from app.repository.sqlite.readiness import SqliteReadiness
from app.repository.sqlite.uow import SqliteReadUnitOfWork, SqliteUnitOfWork
from app.settings import Settings
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.persistent_review import PersistentReview
from app.usecase.readiness import Readiness
from app.usecase.review_card import ReviewCard
from app.usecase.review_query import ReviewQuery
from app.usecase.run_history import RunHistory
from app.usecase.stand_ports import CardInput
from tests.integration.stand_client import client_for


class NoDispatchModel(LocalRulesModel):
    async def complete(self, request: StructuredRequest) -> Completion:
        raise AssertionError("Readiness dispatched a model request")


def test_wal_readers_keep_committed_snapshot_during_writer(database: Path) -> None:
    async def run() -> None:
        read: UnitOfWorkFactory = lambda: SqliteReadUnitOfWork(database, timeout_s=0.01)
        write: UnitOfWorkFactory = lambda: SqliteUnitOfWork(database, timeout_s=0.01)
        history = RunHistory(write, SystemClock(), UuidIds(), read_store=read)
        reviews = ReviewRepository(write, read)
        aliases = AliasRepository(write, read)
        identifier = await history.begin(
            ReviewCard(
                CardInput(title="Existing", description="", category_id=None, seller_params=()),
                "rules",
            )
        )
        async with write() as writer:
            await writer.cards.save(
                "uncommitted",
                ReviewCard(
                    CardInput(title="Pending", description="", category_id=None, seller_params=()),
                    "rules",
                ),
            )

            async def inspect() -> None:
                assert (await reviews.page(ReviewQuery())).total == 0
                assert await reviews.get("missing") is None
                assert await aliases.all() == []
                assert (await history.page(0, 10))[1] == 1
                assert (await history.get(identifier)).status == "running"
                with pytest.raises(ReviewItemNotFound):
                    await PersistentReview(write, read).card("missing")
                await Readiness(SqliteReadiness(read)).check()
                async with read() as reader:
                    assert await reader.catalog.all()
                    assert await reader.cards.get("uncommitted") is None

            await asyncio.wait_for(inspect(), timeout=1)
        async with read() as reader:
            assert await reader.cards.get("uncommitted") is None

    asyncio.run(run())


def test_batch_rolls_back_failed_card_and_preserves_first_result(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_second BEFORE INSERT ON reviews "
            "WHEN json_extract(NEW.payload,'$.title')='Second' "
            "BEGIN SELECT RAISE(ABORT,'private SQL failure'); END"
        )

    async def run() -> None:
        async with client_for(database) as client:
            response = await client.post(
                "/api/v1/extract/batch",
                json={
                    "items": [
                        {
                            "id": title,
                            "title": title,
                            "description": "Цвет: синий",
                            "category_id": 761,
                        }
                        for title in ("First", "Second")
                    ]
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            first, second = body["items"]
            assert body["summary"]["succeeded"] == body["summary"]["failed"] == 1
            assert first["status"] == "completed" and first["result"] is not None
            assert second["status"] == "failed" and second["result"] is None
            assert second["error"]["code"] == "storage_failure"
            assert "private SQL failure" not in response.text
            for item in body["items"]:
                detail = (await client.get(f"/api/v1/runs/{item['run_id']}")).json()
                assert detail["status"] == item["status"]
                assert detail["result"] == item["result"]
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM review_cards").fetchone() == (1,)
            assert connection.execute(
                "SELECT DISTINCT json_extract(payload,'$.title') FROM reviews"
            ).fetchall() == [("First",)]

    asyncio.run(run())


def test_history_save_failure_does_not_discard_completed_batch_item(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_second_history BEFORE UPDATE ON extraction_runs "
            "WHEN json_extract(NEW.input_json,'$.title')='Second' AND NEW.status='completed' "
            "BEGIN SELECT RAISE(ABORT,'private history failure'); END"
        )

    async def run() -> None:
        async with client_for(database) as client:
            response = await client.post(
                "/api/v1/extract/batch",
                json={
                    "items": [
                        {
                            "id": title,
                            "title": title,
                            "description": "Цвет: синий",
                            "category_id": 761,
                        }
                        for title in ("First", "Second")
                    ]
                },
            )
            assert response.status_code == 200
            first, second = response.json()["items"]
            assert first["status"] == "completed"
            assert second["error"]["code"] == "storage_failure"
            detail = (await client.get(f"/api/v1/runs/{first['run_id']}")).json()
            assert detail["status"] == "completed" and detail["result"] == first["result"]

    asyncio.run(run())


@pytest.mark.parametrize(
    "table", ["categories", "reviews", "aliases", "review_cards", "extraction_runs"]
)
def test_readiness_checks_required_tables_without_model(database: Path, table: str) -> None:
    async def run() -> None:
        app = create_app(Settings(database=database), model=NoDispatchModel())
        async with app.router.lifespan_context(app):
            app.state.readiness = Readiness(SqliteReadiness(lambda: SqliteReadUnitOfWork(database)))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/api/v1/ready")).status_code == 200
                with sqlite3.connect(database) as connection:
                    connection.execute(f'DROP TABLE "{table}"')
                response = await client.get("/api/v1/ready")
                assert response.status_code == 503
                assert response.json() == {
                    "code": "storage_unavailable",
                    "message": "Storage is unavailable; retry later",
                }
                assert (await client.get("/api/v1/health")).status_code == 200

    asyncio.run(run())


def test_busy_storage_has_safe_retryable_http_error(database: Path) -> None:
    async def run() -> None:
        app = create_app(Settings(database=database))
        async with app.router.lifespan_context(app):
            app.state.stand = replace(
                app.state.stand,
                history=RunHistory(
                    lambda: SqliteUnitOfWork(database, timeout_s=0.01), SystemClock(), UuidIds()
                ),
            )
            async with (
                SqliteUnitOfWork(database),
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client,
            ):
                response = await client.post(
                    "/api/v1/extract",
                    json={"title": "Locked", "description": "Цвет: синий", "category_id": 761},
                )
                assert response.status_code == 503
                assert response.json() == {
                    "code": "storage_busy",
                    "message": "Storage is busy; retry later",
                }
                with pytest.raises(StorageBusy):
                    async with SqliteUnitOfWork(database, timeout_s=0.01):
                        pytest.fail("Concurrent writer acquired the lock")

    asyncio.run(run())


def test_missing_read_database_is_unavailable_without_creating_file(tmp_path: Path) -> None:
    database = tmp_path / "absent.db"

    async def run() -> None:
        with pytest.raises(StorageUnavailable):
            await Readiness(SqliteReadiness(lambda: SqliteReadUnitOfWork(database))).check()

    asyncio.run(run())
    assert not database.exists()
