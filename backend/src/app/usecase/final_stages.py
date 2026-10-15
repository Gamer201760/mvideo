from collections.abc import Callable, Mapping
from dataclasses import replace

from app.domain.fusion import BASELINE, DECISION, RANKER, TWIN, FusionRules, resolve
from app.domain.scoring import Pick
from app.usecase.final_options import CardSlots

STAGES = ("baseline", "ranker", "ranker+decision", "ranker+decision+twins", "fused")

StagePicks = dict[str, tuple[str, Pick]]


def _ranker_decision(options: Mapping[str, Pick | None]) -> tuple[str, Pick | None]:
    if DECISION in options:
        return DECISION, options[DECISION]
    return RANKER, options.get(RANKER)


def _slot_pick(options: Mapping[str, Pick | None], stage: str) -> tuple[str, Pick | None]:
    if stage == "baseline":
        return BASELINE, options.get(BASELINE)
    if stage == "ranker":
        return RANKER, options.get(RANKER)
    source, pick = _ranker_decision(options)
    if pick is None and stage == "ranker+decision+twins":
        return TWIN, options.get(TWIN)
    return source, pick


def stage_picks_of(item: CardSlots, stage: str) -> StagePicks:
    picks: StagePicks = {}
    for name, options in item.picks.items():
        source, pick = _slot_pick(options, stage)
        if pick is not None:
            picks[name] = (source, pick)
    return picks


def fused_picks(
    item: CardSlots, rules: FusionRules, calibrate: Callable[[str, float], float],
    threshold: float,
) -> StagePicks:
    picks: StagePicks = {}
    for name in item.extraction.profiles:
        source = resolve(item.options(name), rules.rule(name, item.mode))
        if source is None:
            continue
        pick = item.picks[name][source]
        if pick is None:
            continue
        confidence = calibrate(source, pick.confidence)
        if confidence >= threshold:
            picks[name] = (source, replace(pick, confidence=confidence))
    return picks
