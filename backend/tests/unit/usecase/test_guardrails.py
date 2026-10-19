import asyncio
from typing import Any

import httpx
import pytest

from app.controller.stand.dependencies import history_usecase
from app.controller.stand.router import extract_usecase, flow_usecase
from app.controller.stand.schemas import ExtractRequest, SellerParamSchema
from app.domain.attribute_flow import FlowCard
from app.domain.errors import ModelFailure
from app.domain.inference import Completion, StructuredRequest, Usage
from app.domain.lexicon import Lexicon
from app.domain.profile import Kind
from app.main import create_app
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.baseline_ports import RequiredRecord
from app.usecase.extraction import RequiredAttributes


class BlockingModel:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, request: StructuredRequest) -> Completion:
        self.started.set()
        await self.release.wait()
        return Completion({"c": [{"i": 0, "k": None, "a": [], "r": []}]}, Usage("test-port"))


@pytest.mark.parametrize("cancelled_index", [0, 3])
def test_overload_is_bounded_and_cancellation_frees_capacity(cancelled_index: int) -> None:
    async def run() -> None:
        model = BlockingModel()
        flow = AttributeFlow(model, FlowConfig(concurrency=1, timeout_s=3))
        tasks = [asyncio.create_task(flow.run([FlowCard(i, "Card", ())])) for i in range(8)]
        try:
            await asyncio.wait_for(model.started.wait(), 1)
            await asyncio.sleep(0)
            rejected = await flow.run([FlowCard(8, "Card", ())])
            assert rejected[0].final == ()
            assert rejected[0].calls[0].error == "capacity"
            tasks[cancelled_index].cancel()
            with pytest.raises(asyncio.CancelledError):
                await tasks[cancelled_index]
            tasks.append(asyncio.create_task(flow.run([FlowCard(9, "Card", ())])))
            await asyncio.sleep(0)
            model.release.set()
            remaining = [task for i, task in enumerate(tasks) if i != cancelled_index]
            results = await asyncio.wait_for(asyncio.gather(*remaining), 1)
            assert all(result[0].final and result[0].calls[0].error is None for result in results)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run())


def test_queue_wait_counts_towards_request_timeout() -> None:
    async def run() -> None:
        model = BlockingModel()
        flow = AttributeFlow(model, FlowConfig(concurrency=1, timeout_s=0.15))
        active = asyncio.create_task(flow.run([FlowCard(0, "Card", ())]))
        queued = asyncio.create_task(flow.run([FlowCard(1, "Card", ())]))
        try:
            await asyncio.wait_for(model.started.wait(), 1)
            result = await asyncio.wait_for(asyncio.shield(queued), 0.25)
            assert result[0].final == ()
            assert result[0].calls[0].error == "TimeoutError"
        finally:
            active.cancel()
            queued.cancel()
            await asyncio.gather(active, queued, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize(
    "body",
    [
        {"title": " \n\t "},
        {"title": "Card", "image": "unaccepted-input"},
        {"title": "Card", "gold": {"Color_search": "blue"}},
        {"title": "Card", "seller_params": [{"name": " Color_SeArCh ", "value": "blue"}]},
        {"title": "Card", "seller_params": [{"name": "Color", "value": "blue", "gold": "red"}]},
        {
            "title": "T" * 500,
            "description": "D" * 20000,
            "seller_params": [{"name": "P", "value": "V" * 500}] * 8,
        },
    ],
)
def test_invalid_input_is_rejected_by_http_before_flow_execution(body: dict[str, Any]) -> None:
    async def run() -> None:
        app = create_app()
        app.dependency_overrides[extract_usecase] = lambda: None
        app.dependency_overrides[flow_usecase] = lambda: None
        app.dependency_overrides[history_usecase] = lambda: None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/extract", json=body)
            assert response.status_code == 422

    asyncio.run(run())


def test_exact_text_limit_is_accepted() -> None:
    request = ExtractRequest(
        title="T" * 500,
        description="D" * 20000,
        seller_params=[SellerParamSchema(name="P", value="V" * 499)] * 7,
    )
    assert len(request.title) + len(request.description) + 7 * 500 == 24000


def test_required_field_without_dictionary_remains_visible() -> None:
    required = RequiredAttributes(
        [RequiredRecord(123456, "New required field", 1)], Lexicon({}, [], {})
    )
    assert required.profiles(123456)["New required field"].kind is Kind.FREE


def test_model_error_details_are_not_saved_in_flow_records() -> None:
    class FailingModel:
        async def complete(self, request: StructuredRequest) -> Completion:
            raise ModelFailure("private transport details")

    async def run() -> None:
        result = await AttributeFlow(FailingModel()).run([FlowCard(1, "Card", ())])
        assert result[0].calls[0].error == "ModelFailure"

    asyncio.run(run())
