import asyncio
import json

from tests.unit.usecase.test_flow_fallback import FailedModel, TrackedLocal, grounded_card

from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.errors import ModelUnavailable
from app.domain.inference import Completion, StructuredRequest
from app.usecase.attribute_flow import AttributeFlow, FlowConfig


def test_multicard_batch_fallback_maps_each_quote_without_counting_local_provider_calls() -> None:
    async def run() -> None:
        cards = [
            grounded_card(i, f"Чайник {i}\nЦвет: {color}")
            for i, color in enumerate(("green", "красный"))
        ]
        outcome = (
            await AttributeFlow(
                FailedModel(ModelUnavailable(attempts=2)),
                FlowConfig(batch_size=2),
                fallback_model=LocalRulesModel(),
            ).run(cards)
        )[0]
        assert len(outcome.final) == 2
        assert [result.sku_id for result in outcome.final] == [0, 1]
        assert [result.items[0].normalized_value for result in outcome.final] == [
            "зеленый",
            "красный",
        ]
        assert sum(call.attempts for call in outcome.calls if call.dispatched) == 2
        for card, extraction in zip(cards, outcome.final, strict=True):
            assert extraction.fallback_reason == "model_unavailable"
            for answer in extraction.items:
                assert card.text[answer.start : answer.end] == answer.quote

    asyncio.run(run())


def test_primary_and_fallback_share_concurrency_bound_and_reason_does_not_leak() -> None:
    class Activity:
        active = 0
        peak = 0

    class Controlled(LocalRulesModel):
        def __init__(self, activity: Activity, *, primary: bool) -> None:
            self.activity, self.primary = activity, primary

        async def complete(self, request: StructuredRequest) -> Completion:
            self.activity.active += 1
            self.activity.peak = max(self.activity.peak, self.activity.active)
            try:
                await asyncio.sleep(0.005)
                if self.primary and "fail" in json.loads(request.prompt)["c"][0]["t"]:
                    raise ModelUnavailable()
                return await super().complete(request)
            finally:
                self.activity.active -= 1

    async def run() -> None:
        activity = Activity()
        flow = AttributeFlow(
            Controlled(activity, primary=True),
            FlowConfig(concurrency=2),
            fallback_model=Controlled(activity, primary=False),
        )
        cards = [
            grounded_card(i, f"Чайник {'fail' if i % 2 else 'healthy'} {i}\nЦвет: green")
            for i in range(8)
        ]
        outcomes = await flow.run(cards)
        assert activity.peak == 2 and activity.active == 0
        for outcome in outcomes:
            result = outcome.final[0]
            assert result.fallback_reason == ("model_unavailable" if result.sku_id % 2 else None)
            assert len(outcome.calls) == (2 if result.sku_id % 2 else 1)

    asyncio.run(run())


def test_caller_cancellation_never_starts_fallback_and_flow_can_be_reused() -> None:
    class Blocked(LocalRulesModel):
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.block = True

        async def complete(self, request: StructuredRequest) -> Completion:
            self.started.set()
            if self.block:
                await asyncio.Event().wait()
            return await super().complete(request)

    async def run() -> None:
        primary, local = Blocked(), TrackedLocal()
        flow = AttributeFlow(primary, FlowConfig(max_pending=1), fallback_model=local)
        task = asyncio.create_task(flow.run([grounded_card()]))
        await asyncio.wait_for(primary.started.wait(), 1)
        task.cancel()
        try:
            await task
            raise AssertionError("Cancellation was swallowed")
        except asyncio.CancelledError:
            pass
        assert local.calls == 0
        primary.block = False
        result = (await flow.run([grounded_card()]))[0]
        assert result.final[0].fallback_reason is None

    asyncio.run(run())


def test_caller_can_cancel_in_progress_local_fallback() -> None:
    class Blocked(LocalRulesModel):
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False

        async def complete(self, request: StructuredRequest) -> Completion:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return await super().complete(request)

    async def run() -> None:
        local = Blocked()
        flow = AttributeFlow(FailedModel(ModelUnavailable()), fallback_model=local)
        task = asyncio.create_task(flow.run([grounded_card()]))
        await asyncio.wait_for(local.started.wait(), 1)
        task.cancel()
        try:
            await task
            raise AssertionError("Cancellation was swallowed")
        except asyncio.CancelledError:
            pass
        assert local.cancelled

    asyncio.run(run())


def test_primary_deadline_can_recover_with_bounded_local_fallback() -> None:
    class Blocked:
        async def complete(self, request: StructuredRequest) -> Completion:
            await asyncio.Event().wait()
            raise AssertionError("Timed out primary resumed")

    async def run() -> None:
        result = (
            await AttributeFlow(
                Blocked(), FlowConfig(timeout_s=0.01), fallback_model=LocalRulesModel()
            ).run([grounded_card()])
        )[0]
        assert result.final[0].fallback_reason == "model_timeout"
        assert result.calls[0].error == "TimeoutError"
        assert result.calls[1].stage == "fallback"

    asyncio.run(run())


def test_capacity_rejection_does_not_bypass_backpressure_via_fallback() -> None:
    class Blocked:
        def __init__(self) -> None:
            self.started, self.release = asyncio.Event(), asyncio.Event()

        async def complete(self, request: StructuredRequest) -> Completion:
            self.started.set()
            await self.release.wait()
            raise ModelUnavailable()

    async def run() -> None:
        primary, local = Blocked(), TrackedLocal()
        flow = AttributeFlow(primary, FlowConfig(max_pending=1), fallback_model=local)
        first = asyncio.create_task(flow.run([grounded_card(0)]))
        await asyncio.wait_for(primary.started.wait(), 1)
        rejected = (await flow.run([grounded_card(1)]))[0]
        assert rejected.final == () and rejected.calls[0].error == "capacity"
        assert not rejected.calls[0].dispatched and local.calls == 0
        primary.release.set()
        recovered = (await first)[0]
        assert recovered.final[0].fallback_reason == "model_unavailable"
        assert local.calls == 1

    asyncio.run(run())


def test_failed_fallback_is_not_retried_or_counted_as_a_provider_request() -> None:
    async def run() -> None:
        primary, local = FailedModel(ModelUnavailable(attempts=2)), FailedModel(ModelUnavailable())
        result = (await AttributeFlow(primary, fallback_model=local).run([grounded_card()]))[0]
        assert result.final == () and primary.calls == local.calls == 1
        assert len(result.calls) == 2
        assert result.calls[-1].stage == "fallback"
        assert result.calls[-1].error == "ModelUnavailable"
        assert sum(call.attempts for call in result.calls if call.dispatched) == 2

    asyncio.run(run())
