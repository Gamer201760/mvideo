import asyncio
import time

import httpx
import pytest
from tests.unit.adapter.test_gateway import REQUEST
from tests.unit.usecase.test_attribute_flow import card

from app.adapter.llm.gateway import GatewayModel
from app.adapter.llm.gateway_retry import GatewayRetry
from app.domain.errors import ModelTimeout
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.flow_failures import flow_failure


def test_overall_timeout_cancels_backoff_without_another_attempt() -> None:
    async def run() -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, headers={"retry-after": "999"})

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            timeout_s=0.02,
            transport=httpx.MockTransport(respond),
        )
        started = time.perf_counter()
        try:
            with pytest.raises(ModelTimeout) as error:
                await model.complete(REQUEST)
            assert error.value.attempts == calls == 1
            assert time.perf_counter() - started < 0.5
        finally:
            await model.aclose()

    asyncio.run(run())


def test_cancellation_in_second_attempt_stops_and_preserves_count() -> None:
    async def run() -> None:
        calls = 0
        second = asyncio.Event()

        async def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503)
            second.set()
            await asyncio.Event().wait()
            raise AssertionError("Cancelled request resumed")

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            retry=GatewayRetry(base_delay_s=0),
            transport=httpx.MockTransport(respond),
        )
        task = asyncio.create_task(model.complete(REQUEST))
        try:
            await asyncio.wait_for(second.wait(), 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError) as error:
                await task
            assert error.value.__dict__["model_attempts"] == calls == 2
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await model.aclose()

    asyncio.run(run())


def test_flow_timeout_during_retry_reports_both_real_attempts() -> None:
    async def run() -> None:
        calls = 0

        async def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(502)
            await asyncio.Event().wait()
            raise AssertionError("Timed out request resumed")

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            timeout_s=1,
            retry=GatewayRetry(base_delay_s=0),
            transport=httpx.MockTransport(respond),
        )
        try:
            outcomes = await AttributeFlow(model, FlowConfig(timeout_s=0.02)).run([card()])
            call = outcomes[0].calls[0]
            assert outcomes[0].final == ()
            assert call.error == "TimeoutError"
            assert call.dispatched and call.attempts == calls == 2
            assert flow_failure((call,)).attempts == 2
        finally:
            await model.aclose()

    asyncio.run(run())


def test_queue_timeout_does_not_count_an_unsent_model_attempt() -> None:
    async def run() -> None:
        calls = 0

        async def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            await asyncio.Event().wait()
            raise AssertionError("Timed out request resumed")

        model = GatewayModel(
            "https://gateway.example/v1",
            "default",
            transport=httpx.MockTransport(respond),
        )
        flow = AttributeFlow(model, FlowConfig(concurrency=1, timeout_s=0.02))
        try:
            outcomes = await asyncio.gather(flow.run([card(1)]), flow.run([card(2)]))
            attempts = [outcome[0].calls[0].attempts for outcome in outcomes]
            assert sorted(attempts) == [0, 1]
            assert calls == 1
        finally:
            await model.aclose()

    asyncio.run(run())
