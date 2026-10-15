import asyncio
import hashlib
import heapq
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.errors import ModelFailure
from app.domain.metrics import MetricsBook
from app.usecase.baseline import (
    EVAL_SPLITS,
    BaselineConfig,
    Segments,
    extra_attributes,
    observe,
)
from app.usecase.baseline_ports import (
    BaselineSource,
    CardRecord,
    GoldRecord,
    PredictionSink,
    ReportSink,
)
from app.usecase.decision_ports import CategoryTree, DecisionCache
from app.usecase.decision_report import (
    BUDGET_SKIP,
    CalibrationBook,
    ReportMeta,
    UsageBook,
    build_decision_report,
    render_decision_markdown,
)
from app.usecase.decision_slots import SlotBook
from app.usecase.decision_stage import (
    ChooseValues,
    StageConfig,
    StageResult,
    merge,
)
from app.usecase.extraction import CardExtraction, RequiredAttributes, extract_card, prediction_of
from app.usecase.interface import DecisionModel, Logger
from app.usecase.lexicon_builder import LexiconConfig, build_lexicon

BUDGET_EXHAUSTED = BUDGET_SKIP


OVERRIDE_GRID = (0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.01)
DROP_GRID: tuple[float | None, ...] = (None, 0.95, 0.8, 0.6)


@dataclass(frozen=True, slots=True)
class DecisionRunConfig:
    stage: StageConfig
    provider: str
    offline: bool
    splits: frozenset[str] = EVAL_SPLITS
    sample: int = 300
    seed: int = 42
    concurrency: int = 8
    batch: int = 2000
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    head_categories: int = 50
    max_cost_usd: float | None = None
    override: float = 0.5
    drop: float | None = None
    grid: tuple[float, ...] = OVERRIDE_GRID
    drop_grid: tuple[float | None, ...] = DROP_GRID
    lexicon: LexiconConfig = field(default_factory=LexiconConfig)


@dataclass(frozen=True, slots=True)
class CardOutcome:
    card: CardRecord
    base: CardExtraction
    result: StageResult | None
    failure: str | None


