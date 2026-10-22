import asyncio

import pytest

from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.attribute_flow import CatalogCandidate, CatalogField, FlowCard
from app.domain.errors import (
    InvalidModelOutput,
    ModelCapacity,
    ModelFailure,
    ModelInputTooLarge,
    ModelRateLimited,
    ModelTimeout,
    ModelUnavailable,
    StorageUnavailable,
)
from app.domain.inference import Completion, StructuredRequest, Usage
from app.domain.regex_answers import regex_answers
from app.usecase.attribute_flow import AttributeFlow, FlowConfig


def grounded_card(sku_id: int = 0, text: str = "Чайник\nЦвет: green") -> FlowCard:
    category = CatalogCandidate(
        1001,
        "Чайники",
        1,
        (
            CatalogField("Цвет", "categorical", "", ("красный",)),
            CatalogField("Объем", "numeric", "л"),
        ),
    )
    return FlowCard(sku_id, text, (category,), regex_answers(text, category))


class FailedModel:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    async def complete(self, request: StructuredRequest) -> Completion:
        self.calls += 1
        raise self.error


class TrackedLocal(LocalRulesModel):
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: StructuredRequest) -> Completion:
        self.calls += 1
        return await super().complete(request)


@pytest.mark.parametrize("failure", [ModelUnavailable, ModelRateLimited, ModelTimeout])
def test_availability_failure_runs_grounded_partial_fallback_and_retains_attempts(
    failure: type[ModelFailure],
) -> None:
    async def run() -> None:
        card = grounded_card()
        local = TrackedLocal()
        result = (
            await AttributeFlow(FailedModel(failure(attempts=2)), fallback_model=local).run([card])
        )[0]
        assert local.calls == 1
        assert len(result.final) == 1
        extraction = result.final[0]
        assert extraction.fallback_reason == failure.code
        assert [answer.attribute for answer in extraction.items] == ["Цвет"]
        answer = extraction.items[0]
        assert answer.normalized_value == "зеленый"
        assert card.text[answer.start : answer.end] == answer.quote == "green"
        primary, fallback = result.calls
        assert primary.error == failure.__name__ and primary.attempts == 2
        assert primary.dispatched
        assert fallback.stage == "fallback" and fallback.error is None
        assert not fallback.dispatched and fallback.attempts == 0 and fallback.usage is None

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure", [InvalidModelOutput, ModelInputTooLarge, ModelCapacity, ModelFailure]
)
def test_nonavailability_model_failures_do_not_trigger_fallback(
    failure: type[ModelFailure],
) -> None:
    async def run() -> None:
        local = TrackedLocal()
        result = (
            await AttributeFlow(FailedModel(failure()), fallback_model=local).run([grounded_card()])
        )[0]
        assert local.calls == 0
        assert result.final == ()
        assert len(result.calls) == 1 and result.calls[0].error == failure.__name__

    asyncio.run(run())


@pytest.mark.parametrize("failure", [ValueError, TypeError, RuntimeError, StorageUnavailable])
def test_programmer_and_storage_failures_propagate_without_fallback(
    failure: type[Exception],
) -> None:
    async def run() -> None:
        local = TrackedLocal()
        with pytest.raises(failure):
            await AttributeFlow(FailedModel(failure()), fallback_model=local).run([grounded_card()])
        assert local.calls == 0

    asyncio.run(run())


def test_oversized_input_never_calls_primary_or_fallback() -> None:
    async def run() -> None:
        primary, local = FailedModel(ModelUnavailable()), TrackedLocal()
        result = (
            await AttributeFlow(primary, FlowConfig(max_batch_chars=1), fallback_model=local).run(
                [grounded_card()]
            )
        )[0]
        assert primary.calls == local.calls == 0
        assert not result.calls[0].dispatched
        assert result.calls[0].attempts == 0 and result.final == ()

    asyncio.run(run())


def test_fallback_uses_same_uncertainty_guards_and_does_not_invent_absent_values() -> None:
    async def run() -> None:
        cards = [
            grounded_card(i, text)
            for i, text in enumerate(("Чайник\nЦвет: возможно красный", "Чайник без характеристик"))
        ]
        outcomes = await AttributeFlow(
            FailedModel(ModelUnavailable()), fallback_model=LocalRulesModel()
        ).run(cards)
        for outcome in outcomes:
            extraction = outcome.final[0]
            assert extraction.items == ()
            assert extraction.fallback_reason == "model_unavailable"
        assert outcomes[0].final[0].rejections

    asyncio.run(run())


def test_fallback_results_are_not_sent_back_to_failed_provider_for_audit() -> None:
    async def run() -> None:
        primary, local = FailedModel(ModelUnavailable()), TrackedLocal()
        result = (
            await AttributeFlow(primary, FlowConfig(audit="all"), fallback_model=local).run(
                [grounded_card()]
            )
        )[0]
        assert primary.calls == local.calls == 1
        assert [call.stage for call in result.calls] == ["extract", "fallback"]

    asyncio.run(run())


def test_failed_optional_audit_preserves_successful_primary_extraction() -> None:
    class AuditFails(LocalRulesModel):
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, request: StructuredRequest) -> Completion:
            self.calls += 1
            if self.calls == 2:
                raise ModelUnavailable()
            return await super().complete(request)

    async def run() -> None:
        primary, local = AuditFails(), TrackedLocal()
        outcome = (
            await AttributeFlow(primary, FlowConfig(audit="all"), fallback_model=local).run(
                [grounded_card()]
            )
        )[0]
        assert local.calls == 0
        assert outcome.final == outcome.initial
        assert outcome.final[0].fallback_reason is None
        assert outcome.calls[-1].error == "ModelUnavailable"

    asyncio.run(run())


def test_malformed_primary_output_does_not_trigger_availability_fallback() -> None:
    class Malformed:
        async def complete(self, request: StructuredRequest) -> Completion:
            return Completion({"c": []}, Usage("test"))

    async def run() -> None:
        local = TrackedLocal()
        result = (await AttributeFlow(Malformed(), fallback_model=local).run([grounded_card()]))[0]
        assert local.calls == 0 and result.final == ()
        assert result.calls[0].error == "ValueError"

    asyncio.run(run())


def test_disabled_fallback_keeps_original_failure() -> None:
    async def run() -> None:
        result = (await AttributeFlow(FailedModel(ModelUnavailable())).run([grounded_card()]))[0]
        assert result.final == () and len(result.calls) == 1

    asyncio.run(run())
