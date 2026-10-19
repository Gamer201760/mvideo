from collections.abc import Sequence
from dataclasses import dataclass, replace

from app.domain.attribute_flow import FlowCall, FlowCard
from app.domain.errors import DomainError
from app.usecase.flow_failures import flow_failure
from app.usecase.stand_attribute_flow import StandAttributeFlow, StandFlowResult
from app.usecase.stand_ports import CardInput


@dataclass(frozen=True, slots=True)
class BatchItem:
    index: int
    result: StandFlowResult | None = None
    error: DomainError | None = None


@dataclass(frozen=True, slots=True)
class BatchResult:
    items: tuple[BatchItem, ...]
    calls: tuple[FlowCall, ...]


class BatchExtraction:
    def __init__(self, flow: StandAttributeFlow) -> None:
        self._flow = flow

    async def execute(self, cards: Sequence[CardInput]) -> BatchResult:
        prepared: dict[int, FlowCard] = {}
        items: dict[int, BatchItem] = {}
        for index, card in enumerate(cards):
            try:
                prepared[index] = replace(await self._flow.prepare(card), sku_id=index)
            except DomainError as error:
                items[index] = BatchItem(index, error=error)
        outcomes = await self._flow.infer(tuple(prepared.values()))
        results = {result.sku_id: result for outcome in outcomes for result in outcome.final}
        calls = tuple(call for outcome in outcomes for call in outcome.calls)
        for index, prepared_card in prepared.items():
            if index not in results:
                failure = flow_failure([call for call in calls if index in call.sku_ids])
                items[index] = BatchItem(index, error=failure)
                continue
            try:
                result = await self._flow.finalize(cards[index], prepared_card, results[index])
                items[index] = BatchItem(index, result=result)
            except DomainError as error:
                items[index] = BatchItem(index, error=error)
        return BatchResult(tuple(items[index] for index in range(len(cards))), calls)
