from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from app.domain.fusion import BASELINE, DECISION, KNOWN, NEW, RANKER, TWIN, Options
from app.domain.lexicon import Lexicon
from app.domain.scoring import Pick, pick_values
from app.domain.twin import TWIN_SOURCE
from app.domain.values import canonical_key
from app.usecase.baseline_ports import CardRecord, GoldRecord
from app.usecase.extraction import CardExtraction, RequiredAttributes, extract_card
from app.usecase.ranker_pass import BASELINE_MIN_CONFIDENCE
from app.usecase.ranker_ports import RankerSource
from app.usecase.twin_pass import stage_picks
from app.usecase.twin_ports import StageRecord

DECISION_MARK = "decision"
NEW_CATEGORY_SPLIT = "new_category"

StageRecords = Mapping[int, StageRecord]


class FinalSource(RankerSource, Protocol):
    def stage_records(self, name: str) -> Mapping[int, StageRecord]: ...


@dataclass(frozen=True, slots=True)
class StageSet:
    ranker: StageRecords
    decision: StageRecords
    twin: StageRecords


@dataclass(frozen=True, slots=True)
class CardSlots:
    card: CardRecord
    extraction: CardExtraction
    mode: str
    picks: Mapping[str, Mapping[str, Pick | None]]
    expected: Mapping[str, str]
    decided: bool

    def options(self, attribute: str) -> Options:
        return {s: (p.candidate.key if p is not None else None)
                for s, p in self.picks.get(attribute, {}).items()}


def card_mode(card: CardRecord) -> str:
    return NEW if card.category_id is None or card.split == NEW_CATEGORY_SPLIT else KNOWN


def card_slots(
    card: CardRecord, gold: Sequence[GoldRecord], required: RequiredAttributes, lexicon: Lexicon,
    stages: StageSet, blind: bool,
) -> CardSlots:
    extraction = extract_card(card, required, lexicon, 0.0)
    plain = _accepted(extraction.picks)
    baseline = _accepted(_blind_picks(extraction)) if blind else plain
    by_source: dict[str, Mapping[str, Pick | None]] = {
        BASELINE: baseline,
        RANKER: stage_picks(extraction, stages.ranker.get(card.sku_id)),
        TWIN: _twin(extraction, stages.twin.get(card.sku_id)),
    }
    decision_record = stages.decision.get(card.sku_id)
    if decision_record is not None:
        by_source[DECISION] = _decision(extraction, decision_record, plain)
    picks: dict[str, dict[str, Pick | None]] = {}
    for source, chosen in by_source.items():
        for name, pick in chosen.items():
            if name in extraction.profiles:
                picks.setdefault(name, {})[source] = pick
    expected = {
        g.attribute: canonical_key(g.value, g.unit, extraction.profiles[g.attribute].numeric)
        for g in gold if g.attribute in extraction.profiles and g.value
    }
    mode = NEW if blind else card_mode(card)
    return CardSlots(card, extraction, mode, picks, expected, decision_record is not None)


def _accepted(picks: Mapping[str, Pick]) -> dict[str, Pick]:
    return {n: p for n, p in picks.items() if p.confidence >= BASELINE_MIN_CONFIDENCE}


def _blind_picks(extraction: CardExtraction) -> dict[str, Pick]:
    blind = tuple(replace(c, prior=0.0) for c in extraction.candidates)
    return pick_values(blind, extraction.profiles)


def _twin(extraction: CardExtraction, record: StageRecord | None) -> dict[str, Pick]:
    if record is None:
        return {}
    picks = stage_picks(extraction, record)
    return {n: p for n, p in picks.items() if record.values[n].source == TWIN_SOURCE}


def _decision(
    extraction: CardExtraction, record: StageRecord, baseline: Mapping[str, Pick]
) -> dict[str, Pick | None]:
    picks = stage_picks(extraction, record)
    chosen: dict[str, Pick | None] = {
        n: p for n, p in picks.items() if DECISION_MARK in record.values[n].sources}
    for name in baseline:
        if name not in record.values:
            chosen[name] = None
    return chosen
