from collections.abc import Sequence

from app.domain.attribute_flow import CatalogCandidate
from app.domain.lexicon import LexiconEntry, value_tokens
from app.domain.profile import AttributeProfile, Kind, name_keywords
from app.usecase.baseline_ports import RequiredRecord
from app.usecase.stand_ports import StandCategory, StandExample, StandPack


def catalog_pack(
    categories: Sequence[CatalogCandidate],
    *,
    built_at: str,
    threshold: float,
    examples: Sequence[StandExample],
) -> StandPack:
    profiles = {
        f.attribute: AttributeProfile(f.attribute, Kind(f.kind), f.unit, name_keywords(f.attribute))
        for c in categories
        for f in c.fields
    }
    entries = tuple(
        LexiconEntry(f.attribute, value_tokens(v), profiles[f.attribute].value_key(v), v)
        for c in categories
        for f in c.fields
        for v in f.values
    )
    return StandPack(
        built_at=built_at,
        threshold=threshold,
        profiles=profiles,
        entries=entries,
        priors={},
        required=tuple(
            RequiredRecord(c.category_id, f.attribute, 1.0) for c in categories for f in c.fields
        ),
        categories=tuple(
            StandCategory(
                category_id=c.category_id,
                name=c.path.split("/")[-1].strip(),
                path=c.path,
            )
            for c in categories
        ),
        examples=examples,
    )
