import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.lexicon import Lexicon
from app.domain.metrics import MetricsBook
from app.domain.profile import MODEL
from app.domain.scoring import Pick
from app.domain.twin import Transfer, accepted, others, vote
from app.domain.values import canonical_key
from app.usecase.baseline import EVAL_SPLITS, BaselineConfig, Segments, extra_attributes, observe
from app.usecase.baseline_ports import CardRecord, GoldRecord, ReportSink
from app.usecase.extraction import CardExtraction, RequiredAttributes, extract_card
from app.usecase.interface import Logger
from app.usecase.lexicon_builder import build_lexicon
from app.usecase.ranker_ports import Calibrator
from app.usecase.twin_pass import (
    IndexBuilder,
    TwinIndexData,
    numeric_of,
    open_slots,
    query_of,
    stage_picks,
    twin_pick,
    with_picks,
)
from app.usecase.twin_ports import TitleIndex, TwinPrediction, TwinPredictionSink, TwinSource
from app.usecase.twin_report import TwinLog, build_twin_report, render_twin_markdown
from app.usecase.twin_tuning import CurvePoint, PairRecord, TuningLog, pick_threshold

GRID = tuple(round(0.5 + 0.05 * i, 2) for i in range(10))


@dataclass(frozen=True, slots=True)
class TwinConfig:
    stage: str = "ranker"
    k: int = 10
    floor: float = 0.5
    batch: int = 2000
    grid: tuple[float, ...] = GRID
    splits: frozenset[str] = EVAL_SPLITS
    baseline: BaselineConfig = field(default_factory=BaselineConfig)


@dataclass(slots=True)
class TwinContext:
    required: RequiredAttributes
    lexicon: Lexicon
    names: frozenset[str]
    segments: Segments
    data: TwinIndexData


@dataclass(slots=True)
class TwinModel:
    context: TwinContext
    threshold: float
    curve: list[CurvePoint]
    tuning: TuningLog


