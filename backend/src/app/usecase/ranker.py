import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.calibration import ScoredPick, ThresholdPoint, best_threshold, threshold_curve
from app.domain.lexicon import Lexicon
from app.domain.metrics import MetricsBook
from app.domain.ranker_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from app.usecase.baseline import EVAL_SPLITS, BaselineConfig, Segments, extra_attributes, observe
from app.usecase.baseline_ports import CardPrediction, PredictionSink, ReportSink
from app.usecase.extraction import RequiredAttributes, prediction_of
from app.usecase.interface import Logger
from app.usecase.lexicon_builder import build_lexicon
from app.usecase.ranker_pass import (
    Scored,
    add_training_rows,
    baseline_picks,
    card_options,
    ranked_extraction,
    score_items,
)
from app.usecase.ranker_ports import Calibrator, FeatureTable, RankerSource, ScoreModel
from app.usecase.ranker_report import CalibrationLog, build_ranker_report, render_ranker_markdown

THRESHOLDS = tuple(round(0.05 * i, 2) for i in range(1, 20))


@dataclass(frozen=True, slots=True)
class RankerConfig:
    train_modulo: int = 4
    blind_modulo: int = 5
    blind_remainder: int = 1
    batch: int = 2000
    thresholds: tuple[float, ...] = THRESHOLDS
    baseline: BaselineConfig = field(default_factory=BaselineConfig)


@dataclass(slots=True)
class RankerContext:
    required: RequiredAttributes
    lexicon: Lexicon
    names: frozenset[str]
    segments: Segments


class RunRanker:
    def __init__(
        self, source: RankerSource, model: ScoreModel, calibrator: Calibrator,
        sink: PredictionSink, reports: ReportSink, logger: Logger,
        baseline_report: Mapping[str, object] | None = None,
        val_sink: PredictionSink | None = None,
    ) -> None:
        self._source = source
        self._model = model
        self._calibrator = calibrator
        self._sink = sink
        self._reports = reports
        self._logger = logger
        self._baseline_report = baseline_report
        self._val_sink = val_sink

    def run(self, config: RankerConfig) -> Mapping[str, object]:
        started = time.monotonic()
        context = self._context(config)
        train = self._train(context, config)
        self._model.fit(train, NUMERIC_FEATURES, CATEGORICAL_FEATURES)
        self._logger.info("ranker_fitted", rows=train.rows, seconds=round(time.monotonic() - started))
        threshold, curve = self._tune(context, config)
        plain, weighted, log, cards = self._evaluate(context, config, threshold)
        self._write_val(context, config, threshold)
        report = build_ranker_report(
            plain, weighted, cards=cards, lexicon_entries=context.lexicon.size,
            attributes=len(context.lexicon.profiles), train=train, threshold=threshold, curve=curve,
            calibration=log, importances=self._model.importances(),
            baseline=self._baseline_report, seconds=round(time.monotonic() - started, 1),
        )
        self._reports.write(report, render_ranker_markdown(report))
        self._logger.info("ranker_done", cards=cards, seconds=round(time.monotonic() - started))
        return report

    def _context(self, config: RankerConfig) -> RankerContext:
        return ranker_context(self._source, config)

    def _scored(
        self, context: RankerContext, splits: frozenset[str], config: RankerConfig, simulate: bool
    ) -> Iterator[list[Scored]]:
        return scored_batches(self._source, self._model, context, splits, config, simulate)

    def _write_val(self, context: RankerContext, config: RankerConfig, threshold: float) -> None:
        if self._val_sink is None:
            return
        for scored_batch in self._scored(context, frozenset({"val"}), config, simulate=True):
            self._val_sink.write(calibrated_predictions(scored_batch, self._calibrator, threshold),
                                 [])
        self._val_sink.close()

    def _train(self, context: RankerContext, config: RankerConfig) -> FeatureTable:
        table = FeatureTable(len(NUMERIC_FEATURES))
        splits = frozenset({"train"})
        gold = self._source.gold_where(splits, context.names, config.train_modulo)
        for batch in self._source.cards(splits, config.batch):
            for card in batch:
                if card.sku_id % config.train_modulo == 0:
                    item = card_options(card, gold.get(card.sku_id, ()), context.required,
                                        context.lexicon, _blind(card.sku_id, config))
                    add_training_rows(table, item)
            self._logger.info("ranker_train_rows", rows=table.rows)
        return table

    def _tune(self, context: RankerContext, config: RankerConfig) -> tuple[float, list[ThresholdPoint]]:
        picks: list[tuple[float, bool, bool]] = []
        pairs = gold = 0
        for scored_batch in self._scored(context, frozenset({"val"}), config, simulate=True):
            for scored in scored_batch:
                expected = scored.item.expected
                pairs += len(scored.item.extraction.profiles)
                gold += len(expected)
                for name, choice in scored.choices.items():
                    truth = expected.get(name)
                    picks.append((choice.raw, truth is not None, choice.option.key == truth))
        judged = [(raw, ok) for raw, has, ok in picks if has]
        self._calibrator.fit([r for r, _ in judged], [ok for _, ok in judged])
        calibrated = self._calibrator.transform([raw for raw, _, _ in picks])
        scored_picks = [ScoredPick(c, has, ok) for c, (_, has, ok) in zip(calibrated, picks,
                                                                          strict=True)]
        curve = threshold_curve(scored_picks, gold, pairs, config.thresholds)
        best = best_threshold(curve)
        self._logger.info("ranker_threshold", threshold=best.threshold, f1=round(best.f1, 4))
        return best.threshold, curve

    def _evaluate(
        self, context: RankerContext, config: RankerConfig, threshold: float
    ) -> tuple[MetricsBook, MetricsBook, CalibrationLog, int]:
        plain, weighted = MetricsBook(weighted=False), MetricsBook(weighted=True)
        log = CalibrationLog()
        cards = 0
        gold = self._source.gold_where(EVAL_SPLITS, context.names, 1)
        for scored_batch in self._scored(context, EVAL_SPLITS, config, simulate=False):
            raws = [c.raw for s in scored_batch for c in s.choices.values()]
            calibrated = iter(self._calibrator.transform(raws) if raws else [])
            predictions = []
            for scored in scored_batch:
                confidences = {name: float(next(calibrated)) for name in scored.choices}
                extraction = ranked_extraction(scored, confidences, threshold)
                card = scored.item.card
                observe(card, extraction, gold.get(card.sku_id, ()), context.required,
                        context.segments, (plain, weighted))
                predictions.append(prediction_of(card, extraction))
                log.add(scored, confidences, baseline_picks(scored.item))
            self._sink.write(predictions, [])
            cards += len(scored_batch)
            self._logger.info("ranker_batch_done", cards=cards)
        self._sink.close()
        return plain, weighted, log, cards


