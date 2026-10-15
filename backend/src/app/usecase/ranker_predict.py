import time
from dataclasses import replace

from app.usecase.baseline_ports import CardPrediction, PredictionSink
from app.usecase.extraction import prediction_of
from app.usecase.interface import Logger
from app.usecase.ranker import RankerConfig, calibrated_predictions, ranker_context, scored_batches
from app.usecase.ranker_pass import BASELINE_MIN_CONFIDENCE, Scored
from app.usecase.ranker_ports import Calibrator, RankerSource, ScoreModel


class PredictRanker:
    def __init__(
        self, source: RankerSource, model: ScoreModel, calibrator: Calibrator,
        sink: PredictionSink, baseline_sink: PredictionSink, logger: Logger,
    ) -> None:
        self._source = source
        self._model = model
        self._calibrator = calibrator
        self._sink = sink
        self._baseline_sink = baseline_sink
        self._logger = logger

    def run(self, config: RankerConfig, threshold: float, splits: frozenset[str] | None) -> int:
        started = time.monotonic()
        context = ranker_context(self._source, config)
        cards = 0
        for scored_batch in scored_batches(self._source, self._model, context, splits, config,
                                           simulate=False):
            self._sink.write(calibrated_predictions(scored_batch, self._calibrator, threshold), [])
            self._baseline_sink.write([_baseline(s) for s in scored_batch], [])
            cards += len(scored_batch)
            self._logger.info("ranker_predict_batch", cards=cards,
                              seconds=round(time.monotonic() - started))
        self._sink.close()
        self._baseline_sink.close()
        return cards


def _baseline(scored: Scored) -> CardPrediction:
    extraction = scored.item.extraction
    picks = {n: p for n, p in extraction.picks.items() if p.confidence >= BASELINE_MIN_CONFIDENCE}
    review = {n: p for n, p in extraction.picks.items() if p.confidence < BASELINE_MIN_CONFIDENCE}
    return prediction_of(scored.item.card, replace(extraction, picks=picks, review=review))