class RunTwins:
    def __init__(
        self, source: TwinSource, index: TitleIndex, calibrator: Calibrator,
        sink: TwinPredictionSink, reports: ReportSink, logger: Logger,
    ) -> None:
        self._source = source
        self._index = index
        self._calibrator = calibrator
        self._sink = sink
        self._reports = reports
        self._logger = logger

    def prepare(self, config: TwinConfig) -> TwinModel:
        started = time.monotonic()
        context = self._context(config)
        self._index.fit(context.data.titles)
        self._logger.info("twin_index", entries=len(context.data.entries),
                          seconds=round(time.monotonic() - started))
        tuning = self._tune(context, config)
        threshold, curve = pick_threshold(tuning.pairs, config.grid)
        fit = [(p.similarity, p.twin_ok) for p in tuning.pairs if p.similarity >= 0 and p.has_gold]
        self._calibrator.fit([s for s, _ in fit], [ok for _, ok in fit])
        self._logger.info("twin_threshold", threshold=threshold)
        return TwinModel(context, threshold, curve, tuning)

    def run(self, config: TwinConfig) -> Mapping[str, object]:
        started = time.monotonic()
        model = self.prepare(config)
        context, threshold, tuning = model.context, model.threshold, model.tuning
        books, log, cards = self._evaluate(context, config, threshold)
        report = build_twin_report(
            books, cards=cards, entries=len(context.data.entries), threshold=threshold,
            curve=model.curve, tuning=tuning.summary(threshold),
            examples=tuning.examples(threshold), log=log,
            seconds=round(time.monotonic() - started, 1),
        )
        self._reports.write(report, render_twin_markdown(report))
        self._logger.info("twins_done", cards=cards, seconds=round(time.monotonic() - started))
        return report

    def _context(self, config: TwinConfig) -> TwinContext:
        records = self._source.required()
        names = frozenset(r.attribute for r in records) | extra_attributes() | {MODEL}
        lexicon = build_lexicon(self._source.train_values(names), config.baseline.lexicon)
        required = RequiredAttributes(records, lexicon)
        stats = self._source.category_stats()
        head = frozenset(sorted(stats, key=lambda c: -stats[c][0])[: config.baseline.head_categories])
        cards_of = {c: max(1, s[1]) for c, s in stats.items()}
        segments = Segments(head, self._source.seller_cards(), config.baseline, cards_of)
        builder = IndexBuilder(lexicon)
        train = frozenset({"train"})
        for batch in self._source.cards(train, config.batch):
            for card in batch:
                builder.add_card(card)
        for rows in self._source.gold_rows(train, names):
            builder.add_rows(rows)
        data = builder.build()
        return TwinContext(required, lexicon, names, segments, data)

    def _neighbors(
        self, context: TwinContext, cards: list[CardRecord], extractions: list[CardExtraction],
        picks: Sequence[Mapping[str, Pick]], config: TwinConfig,
    ) -> Iterator[dict[str, Transfer]]:
        queries = [query_of(c, p) for c, p in zip(cards, picks, strict=True)]
        found = self._index.neighbors([q.title for q in queries], config.k)
        entries = context.data.entries
        for card, query, hits, extraction, chosen in zip(cards, queries, found, extractions, picks,
                                                         strict=True):
            near = others([(entries[i], s) for i, s in hits], card.sku_id)
            slots = open_slots(extraction, chosen)
            yield vote(query, near, slots, config.floor) if query.title else {}

    def _tune(self, context: TwinContext, config: TwinConfig) -> TuningLog:
        log = TuningLog()
        val = frozenset({"val"})
        gold = self._source.gold_where(val, context.names, 1)
        for batch in self._source.cards(val, config.batch):
            extractions = [extract_card(c, context.required, context.lexicon,
                                        config.baseline.min_confidence) for c in batch]
            picks = [e.picks for e in extractions]
            for card, extraction, transfers in zip(
                    batch, extractions, self._neighbors(context, batch, extractions, picks, config),
                    strict=True):
                expected = _expected(gold.get(card.sku_id, ()), context.lexicon)
                model = expected.get(MODEL)
                for name in extraction.profiles:
                    log.add(PairRecord.of(name, expected.get(name), extraction.picks.get(name),
                                          transfers.get(name), model), card)
        return log

    def _evaluate(
        self, context: TwinContext, config: TwinConfig, threshold: float
    ) -> tuple[tuple[MetricsBook, MetricsBook, MetricsBook, MetricsBook], TwinLog, int]:
        books = (MetricsBook(weighted=False), MetricsBook(weighted=True),
                 MetricsBook(weighted=False), MetricsBook(weighted=True))
        records = self._source.stage_records(config.stage)
        gold = self._source.gold_where(config.splits, context.names, 1)
        log = TwinLog()
        cards = 0
        for batch in self._source.cards(config.splits, config.batch):
            extractions = [extract_card(c, context.required, context.lexicon,
                                        config.baseline.min_confidence) for c in batch]
            picks = [stage_picks(e, records.get(c.sku_id)) for c, e in zip(batch, extractions,
                                                                          strict=True)]
            found = self._neighbors(context, batch, extractions, picks, config)
            predictions = []
            for card, extraction, chosen, transfers in zip(batch, extractions, picks, found,
                                                            strict=True):
                truth = gold.get(card.sku_id, ())
                observe(card, with_picks(extraction, chosen), truth, context.required,
                        context.segments, (books[0], books[1]))
                kept = accepted(transfers, threshold)
                confidences = self._calibrator.transform([t.similarity for t in kept.values()]) \
                    if kept else []
                scored = {n: (t, round(float(c), 4)) for (n, t), c in zip(kept.items(), confidences,
                                                                          strict=True)}
                final = {**chosen, **{n: twin_pick(t, c) for n, (t, c) in scored.items()}}
                observe(card, with_picks(extraction, final), truth, context.required,
                        context.segments, (books[2], books[3]))
                log.add(card, scored, _expected(truth, context.lexicon))
                record = records.get(card.sku_id)
                predictions.append(TwinPrediction(record.raw if record else _empty(card), scored))
            self._sink.write(predictions)
            cards += len(batch)
            self._logger.info("twins_batch_done", cards=cards)
        self._sink.close()
        return books, log, cards


def _expected(gold: Sequence[GoldRecord], lexicon: Lexicon) -> dict[str, str]:
    return {g.attribute: canonical_key(g.value, g.unit, numeric_of(lexicon, g.attribute))
            for g in gold if g.value}


def _empty(card: CardRecord) -> dict[str, object]:
    return {"sku_id": card.sku_id, "category_id": card.category_id, "split": card.split,
            "confidence_calibrated": True, "attributes": {}, "review": {}}
