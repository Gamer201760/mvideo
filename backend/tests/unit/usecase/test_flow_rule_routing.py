import asyncio
import json
from dataclasses import replace

import pytest
from tests.unit.domain.routing_cases import complete_card

from app.domain.attribute_flow import FlowOutcome
from app.domain.errors import ModelFailure
from app.domain.inference import Completion, StructuredRequest, Usage
from app.domain.rule_routing import RuleRoutingPolicy
from app.usecase.attribute_flow import AttributeFlow, FlowConfig


class CountingModel:
    def __init__(self, fail: bool = False) -> None:
        self.requests: list[StructuredRequest] = []
        self.fail = fail

    async def complete(self, request: StructuredRequest) -> Completion:
        self.requests.append(request)
        if self.fail:
            raise ModelFailure("test failure")
        cards = json.loads(request.prompt)["c"]
        return Completion(
            {"c": [{"i": i, "k": card["k"][0], "a": [], "r": []} for i, card in enumerate(cards)]},
            Usage("test"),
        )


@pytest.mark.parametrize("audit", ["off", "conditional", "all"])
def test_complete_rules_do_not_invoke_extraction_or_audit(audit: str) -> None:
    model = CountingModel()
    flow = AttributeFlow(model, FlowConfig(audit=audit), RuleRoutingPolicy())
    outcomes = asyncio.run(flow.run([complete_card()]))
    assert not model.requests
    assert not outcomes[0].calls
    assert outcomes[0].initial == outcomes[0].final
    assert len(outcomes[0].final[0].items) == 2


def test_mixed_batch_sends_only_unresolved_cards_and_keeps_identifiers() -> None:
    model = CountingModel()
    flow = AttributeFlow(model, FlowConfig(batch_size=3), RuleRoutingPolicy())
    ready = complete_card(2)
    unresolved = replace(complete_card(1), rules=())
    callbacks: list[FlowOutcome] = []
    outcomes = asyncio.run(flow.run([unresolved, ready], callbacks.append))
    assert len(model.requests) == 1
    assert len(json.loads(model.requests[0].prompt)["c"]) == 1
    assert [r.sku_id for r in outcomes[0].final] == [1, 2]
    assert outcomes[0].final[0].items == ()
    assert len(outcomes[0].final[1].items) == 2
    assert callbacks == outcomes


def test_pending_failure_preserves_rules_result_without_a_spurious_audit() -> None:
    model = CountingModel(fail=True)
    flow = AttributeFlow(model, FlowConfig(batch_size=2, audit="all"), RuleRoutingPolicy())
    unresolved = replace(complete_card(1), rules=())
    outcomes = asyncio.run(flow.run([unresolved, complete_card(2)]))
    assert len(model.requests) == 1
    assert [r.sku_id for r in outcomes[0].final] == [2]
    assert outcomes[0].calls[0].error == "ModelFailure"


def test_routing_is_not_enabled_implicitly() -> None:
    model = CountingModel()
    asyncio.run(AttributeFlow(model).run([complete_card()]))
    assert len(model.requests) == 1
