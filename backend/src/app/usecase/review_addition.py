from datetime import datetime
from uuid import uuid4

from app.domain.card_text import build_card_text
from app.domain.review import (
    InvalidCorrection,
    InvalidReviewAttribute,
    InvalidReviewEvidence,
    ReviewAction,
    ReviewAlreadyResolved,
    ReviewItem,
    ReviewItemNotFound,
    ReviewStatus,
    resolve,
)
from app.domain.review_decisions import latest_decisions
from app.usecase.extract_card import card_key
from app.usecase.persistence import UnitOfWork
from app.usecase.review_query import ReviewQuery
from app.usecase.stand_ports import CardInput


async def add_review(
    unit: UnitOfWork, card: CardInput, attribute: str, value: str, evidence: str, now: datetime
) -> ReviewItem:
    key = card_key(card)
    saved = await unit.cards.get(key)
    if saved is None:
        raise ReviewItemNotFound()
    attribute, value = attribute.strip(), value.strip()
    category = next(
        (c for c in await unit.catalog.all() if c.category_id == card.category_id), None
    )
    text = build_card_text(card.title, card.description, card.seller_params).text
    if not value or len(value) > 500:
        raise InvalidCorrection()
    if not evidence.strip() or len(evidence) > 24000 or evidence not in text:
        raise InvalidReviewEvidence()
    if (
        not attribute
        or len(attribute) > 200
        or attribute.casefold().endswith("_search")
        or category is None
        or attribute not in {f.attribute for f in category.fields}
    ):
        raise InvalidReviewAttribute()
    page = await unit.reviews.page(ReviewQuery(card_key=key, limit=None))
    decision = latest_decisions(page.items).get(attribute)
    if decision is not None and decision.status is not ReviewStatus.REJECTED:
        if decision.resolved_value == value and decision.evidence == evidence:
            return decision
        raise ReviewAlreadyResolved()
    existing = [i for i in page.items if i.attribute == attribute]
    if decision is None and existing:
        raise ReviewAlreadyResolved()
    pending = ReviewItem(
        id=str(uuid4()),
        card_key=key,
        category_id=card.category_id,
        title=card.title,
        attribute=attribute,
        value=value,
        confidence=0,
        source="review",
        evidence=evidence,
        status=ReviewStatus.PENDING,
        resolved_value=None,
        created_at=now,
        resolved_at=None,
    )
    item = await unit.reviews.upsert_pending(pending)
    resolved, alias = resolve(
        item,
        ReviewAction.CORRECT,
        value,
        now,
        override=item.status not in {ReviewStatus.PENDING, ReviewStatus.AUTO_ACCEPTED},
        expected_value=item.resolved_value,
    )
    assert alias is not None
    await unit.reviews.save(resolved)
    await unit.aliases.add(alias)
    return resolved
