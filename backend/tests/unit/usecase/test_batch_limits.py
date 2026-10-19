import asyncio
from dataclasses import replace

from tests.unit.domain.routing_cases import complete_card
from tests.unit.usecase.test_attribute_flow import Model, card
from tests.unit.usecase.test_flow_rule_routing import CountingModel

from app.domain.attribute_flow import FlowCard
from app.domain.rule_routing import RuleRoutingPolicy
from app.usecase.attribute_flow import AttributeFlow, FlowConfig, batches
from app.usecase.attribute_flow_contract import make_request


def test_many_batches_are_processed_without_rejecting_their_own_queue() -> None:
    async def run() -> None:
        model = Model()
        flow = AttributeFlow(model, FlowConfig(batch_size=2, concurrency=2, max_pending=3))
        results = await flow.run([card(i) for i in range(40)])
        assert len(results) == len(model.requests) == 20
        assert model.peak == 2
        assert not any(call.error for result in results for call in result.calls)
        assert [item.sku_id for result in results for item in result.final] == list(range(40))

    asyncio.run(run())


def test_packing_uses_actual_shared_dictionary_json_at_the_limit() -> None:
    cards = [card(i) for i in range(3)]
    limit = len(make_request(tuple(cards[:2])).prompt)
    groups = batches(cards, FlowConfig(batch_size=3, max_batch_chars=limit))
    assert [len(group) for group in groups] == [2, 1]
    assert all(len(make_request(group).prompt) <= limit for group in groups)


def test_rules_are_removed_before_packing_remaining_cards() -> None:
    async def run() -> None:
        model = CountingModel()
        cards = [
            complete_card(i) if i % 2 else replace(complete_card(i), rules=()) for i in range(12)
        ]
        outcomes = await AttributeFlow(model, FlowConfig(batch_size=3), RuleRoutingPolicy()).run(
            cards
        )
        assert len(model.requests) == 2
        assert {item.sku_id for outcome in outcomes for item in outcome.final} == set(range(12))

    asyncio.run(run())


def test_oversized_single_card_is_not_sent_or_silently_truncated() -> None:
    async def run() -> None:
        model = Model()
        flow = AttributeFlow(model, FlowConfig(max_batch_chars=100))
        results = await flow.run([FlowCard(7, "X" * 200, ())])
        assert model.requests == []
        assert results[0].final == ()
        assert results[0].calls[0].error == "input_too_large"
        assert results[0].calls[0].dispatched is False

    asyncio.run(run())
