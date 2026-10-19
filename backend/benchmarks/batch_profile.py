import argparse
import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.attribute_flow import CatalogCandidate, CatalogField, Extraction, FlowCard
from app.domain.inference import Completion, StructuredRequest
from app.domain.regex_answers import regex_answers
from app.usecase.attribute_flow import AttributeFlow, FlowConfig


class MeteredRules(LocalRulesModel):
    def __init__(self) -> None:
        self.requests = 0
        self.characters = 0
        self.bytes = 0

    async def complete(self, request: StructuredRequest) -> Completion:
        serialized = (
            request.system + request.prompt + json.dumps(request.schema, ensure_ascii=False)
        )
        self.requests += 1
        self.characters += len(serialized)
        self.bytes += len(serialized.encode())
        return await super().complete(request)


def synthetic_cards(count: int) -> list[FlowCard]:
    category = CatalogCandidate(
        7,
        "Товары / Емкости",
        0.9,
        (CatalogField("Объем", "numeric", "л"), CatalogField("Цвет", "categorical", "")),
    )
    cards = []
    for index in range(count):
        text = f"Емкость {index}\nОбъем: 1700 мл\nЦвет: черный"
        cards.append(FlowCard(index, text, (category,), regex_answers(text, category)))
    return cards


@dataclass(frozen=True, slots=True)
class Measurement:
    batch_size: int
    requests: int
    request_characters: int
    request_bytes: int
    local_wall_ms: float


async def measure(
    cards: list[FlowCard], batch_size: int, concurrency: int
) -> tuple[Measurement, dict[int, Extraction]]:
    model = MeteredRules()
    started = time.perf_counter()
    outcomes = await AttributeFlow(
        model, FlowConfig(batch_size=batch_size, concurrency=concurrency, max_batch_chars=48_000)
    ).run(cards)
    results = {item.sku_id: item for outcome in outcomes for item in outcome.final}
    if len(results) != len(cards) or any(len(result.items) != 2 for result in results.values()):
        raise ValueError("Synthetic extraction did not fill the expected fields")
    return Measurement(
        batch_size,
        model.requests,
        model.characters,
        model.bytes,
        round((time.perf_counter() - started) * 1000, 3),
    ), results


def implementation_hash() -> str:
    root = Path(__file__).resolve().parents[1] / "src"
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


async def profile(count: int, batch_size: int, concurrency: int) -> dict[str, object]:
    cards = synthetic_cards(count)
    single, before = await measure(cards, 1, concurrency)
    grouped, after = await measure(cards, batch_size, concurrency)
    if before != after:
        raise ValueError("Batching changed the synthetic extraction results")
    spans_valid = all(
        card.text[item.start : item.end] == item.quote
        for card in cards
        for item in after[card.sku_id].items
    )
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "synthetic local_rules; no external model calls; no token or production throughput measurement",
        "cards": count,
        "concurrency_limit": concurrency,
        "rules_first": False,
        "single": asdict(single),
        "batch": asdict(grouped),
        "requests_reduction_percent": round(100 * (1 - grouped.requests / single.requests), 2),
        "request_characters_reduction_percent": round(
            100 * (1 - grouped.request_characters / single.request_characters), 2
        ),
        "outputs_equal": before == after,
        "evidence_spans_valid": spans_valid,
        "implementation_sha256": implementation_hash(),
        "profiler_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        not 1 <= args.cards <= 1000
        or not 1 <= args.batch_size <= 16
        or not 1 <= args.concurrency <= 8
    ):
        parser.error("cards must be 1..1000, batch-size 1..16, concurrency 1..8")
    if args.output.exists():
        parser.error("Output already exists; choose a new report path")
    report = asyncio.run(profile(args.cards, args.batch_size, args.concurrency))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
