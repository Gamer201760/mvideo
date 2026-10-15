import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from app.domain.calibration import (
    ScoredPick,
    ThresholdPoint,
    best_threshold,
    expected_calibration_error,
    reliability,
    threshold_curve,
)
from app.domain.fusion import SOURCES, FusionRules, RuleBook, resolve
from app.domain.metrics import MetricsBook
from app.domain.scoring import Pick
from app.usecase.baseline import EVAL_SPLITS, observe
from app.usecase.final_options import CardSlots, FinalSource, StageSet, card_slots
from app.usecase.final_report import build_final_report
from app.usecase.final_stages import STAGES, fused_picks, stage_picks_of
from app.usecase.interface import Logger
from app.usecase.ranker import RankerConfig, RankerContext, ranker_context
from app.usecase.ranker_ports import Calibrator
from app.usecase.twin_pass import with_picks

THRESHOLDS = (0.0, *(round(0.05 * i, 2) for i in range(1, 20)))
DECISION_GROUP = "sample:decision"


@dataclass(frozen=True, slots=True)
class FinalConfig:
    ranker_val: str = "ranker_final_val"
    ranker_eval: str = "ranker_final"
    decision_val: str = "decision_jev_val_final"
    decision_eval: str = "decision_jev"
    twins: str = "twins_final"
    batch: int = 2000
    thresholds: tuple[float, ...] = THRESHOLDS
    ranker: RankerConfig = field(default_factory=RankerConfig)


@dataclass(frozen=True, slots=True)
class _Slot:
    attribute: str
    mode: str
    options: Mapping[str, str | None]
    confidences: Mapping[str, float]
    truth: str | None


@dataclass(slots=True)
class FusionModel:
    rules: FusionRules
    calibrators: dict[str, Calibrator]
    threshold: float
    curve: list[ThresholdPoint]

    def calibrate(self, source: str, confidence: float) -> float:
        return round(float(self.calibrators[source].transform([confidence])[0]), 4)


class RunFinal:
    def __init__(
        self, source: FinalSource, calibrator: Callable[[], Calibrator], logger: Logger
    ) -> None:
        self._source = source
        self._calibrator = calibrator
        self._logger = logger

    def run(self, config: FinalConfig) -> tuple[dict[str, object], FusionModel]:
        started = time.monotonic()
        context = ranker_context(self._source, config.ranker)
        model = self._fit(context, config)
        self._logger.info("final_fitted", threshold=model.threshold,
                          specific=len(model.rules.specific), seconds=round(time.monotonic() - started))
        books, picks, sources, cards = self._evaluate(context, config, model)
        table = reliability([c for c, _ in picks], [ok for _, ok in picks])
        report = build_final_report(
            books, model.rules, threshold=model.threshold, val_curve=model.curve, cards=cards,
            reliability=table, ece=expected_calibration_error(table), sources=sources,
            seconds=round(time.monotonic() - started, 1),
        )
        return report, model

    def _stages(self, ranker: str, decision: str, twins: str) -> StageSet:
        return StageSet(self._source.stage_records(ranker), self._source.stage_records(decision),
                        self._source.stage_records(twins))

    def _fit(self, context: RankerContext, config: FinalConfig) -> FusionModel:
        stages = self._stages(config.ranker_val, config.decision_val, config.twins)
        val = frozenset({"val"})
        gold = self._source.gold_where(val, context.names, 1)
        book, slots = RuleBook(), []
        for batch in self._source.cards(val, config.batch):
            for card in batch:
                blind = card.sku_id % config.ranker.blind_modulo == config.ranker.blind_remainder
                item = card_slots(card, gold.get(card.sku_id, ()), context.required,
                                  context.lexicon, stages, blind)
                for name in item.extraction.profiles:
                    options, truth = item.options(name), item.expected.get(name)
                    if truth is not None:
                        book.add(name, item.mode, options, truth)
                    confidences = {s: p.confidence for s, p in item.picks.get(name, {}).items()
                                   if p is not None}
                    slots.append(_Slot(name, item.mode, options, confidences, truth))
        rules = book.choose()
        calibrators = self._calibrators(slots)
        model = FusionModel(rules, calibrators, 0.0, [])
        scored = []
        for slot in slots:
            chosen = resolve(slot.options, rules.rule(slot.attribute, slot.mode))
            if chosen is not None:
                confidence = model.calibrate(chosen, slot.confidences[chosen])
                scored.append(ScoredPick(confidence, slot.truth is not None,
                                         slot.options[chosen] == slot.truth))
        gold_pairs = sum(1 for s in slots if s.truth is not None)
        model.curve = threshold_curve(scored, gold_pairs, len(slots), config.thresholds)
        model.threshold = best_threshold(model.curve).threshold
        return model

    def _calibrators(self, slots: list[_Slot]) -> dict[str, Calibrator]:
        fitted: dict[str, Calibrator] = {}
        for source in SOURCES:
            pairs = [(s.confidences[source], s.options[source] == s.truth) for s in slots
                     if s.truth is not None and source in s.confidences]
            calibrator = self._calibrator()
            if pairs:
                calibrator.fit([c for c, _ in pairs], [ok for _, ok in pairs])
            else:
                calibrator.fit([0.0, 1.0], [False, True])
            fitted[source] = calibrator
        return fitted

    def _evaluate(
        self, context: RankerContext, config: FinalConfig, model: FusionModel
    ) -> tuple[dict[str, tuple[MetricsBook, MetricsBook]], list[tuple[float, bool]],
               dict[str, int], int]:
        stages = self._stages(config.ranker_eval, config.decision_eval, config.twins)
        books = {s: (MetricsBook(weighted=False), MetricsBook(weighted=True)) for s in STAGES}
        gold = self._source.gold_where(EVAL_SPLITS, context.names, 1)
        fused_scores: list[tuple[float, bool]] = []
        sources: Counter[str] = Counter()
        cards = 0
        for batch in self._source.cards(EVAL_SPLITS, config.batch):
            for card in batch:
                truth = gold.get(card.sku_id, ())
                item = card_slots(card, truth, context.required, context.lexicon, stages, False)
                extra = [DECISION_GROUP] if item.decided else []
                for stage in STAGES:
                    picks = (fused_picks(item, model.rules, model.calibrate, model.threshold)
                             if stage == STAGES[-1] else stage_picks_of(item, stage))
                    observe(card, with_picks(item.extraction, _plain(picks)), truth,
                            context.required, context.segments, books[stage], extra)
                    if stage == STAGES[-1]:
                        _collect(item, picks, fused_scores, sources)
            cards += len(batch)
            self._logger.info("final_eval_batch", cards=cards)
        return books, fused_scores, dict(sources), cards


def _plain(picks: Mapping[str, tuple[str, Pick]]) -> dict[str, Pick]:
    return {name: pick for name, (_, pick) in picks.items()}


def _collect(
    item: CardSlots, picks: Mapping[str, tuple[str, Pick]], scores: list[tuple[float, bool]],
    sources: Counter[str],
) -> None:
    for name, (source, pick) in picks.items():
        sources[source] += 1
        truth = item.expected.get(name)
        if truth is not None:
            scores.append((pick.confidence, pick.candidate.key == truth))

