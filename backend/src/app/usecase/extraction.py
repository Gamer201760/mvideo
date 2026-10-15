from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.candidate import Candidate
from app.domain.card_text import CardText, build_card_text
from app.domain.extractors import extract_candidates
from app.domain.lexicon import Lexicon
from app.domain.profile import BRAND, TZ_REQUIRED, AttributeProfile
from app.domain.scoring import Pick, candidate_score, pick_values
from app.usecase.baseline_ports import (
    CandidateRow,
    CardPrediction,
    CardRecord,
    PredictedValue,
    RequiredRecord,
)

UNKNOWN_CATEGORY_ATTRIBUTES = (BRAND, "Цвет")


@dataclass(frozen=True, slots=True)
class CardExtraction:
    text: CardText
    profiles: Mapping[str, AttributeProfile]
    candidates: tuple[Candidate, ...]
    picks: Mapping[str, Pick]
    review: Mapping[str, Pick]


class RequiredAttributes:
    def __init__(self, records: Sequence[RequiredRecord], lexicon: Lexicon) -> None:
        weights: dict[int, dict[str, float]] = {}
        for r in records:
            weights.setdefault(r.category_id, {})[r.attribute] = r.weight
        for category, names in TZ_REQUIRED.items():
            current = weights.setdefault(category, {})
            fallback = sorted(current.values())[len(current) // 2] if current else 1.0
            for name in names:
                current.setdefault(name, fallback)
        self._weights = weights
        self._lexicon = lexicon

    @property
    def attributes(self) -> frozenset[str]:
        names = {a for w in self._weights.values() for a in w}
        return frozenset(names | set(UNKNOWN_CATEGORY_ATTRIBUTES))

    def weights(self, category: int | None) -> Mapping[str, float]:
        if category is None or category not in self._weights:
            return {a: 1.0 for a in UNKNOWN_CATEGORY_ATTRIBUTES}
        return self._weights[category]

    def profiles(self, category: int | None) -> dict[str, AttributeProfile]:
        known = self._lexicon.profiles
        return {a: known[a] for a in self.weights(category) if a in known}


def extract_card(
    card: CardRecord, required: RequiredAttributes, lexicon: Lexicon, min_confidence: float
) -> CardExtraction:
    text = build_card_text(card.title, card.description, card.seller_params)
    profiles = required.profiles(card.category_id)
    candidates = tuple(extract_candidates(text, profiles, lexicon, card.category_id))
    picks = pick_values(candidates, profiles)
    accepted = {n: p for n, p in picks.items() if p.confidence >= min_confidence}
    review = {n: p for n, p in picks.items() if p.confidence < min_confidence}
    return CardExtraction(text, profiles, candidates, accepted, review)


def _values(picks: Mapping[str, Pick]) -> tuple[PredictedValue, ...]:
    return tuple(
        PredictedValue(name, p.candidate.value, p.confidence, p.candidate.source, p.sources,
                       p.candidate.evidence, p.candidate.start, p.candidate.end)
        for name, p in sorted(picks.items())
    )


def prediction_of(card: CardRecord, extraction: CardExtraction) -> CardPrediction:
    return CardPrediction(card.sku_id, card.category_id, card.split, _values(extraction.picks),
                          _values(extraction.review))


def candidate_rows(card: CardRecord, extraction: CardExtraction) -> list[CandidateRow]:
    picked = [*extraction.picks.items(), *extraction.review.items()]
    chosen = {(n, p.candidate.key) for n, p in picked}
    return [
        CandidateRow(card.sku_id, c.attribute, c.key, c.value, c.evidence, c.start, c.end,
                     c.source, c.zone, round(c.affinity, 4), c.prior, c.seller_fit, c.slot,
                     round(candidate_score(c, extraction.profiles[c.attribute]), 4),
                     (c.attribute, c.key) in chosen)
        for c in extraction.candidates
    ]
