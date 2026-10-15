from collections.abc import Callable
from dataclasses import dataclass, replace

from app.domain.fusion import BASELINE, KNOWN, NEW, RANKER, TWIN, FusionRules, resolve
from app.domain.profile import BRAND
from app.domain.ranker_features import NUMERIC_FEATURES, rank_options
from app.domain.scoring import Pick
from app.usecase.extraction import CardExtraction
from app.usecase.ranker_ports import Calibrator, FeatureTable, ScoreModel
from app.usecase.stand_twins import StandTwins


@dataclass(frozen=True, slots=True)
class FusionPolicy:
    rules: FusionRules
    calibrate: Callable[[str, float], float]
    threshold: float


class FusedChooser:
    def __init__(self, model: ScoreModel, ranker_calibrator: Calibrator, ranker_threshold: float,
                 policy: FusionPolicy, twins: StandTwins | None = None) -> None:
        self._model = model
        self._ranker_calibrator = ranker_calibrator
        self._ranker_threshold = ranker_threshold
        self._policy = policy
        self._twins = twins

    async def choose(self, extraction: CardExtraction, threshold: float, category_id: int | None,
                     known: frozenset[str]) -> CardExtraction:
        ranked = self._ranked(extraction, known)
        open_slots = [n for n in extraction.profiles if n not in ranked]
        twins = self._twins.picks(extraction, open_slots, ranked.get(BRAND)) \
            if self._twins is not None else {}
        mode = NEW if category_id is None else KNOWN
        picks: dict[str, Pick] = {}
        review: dict[str, Pick] = {}
        for name in extraction.profiles:
            by_source = {BASELINE: extraction.picks.get(name), RANKER: ranked.get(name),
                         TWIN: twins.get(name)}
            options = {s: p.candidate.key for s, p in by_source.items() if p is not None}
            source = resolve(options, self._policy.rules.rule(name, mode))
            fallback = extraction.review.get(name)
            if source is None:
                if fallback is not None:
                    review[name] = fallback
                continue
            pick = by_source[source]
            if pick is None:
                continue
            confidence = self._policy.calibrate(source, pick.confidence)
            fused = replace(pick, confidence=confidence, sources=(*pick.sources, source))
            (picks if confidence >= self._policy.threshold else review)[name] = fused
        return replace(extraction, picks=picks, review=review)

    def _ranked(self, extraction: CardExtraction, known: frozenset[str]) -> dict[str, Pick]:
        options = rank_options(extraction.candidates, extraction.profiles,
                               len(extraction.text.text), known)
        if not options:
            return {}
        table = FeatureTable(len(NUMERIC_FEATURES))
        for option in options:
            table.add(option.numeric, option.categorical, 0)
        scores = self._model.predict(table)
        best: dict[str, tuple[float, Pick]] = {}
        for option, raw in zip(options, scores, strict=True):
            current = best.get(option.attribute)
            if current is None or raw > current[0]:
                best[option.attribute] = (float(raw), Pick(option.candidate, 0.0, option.sources))
        raws = [raw for raw, _ in best.values()]
        calibrated = self._ranker_calibrator.transform(raws)
        return {name: replace(pick, confidence=round(float(c), 4))
                for (name, (_, pick)), c in zip(best.items(), calibrated, strict=True)
                if c >= self._ranker_threshold}