def ranker_context(source: RankerSource, config: RankerConfig) -> RankerContext:
    records = source.required()
    names = frozenset(r.attribute for r in records) | extra_attributes()
    lexicon = build_lexicon(source.train_values(names), config.baseline.lexicon)
    required = RequiredAttributes(records, lexicon)
    stats = source.category_stats()
    head = frozenset(sorted(stats, key=lambda c: -stats[c][0])[: config.baseline.head_categories])
    cards_of = {c: max(1, s[1]) for c, s in stats.items()}
    segments = Segments(head, source.seller_cards(), config.baseline, cards_of)
    return RankerContext(required, lexicon, names, segments)


def scored_batches(
    source: RankerSource, model: ScoreModel, context: RankerContext,
    splits: frozenset[str] | None, config: RankerConfig, simulate: bool,
) -> Iterator[list[Scored]]:
    gold = source.gold_where(splits, context.names, 1) if splits is not None else {}
    for batch in source.cards(splits, config.batch):
        items = [card_options(c, gold.get(c.sku_id, ()), context.required, context.lexicon,
                              simulate and _blind(c.sku_id, config))
                 for c in batch]
        yield score_items(items, model)


def calibrated_predictions(
    scored_batch: Sequence[Scored], calibrator: Calibrator, threshold: float
) -> list[CardPrediction]:
    raws = [c.raw for s in scored_batch for c in s.choices.values()]
    calibrated = iter(calibrator.transform(raws) if raws else [])
    predictions = []
    for scored in scored_batch:
        confidences = {name: float(next(calibrated)) for name in scored.choices}
        extraction = ranked_extraction(scored, confidences, threshold)
        predictions.append(prediction_of(scored.item.card, extraction))
    return predictions


def _blind(sku_id: int, config: RankerConfig) -> bool:
    return sku_id % config.blind_modulo == config.blind_remainder
