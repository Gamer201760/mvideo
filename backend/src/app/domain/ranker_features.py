from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.domain.candidate import Candidate, Source
from app.domain.profile import AttributeProfile, Kind
from app.domain.scoring import AGREEMENT_BONUS, candidate_score, slot_bonus

SOURCES = (Source.KEY_VALUE, Source.SELLER, Source.DICTIONARY, Source.NUMBER, Source.TITLE_MODEL)
ZONES = ("title", "description", "seller")
KINDS = (Kind.NUMERIC, Kind.CATEGORICAL, Kind.BOOLEAN, Kind.FREE)
NUMERIC_FEATURES = (
    "heuristic", "agreement", "candidates", "sources",
    *(f"source_{s}" for s in SOURCES),
    *(f"zone_{z}" for z in ZONES),
    *(f"kind_{k.value}" for k in KINDS),
    "affinity_max", "prior_max", "seller_fit_max", "seller_fit_min", "slot_bonus",
    "first_position", "in_title_first", "key_chars", "key_tokens", "evidence_chars",
    "options", "heuristic_rank", "heuristic_gap", "candidate_share", "prior_known",
)
CATEGORICAL_FEATURES = ("attribute", "top_source", "top_zone")


@dataclass(frozen=True, slots=True)
class RankOption:
    attribute: str
    key: str
    candidate: Candidate
    sources: tuple[str, ...]
    heuristic: float
    numeric: tuple[float, ...]
    categorical: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Group:
    attribute: str
    key: str
    scored: list[tuple[float, Candidate]]


def _groups(
    candidates: Iterable[Candidate], profiles: Mapping[str, AttributeProfile]
) -> dict[str, list[_Group]]:
    by_key: dict[tuple[str, str], list[tuple[float, Candidate]]] = defaultdict(list)
    for c in candidates:
        by_key[(c.attribute, c.key)].append((candidate_score(c, profiles[c.attribute]), c))
    by_attribute: dict[str, list[_Group]] = defaultdict(list)
    for (attribute, key), scored in by_key.items():
        scored.sort(key=lambda item: (-item[0], item[1].start))
        by_attribute[attribute].append(_Group(attribute, key, scored))
    return by_attribute


def _flags(values: set[str], names: Iterable[str]) -> list[float]:
    return [1.0 if n in values else 0.0 for n in names]


def _option(
    group: _Group, profile: AttributeProfile, rank: int, best: float, total: int, options: int,
    text_length: int, known: bool,
) -> RankOption:
    top_score, top = group.scored[0]
    members = [c for _, c in group.scored]
    sources = tuple(sorted({c.source for c in members}))
    agreement = top_score + AGREEMENT_BONUS * (len(sources) - 1)
    first = min(c.start for c in members)
    numeric = (
        top_score, agreement, float(len(members)), float(len(sources)),
        *_flags(set(sources), SOURCES),
        *_flags({c.zone for c in members}, ZONES),
        *_flags({profile.kind.value}, (k.value for k in KINDS)),
        max(c.affinity for c in members), max(c.prior for c in members),
        float(max(c.seller_fit for c in members)), float(min(c.seller_fit for c in members)),
        max(slot_bonus(c, profile) for c in members),
        first / max(1, text_length), 1.0 if top.zone == "title" else 0.0,
        float(len(group.key)), float(group.key.count(" ") + 1), float(len(top.evidence)),
        float(options), float(rank), best - agreement, len(members) / max(1, total),
        1.0 if known else 0.0,
    )
    return RankOption(group.attribute, group.key, top, sources, agreement, numeric,
                      (group.attribute, top.source, top.zone))


def rank_options(
    candidates: Iterable[Candidate], profiles: Mapping[str, AttributeProfile], text_length: int,
    known: frozenset[str] = frozenset(),
) -> list[RankOption]:
    result: list[RankOption] = []
    for attribute, groups in _groups(candidates, profiles).items():
        profile = profiles[attribute]
        total = sum(len(g.scored) for g in groups)
        agreements = [
            g.scored[0][0] + AGREEMENT_BONUS * (len({c.source for _, c in g.scored}) - 1)
            for g in groups
        ]
        order = sorted(range(len(groups)), key=lambda i: (-agreements[i], groups[i].scored[0][1].start))
        best = agreements[order[0]]
        for rank, index in enumerate(order):
            result.append(_option(groups[index], profile, rank, best, total, len(groups),
                                  text_length, attribute in known))
    return result
