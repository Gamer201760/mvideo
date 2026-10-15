from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.domain.candidate import Candidate, Source
from app.domain.profile import AttributeProfile

BASE: dict[tuple[str, str], float] = {
    (Source.SELLER, "seller"): 0.55,
    (Source.KEY_VALUE, "description"): 0.55,
    (Source.KEY_VALUE, "title"): 0.55,
    (Source.DICTIONARY, "title"): 0.45,
    (Source.DICTIONARY, "description"): 0.3,
    (Source.DICTIONARY, "seller"): 0.25,
    (Source.NUMBER, "title"): 0.4,
    (Source.NUMBER, "description"): 0.25,
    (Source.NUMBER, "seller"): 0.2,
    (Source.TITLE_MODEL, "title"): 0.5,
}
AFFINITY_WEIGHT = 0.2
PRIOR_WEIGHT = 0.25
SELLER_FIT_WEIGHT = 0.15
AGREEMENT_BONUS = 0.08
SLOT_BONUS = 0.2
RAM_STEMS = frozenset({"опера", "ram"})
ROM_STEMS = frozenset({"встро", "rom", "накоп", "памят"})
MAX_CONFIDENCE = 0.99
MULTI_VALUE_SELLER = 0.3
LENGTH_BONUS = 0.03
MAX_LENGTH_BONUS = 0.15


@dataclass(frozen=True, slots=True)
class Pick:
    candidate: Candidate
    confidence: float
    sources: tuple[str, ...]


def slot_bonus(candidate: Candidate, profile: AttributeProfile) -> float:
    if candidate.slot < 0:
        return 0.0
    stems = set(profile.keywords)
    if stems & RAM_STEMS:
        return SLOT_BONUS if candidate.slot == 0 else -SLOT_BONUS
    if stems & ROM_STEMS:
        return SLOT_BONUS if candidate.slot == 1 else -SLOT_BONUS
    return 0.0


def candidate_score(candidate: Candidate, profile: AttributeProfile) -> float:
    base = BASE.get((candidate.source, candidate.zone), 0.2)
    if candidate.source == Source.SELLER and "/" in candidate.key:
        base = MULTI_VALUE_SELLER
    if candidate.source == Source.DICTIONARY:
        base += min(MAX_LENGTH_BONUS, LENGTH_BONUS * candidate.key.count(" "))
    return (
        base
        + AFFINITY_WEIGHT * candidate.affinity
        + PRIOR_WEIGHT * candidate.prior
        + SELLER_FIT_WEIGHT * candidate.seller_fit
        + slot_bonus(candidate, profile)
    )


def pick_values(
    candidates: Iterable[Candidate], profiles: Mapping[str, AttributeProfile]
) -> dict[str, Pick]:
    groups: dict[tuple[str, str], list[tuple[float, Candidate]]] = defaultdict(list)
    for c in candidates:
        groups[(c.attribute, c.key)].append((candidate_score(c, profiles[c.attribute]), c))
    best: dict[str, tuple[float, Pick]] = {}
    for (attribute, _), scored in groups.items():
        scored.sort(key=lambda item: (-item[0], item[1].start))
        top_score, top = scored[0]
        sources = tuple(sorted({c.source for _, c in scored}))
        score = top_score + AGREEMENT_BONUS * (len(sources) - 1)
        current = best.get(attribute)
        if current is None or score > current[0] or (
            score == current[0] and top.start < current[1].candidate.start
        ):
            confidence = round(max(0.01, min(MAX_CONFIDENCE, score)), 4)
            best[attribute] = (score, Pick(top, confidence, sources))
    return {attribute: pick for attribute, (_, pick) in best.items()}