def sample_rank(seed: int, sku: int) -> int:
    digest = hashlib.sha256(f"{seed}:{sku}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def sample_cards(batches: Iterator[list[CardRecord]], size: int, seed: int) -> list[CardRecord]:
    heap: list[tuple[int, int, CardRecord]] = []
    for batch in batches:
        for card in batch:
            item = (-sample_rank(seed, card.sku_id), card.sku_id, card)
            if len(heap) < size:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
    return sorted((card for _, _, card in heap), key=lambda c: c.sku_id)


class RunDecision:
    def __init__(
        self, source: BaselineSource, sink: PredictionSink, reports: ReportSink,
        model: DecisionModel, logger: Logger, cache: DecisionCache | None = None,
        categories: CategoryTree | None = None,
    ) -> None:
        self._source = source
        self._sink = sink
        self._reports = reports
        self._model = model
        self._logger = logger
        self._cache = cache
        self._categories = categories

    async def run(self, config: DecisionRunConfig) -> Mapping[str, object]:
        started = time.monotonic()
        records = self._source.required()
        names = frozenset(r.attribute for r in records) | extra_attributes()
        lexicon = build_lexicon(self._source.train_values(names), config.lexicon)
        required = RequiredAttributes(records, lexicon)
        cards = sample_cards(self._source.cards(config.splits, config.batch), config.sample,
                             config.seed)
        self._logger.info("decision_sample", cards=len(cards), provider=config.provider)
        stage = ChooseValues(self._model, lexicon, config.stage, self._cache, self._categories)
        gate = asyncio.Semaphore(config.concurrency)
        spent = [0.0]

        async def one(card: CardRecord) -> CardOutcome:
            base = extract_card(card, required, lexicon, config.stage.min_confidence)
            async with gate:
                if config.max_cost_usd is not None and spent[0] >= config.max_cost_usd:
                    return CardOutcome(card, base, None, BUDGET_EXHAUSTED)
                try:
                    result = await stage.choose(card, base)
                except ModelFailure as exc:
                    self._logger.warning("decision_failed", sku=card.sku_id, error=str(exc))
                    return CardOutcome(card, base, None, str(exc))
                if result.usage is not None and not result.cached:
                    spent[0] += result.usage.cost_usd or 0.0
                return CardOutcome(card, base, result, None)

        outcomes = await asyncio.gather(*(one(c) for c in cards))
        gold = self._source.gold(config.splits)
        stats = self._source.category_stats()
        head = frozenset(sorted(stats, key=lambda c: -stats[c][0])[: config.head_categories])
        cards_of = {c: max(1, s[1]) for c, s in stats.items()}
        segments = Segments(head, self._source.seller_cards(),
                            BaselineConfig(head_categories=config.head_categories), cards_of)
        books = (MetricsBook(weighted=False), MetricsBook(weighted=True))
        baseline = (MetricsBook(weighted=False), MetricsBook(weighted=True))
        calibration, usage, slots = CalibrationBook(), UsageBook(), SlotBook()
        predictions = []
        for outcome in outcomes:
            truth = gold.get(outcome.card.sku_id, ())
            chosen = merge(outcome.base, outcome.result, config.override,
                           config.stage.min_confidence, config.drop)
            observe(outcome.card, chosen, truth, required, segments, books)
            observe(outcome.card, outcome.base, truth, required, segments, baseline)
            if outcome.result is not None:
                calibration.extend(slots.add(outcome.base, outcome.result, truth))
            usage.add(outcome.result, outcome.failure)
            predictions.append(prediction_of(outcome.card, chosen))
        self._sink.write(predictions, [])
        self._sink.close()
        grid = [threshold_row(t, d, outcomes, gold, required, segments, config)
                for d in config.drop_grid for t in config.grid]
        report = build_decision_report(
            books, baseline, calibration, usage, meta=report_meta(config), cards=len(cards),
            lexicon_entries=lexicon.size, attributes=len(lexicon.profiles),
            seconds=round(time.monotonic() - started, 1), grid=grid, slots=slots.summary())
        self._reports.write(report, render_decision_markdown(report))
        self._logger.info("decision_done", cards=len(cards), failures=usage.failures)
        return report


def threshold_row(
    threshold: float, drop: float | None, outcomes: Sequence[CardOutcome], gold: Mapping[int, Sequence[GoldRecord]],
    required: RequiredAttributes, segments: Segments, config: DecisionRunConfig,
) -> dict[str, object]:
    books = (MetricsBook(weighted=False), MetricsBook(weighted=True))
    for o in outcomes:
        merged = merge(o.base, o.result, threshold, config.stage.min_confidence, drop)
        observe(o.card, merged, gold.get(o.card.sku_id, ()), required, segments, books)
    plain, weighted = books[0].micro("all"), books[1].micro("all")
    return {"override": threshold, "drop": drop, "precision": plain["precision"], "recall": plain["recall"],
            "f1": plain["f1"], "coverage_after": plain["coverage_after"],
            "weighted_f1": weighted["f1"], "macro_f1": books[0].macro_f1("all")}


def report_meta(config: DecisionRunConfig) -> ReportMeta:
    return ReportMeta(
        provider=config.provider,
        offline=config.offline,
        sample={"size": config.sample, "seed": config.seed, "splits": sorted(config.splits)},
        stage_config={"top_k": config.stage.top_k, "dictionary_k": config.stage.dictionary_k,
                      "min_confidence": config.stage.min_confidence,
                      "model": config.stage.model_name, "max_cost_usd": config.max_cost_usd,
                      "override": config.override, "drop": config.drop,
                      "dictionary": config.stage.dictionary, "mix_k": config.stage.mix_k,
                      "route_all": config.stage.route_all,
                      "route_below": config.stage.route_below},
        price_input_per_mtok=config.price_input_per_mtok,
        price_output_per_mtok=config.price_output_per_mtok,
    )
