import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import Extraction, FlowCall, FlowCard, FlowOutcome
from app.domain.errors import ModelFailure
from app.domain.rule_routing import RuleRoutingPolicy, route_rules
from app.usecase.attribute_flow_contract import make_request
from app.usecase.flow_fallback import fallback_reason, run_fallback
from app.usecase.interface import LanguageModel


@dataclass(frozen=True, slots=True)
class FlowConfig:
    batch_size: int = 1
    concurrency: int = 3
    max_batch_chars: int = 24_000
    timeout_s: float = 120
    audit: str = "off"
    max_pending: int = 8

    def __post_init__(self) -> None:
        if (
            min(
                self.batch_size,
                self.concurrency,
                self.max_batch_chars,
                self.timeout_s,
                self.max_pending,
            )
            <= 0
        ):
            raise ValueError("batch, concurrency, character limit and timeout must be positive")
        if self.audit not in {"off", "conditional", "all"}:
            raise ValueError("audit must be off, conditional or all")


def batches(cards: Sequence[FlowCard], config: FlowConfig) -> list[tuple[FlowCard, ...]]:
    result: list[tuple[FlowCard, ...]] = []
    pending: list[FlowCard] = []
    for card in cards:
        if pending and (
            len(pending) == config.batch_size
            or len(make_request((*pending, card)).prompt) > config.max_batch_chars
        ):
            result.append(tuple(pending))
            pending = []
        pending.append(card)
    if pending:
        result.append(tuple(pending))
    return result


class AttributeFlow:
    def __init__(
        self,
        model: LanguageModel,
        config: FlowConfig | None = None,
        rule_policy: RuleRoutingPolicy | None = None,
        fallback_model: LanguageModel | None = None,
    ) -> None:
        self._model = model
        self._config = config or FlowConfig()
        self._gate = asyncio.Semaphore(self._config.concurrency)
        self._pending = 0
        self._rule_policy = rule_policy
        self._fallback_model = fallback_model

    async def _call(
        self,
        cards: tuple[FlowCard, ...],
        previous: tuple[Extraction, ...] = (),
    ) -> tuple[tuple[Extraction, ...], FlowCall]:
        waiting = time.perf_counter()
        started = waiting
        usage = None
        error = None
        results: tuple[Extraction, ...] = ()
        dispatched = False
        attempts = 0
        request = make_request(cards, previous)
        if len(request.prompt) > self._config.max_batch_chars:
            return (), FlowCall(
                "extract", tuple(c.sku_id for c in cards), 0, 0, None, "input_too_large", False, 0
            )
        if self._pending >= self._config.max_pending:
            return (), FlowCall(
                "extract", tuple(c.sku_id for c in cards), 0, 0, None, "capacity", False, 0
            )
        self._pending += 1
        try:
            async with asyncio.timeout(self._config.timeout_s):
                async with self._gate:
                    started = time.perf_counter()
                    dispatched = True
                    attempts = 1
                    try:
                        completion = await self._model.complete(request)
                    except asyncio.CancelledError as cancelled:
                        actual = getattr(cancelled, "model_attempts", None)
                        if isinstance(actual, int):
                            attempts = actual
                        raise
                    usage = completion.usage
                    attempts = usage.attempts
                    try:
                        results = await asyncio.to_thread(parse_batch, completion.output, cards)
                    except (TypeError, ValueError) as invalid:
                        error = type(invalid).__name__
        except (ModelFailure, TimeoutError) as exc:
            error = type(exc).__name__
            if isinstance(exc, ModelFailure):
                attempts = exc.attempts
        finally:
            self._pending -= 1
        record = FlowCall(
            "audit" if previous else "extract",
            tuple(c.sku_id for c in cards),
            1000 * (started - waiting),
            1000 * (time.perf_counter() - started),
            usage,
            error,
            dispatched,
            attempts,
        )
        return results, record

    async def _infer(
        self, cards: tuple[FlowCard, ...], previous: tuple[Extraction, ...] = ()
    ) -> tuple[tuple[Extraction, ...], tuple[FlowCall, ...]]:
        results, call = await self._call(cards, previous)
        reason = fallback_reason(call)
        if (
            results
            or previous
            or self._fallback_model is None
            or reason is None
            or self._pending >= self._config.max_pending
        ):
            return results, (call,)
        self._pending += 1
        try:
            results, local_call = await run_fallback(
                self._fallback_model, cards, reason, self._gate, self._config.timeout_s
            )
        finally:
            self._pending -= 1
        return results, (call, local_call)

    async def run(
        self,
        cards: Sequence[FlowCard],
        on_batch: Callable[[FlowOutcome], None] | None = None,
    ) -> list[FlowOutcome]:
        if len({card.sku_id for card in cards}) != len(cards):
            raise ValueError("duplicate input card identifiers")
        started = time.perf_counter()
        local: dict[int, Extraction] = {}
        if self._rule_policy is not None:
            for card in cards:
                decision = await asyncio.to_thread(route_rules, card, self._rule_policy)
                if decision.extraction is not None:
                    local[card.sku_id] = decision.extraction

        async def process(batch: tuple[FlowCard, ...]) -> FlowOutcome:
            pending = tuple(c for c in batch if c.sku_id not in local)
            extracted, batch_calls = await self._infer(pending) if pending else ((), ())
            by_id = {r.sku_id: r for r in extracted} | local
            initial = tuple(by_id[c.sku_id] for c in batch if c.sku_id in by_id)
            first_ready = 1000 * (time.perf_counter() - started)
            calls = list(batch_calls)
            targets = tuple(
                card
                for card in batch
                if card.sku_id in by_id
                and card.sku_id not in local
                and by_id[card.sku_id].fallback_reason is None
                and (
                    self._config.audit == "all"
                    or (
                        self._config.audit == "conditional"
                        and (
                            by_id[card.sku_id].review
                            or any(item.status == "ambiguous" for item in by_id[card.sku_id].items)
                        )
                    )
                )
            )
            final = initial
            if targets:
                ids = {card.sku_id for card in targets}
                audited, audit_calls = await self._infer(
                    targets,
                    tuple(result for result in initial if result.sku_id in ids),
                )
                calls.extend(audit_calls)
                replacements = {result.sku_id: result for result in audited}
                final = tuple(replacements.get(result.sku_id, result) for result in initial)
            outcome = FlowOutcome(
                initial,
                final,
                tuple(calls),
                first_ready,
                1000 * (time.perf_counter() - started),
            )
            if on_batch is not None:
                on_batch(outcome)
            return outcome

        groups = batches([card for card in cards if card.sku_id not in local], self._config)
        ready = tuple(card for card in cards if card.sku_id in local)
        if ready:
            positions = {card.sku_id: index for index, card in enumerate(cards)}
            combined = (*(groups[0] if groups else ()), *ready)
            first = tuple(sorted(combined, key=lambda card: positions[card.sku_id]))
            groups = [first, *groups[1:]]
        results: list[FlowOutcome | None] = [None] * len(groups)
        pending_groups = iter(enumerate(groups))

        async def worker() -> None:
            for index, batch in pending_groups:
                results[index] = await process(batch)

        workers = [
            asyncio.create_task(worker()) for _ in range(min(len(groups), self._config.concurrency))
        ]
        try:
            await asyncio.gather(*workers)
        finally:
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        return [result for result in results if result is not None]
