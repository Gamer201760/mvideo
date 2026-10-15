from collections.abc import Mapping
from dataclasses import dataclass, replace

from app.domain.catalog import BRAND, MODEL, is_service_attribute

MENTION_SMOOTHING = 0.01


@dataclass(frozen=True, slots=True)
class CategoryUsage:
    category_id: int
    cards: int
    clicks: int
    query_clicks: int


@dataclass(frozen=True, slots=True)
class AttributeUsage:
    attribute: str
    cards: int
    clicks: int


@dataclass(frozen=True, slots=True)
class RequiredAttribute:
    category_id: int
    attribute: str
    rank: int
    card_coverage: float
    click_coverage: float
    query_share: float
    category_clicks: int
    weight: float


def coverage(usage: AttributeUsage, category: CategoryUsage) -> tuple[float, float]:
    cards = usage.cards / category.cards if category.cards else 0.0
    clicks = usage.clicks / category.clicks if category.clicks else cards
    return cards, clicks


def candidate_attributes(
    usages: Mapping[str, AttributeUsage], category: CategoryUsage, limit: int
) -> list[str]:
    ranked = sorted(
        (u for u in usages.values() if not is_service_attribute(u.attribute)),
        key=lambda u: (-coverage(u, category)[1], -u.cards, u.attribute),
    )
    fixed = [a for a in (BRAND, MODEL) if a in usages]
    return fixed + [u.attribute for u in ranked[:limit]]


def rank_required(
    category: CategoryUsage,
    usages: Mapping[str, AttributeUsage],
    mention_clicks: Mapping[str, int],
    top_n: int,
    min_coverage: float,
) -> list[RequiredAttribute]:
    def build(usage: AttributeUsage, rank: int) -> RequiredAttribute:
        card_cov, click_cov = coverage(usage, category)
        share = (
            mention_clicks.get(usage.attribute, 0) / category.query_clicks
            if category.query_clicks
            else 0.0
        )
        return RequiredAttribute(
            category_id=category.category_id,
            attribute=usage.attribute,
            rank=rank,
            card_coverage=round(card_cov, 4),
            click_coverage=round(click_cov, 4),
            query_share=round(share, 6),
            category_clicks=category.clicks,
            weight=round(category.clicks * (MENTION_SMOOTHING + share), 4),
        )

    fixed = [build(usages[a], 0) for a in (BRAND, MODEL) if a in usages]
    rest = sorted(
        (
            build(usages[a], 0)
            for a in candidate_attributes(usages, category, len(usages))
            if a not in (BRAND, MODEL) and coverage(usages[a], category)[1] >= min_coverage
        ),
        key=lambda r: (-r.query_share, -r.click_coverage, r.attribute),
    )
    chosen = fixed + rest[:top_n]
    return [replace(row, rank=rank) for rank, row in enumerate(chosen)]
