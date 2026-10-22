import asyncio
import time
from dataclasses import replace

from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import Extraction, FlowCall, FlowCard
from app.domain.errors import ModelFailure, ModelRateLimited, ModelTimeout, ModelUnavailable
from app.usecase.attribute_flow_contract import make_request
from app.usecase.interface import LanguageModel

AVAILABILITY_ERRORS = {
    error.__name__: error.code for error in (ModelRateLimited, ModelTimeout, ModelUnavailable)
}
AVAILABILITY_ERRORS["TimeoutError"] = ModelTimeout.code


def fallback_reason(call: FlowCall) -> str | None:
    return AVAILABILITY_ERRORS.get(call.error or "") if call.dispatched else None


async def run_fallback(
    model: LanguageModel,
    cards: tuple[FlowCard, ...],
    reason: str,
    gate: asyncio.Semaphore,
    timeout_s: float,
) -> tuple[tuple[Extraction, ...], FlowCall]:
    waiting = started = time.perf_counter()
    error = None
    results: tuple[Extraction, ...] = ()
    try:
        async with asyncio.timeout(min(timeout_s, 10)):
            async with gate:
                started = time.perf_counter()
                completion = await model.complete(make_request(cards))
                parsed = await asyncio.to_thread(parse_batch, completion.output, cards)
                results = tuple(replace(result, fallback_reason=reason) for result in parsed)
    except (ModelFailure, TimeoutError) as failure:
        error = type(failure).__name__
    return results, FlowCall(
        "fallback",
        tuple(card.sku_id for card in cards),
        1000 * (started - waiting),
        1000 * (time.perf_counter() - started),
        None,
        error,
        False,
        0,
    )
