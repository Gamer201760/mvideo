import asyncio
from pathlib import Path

import pytest

from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.attribute_flow import FlowCard
from app.domain.errors import ModelUnavailable
from app.domain.inference import Completion, StructuredRequest
from app.usecase.attribute_flow import AttributeFlow, FlowConfig
from app.usecase.flow_fallback import run_fallback


class Unavailable:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: StructuredRequest) -> Completion:
        self.calls += 1
        raise ModelUnavailable(attempts=2)


class WaitingLocal(LocalRulesModel):
    def __init__(self) -> None:
        self.started, self.stopped = asyncio.Event(), asyncio.Event()
        self.wait = True

    async def complete(self, request: StructuredRequest) -> Completion:
        if not self.wait:
            return await super().complete(request)
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped.set()
        raise AssertionError("Cancelled local computation resumed")


def test_local_timeout_preserves_only_actual_provider_attempts() -> None:
    async def run() -> None:
        primary, local = Unavailable(), WaitingLocal()
        flow = AttributeFlow(primary, FlowConfig(timeout_s=0.01), fallback_model=local)
        outcomes = await asyncio.wait_for(flow.run([FlowCard(0, "Card", ())]), timeout=1)
        assert local.stopped.is_set() and primary.calls == 1
        assert outcomes[0].final == ()
        first, last = outcomes[0].calls
        assert first.attempts == 2 and first.dispatched
        assert last.error == "TimeoutError" and not last.dispatched and last.attempts == 0
        assert sum(call.attempts for call in outcomes[0].calls if call.dispatched) == 2

    asyncio.run(run())


def test_local_stage_caps_large_primary_budget_without_waiting_ten_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits: list[float] = []
    original_timeout = asyncio.timeout

    def virtual_timeout(seconds: float) -> asyncio.Timeout:
        limits.append(seconds)
        return original_timeout(0.01)

    monkeypatch.setattr("app.usecase.flow_fallback.asyncio.timeout", virtual_timeout)

    async def run() -> None:
        local = WaitingLocal()
        results, record = await run_fallback(
            local, (FlowCard(0, "Card", ()),), "model_unavailable", asyncio.Semaphore(1), 180
        )
        assert limits == [10]
        assert not results and local.stopped.is_set()
        assert record.error == "TimeoutError" and record.attempts == 0

    asyncio.run(run())


def test_user_cancellation_interrupts_local_stage_and_releases_the_gate() -> None:
    async def run() -> None:
        primary, local = Unavailable(), WaitingLocal()
        flow = AttributeFlow(primary, fallback_model=local)
        task = asyncio.create_task(flow.run([FlowCard(0, "Card", ())]))
        try:
            await asyncio.wait_for(local.started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert local.stopped.is_set() and primary.calls == 1
            local.wait = False
            outcomes = await asyncio.wait_for(flow.run([FlowCard(1, "Card", ())]), timeout=1)
            assert outcomes[0].final and outcomes[0].calls[-1].error is None
            assert outcomes[0].calls[-1].attempts == 0 and primary.calls == 2
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


def test_single_proxy_budget_covers_primary_and_local_without_changing_batch_timeout() -> None:
    root = Path(__file__).resolve().parents[4]
    config = (root / "frontend/nginx.conf").read_text()
    single = config.split("location /api/ {", 1)[1].split("\n    }", 1)[0]
    batch = config.split("location = /api/v1/extract/batch {", 1)[1].split("\n    }", 1)[0]
    assert "proxy_read_timeout 240s;" in single
    assert "proxy_read_timeout ${BATCH_PROXY_TIMEOUT_S}s;" in batch
