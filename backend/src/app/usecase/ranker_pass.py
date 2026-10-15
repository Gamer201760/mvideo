from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from app.domain.lexicon import Lexicon
from app.domain.ranker_features import NUMERIC_FEATURES, RankOption, rank_options
from app.domain.scoring import Pick
from app.domain.values import canonical_key
from app.usecase.baseline_ports import CardRecord, GoldRecord
from app.usecase.extraction import CardExtraction, RequiredAttributes, extract_card
from app.usecase.ranker_ports import FeatureTable, ScoreModel

BASELINE_MIN_CONFIDENCE = 0.35


@dataclass(frozen=True, slots=True)
class CardOptions:
    card: CardRecord
    extraction: CardExtraction
    options: tuple[RankOption, ...]
    expected: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Choice:
    option: RankOption
    raw: float


@dataclass(frozen=True, slots=True)
class Scored:
    item: CardOptions
    choices: Mapping[str, Choice]


def card_options(
    card: CardRecord, gold: Sequence[GoldRecord], required: RequiredAttributes, lexicon: Lexicon,
    blind: bool = False,
) -> CardOptions:
    extraction = extract_card(card, required, lexicon, 0.0)
    if blind:
        candidates = tuple(replace(c, prior=0.0) for c in extraction.candidates)
        known: frozenset[str] = frozenset()
    else:
        candidates = extraction.candidates
        known = frozenset(a for a in extraction.profiles
                          if lexicon.category_values(card.category_id, a))
    options = rank_options(candidates, extraction.profiles, len(extraction.text.text), known)
    expected = {
        g.attribute: canonical_key(g.value, g.unit, extraction.profiles[g.attribute].numeric)
        for g in gold
        if g.attribute in extraction.profiles and g.value
    }
    return CardOptions(card, extraction, tuple(options), expected)


def add_training_rows(table: FeatureTable, item: CardOptions) -> None:
    for option in item.options:
        truth = item.expected.get(option.attribute)
        if truth is not None:
            table.add(option.numeric, option.categorical, 1 if option.key == truth else 0)


def score_items(items: Sequence[CardOptions], model: ScoreModel) -> list[Scored]:
    table = FeatureTable(len(NUMERIC_FEATURES))
    for item in items:
        for option in item.options:
            table.add(option.numeric, option.categorical, 0)
    scores = list(model.predict(table)) if table.rows else []
    result: list[Scored] = []
    position = 0
    for item in items:
        best: dict[str, Choice] = {}
        for option in item.options:
            raw = float(scores[position])
            position += 1
            current = best.get(option.attribute)
            if current is None or raw > current.raw:
                best[option.attribute] = Choice(option, raw)
        result.append(Scored(item, best))
    return result


def baseline_picks(item: CardOptions) -> Mapping[str, Pick]:
    return {n: p for n, p in item.extraction.picks.items()
            if p.confidence >= BASELINE_MIN_CONFIDENCE}


def ranked_extraction(
    scored: Scored, confidences: Mapping[str, float], threshold: float
) -> CardExtraction:
    picks: dict[str, Pick] = {}
    review: dict[str, Pick] = {}
    for name, choice in scored.choices.items():
        confidence = round(confidences[name], 4)
        pick = Pick(choice.option.candidate, confidence, choice.option.sources)
        (picks if confidence >= threshold else review)[name] = pick
    return replace(scored.item.extraction, picks=picks, review=review)
