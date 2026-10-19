from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.card_text import match_form
from app.domain.errors import DomainError
from app.domain.lexicon import LexiconEntry, value_tokens
from app.domain.values import canonical_key

REVIEW_CONFIDENCE = 0.97
REVIEW_SOURCE = "review"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    AUTO_ACCEPTED = "auto_accepted"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ReviewAction(StrEnum):
    ACCEPT = "accept"
    CORRECT = "correct"
    REJECT = "reject"


class ReviewItemNotFound(DomainError):
    code = "review_item_not_found"
    message = "Review item not found"


class ReviewAlreadyResolved(DomainError):
    code = "review_already_resolved"
    message = "Review item is already resolved"


class InvalidCorrection(DomainError):
    code = "invalid_correction"
    message = "A correction needs a non-empty value"


class InvalidReviewEvidence(DomainError):
    code = "invalid_review_evidence"
    message = "A manual addition needs an exact non-empty quote from the card"


class InvalidReviewAttribute(DomainError):
    code = "invalid_review_attribute"
    message = "A manual addition needs a field from the selected category"


class StandUnavailable(DomainError):
    code = "stand_unavailable"
    message = "Stand data is not built; run stand-pack"


class UnknownCategory(DomainError):
    code = "unknown_category"
    message = "Category is not part of the stand data"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewItem:
    id: str
    card_key: str
    category_id: int | None
    title: str
    attribute: str
    value: str
    confidence: float
    source: str
    evidence: str
    status: ReviewStatus
    resolved_value: str | None
    created_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Alias:
    attribute: str
    evidence: str
    value: str
    created_at: datetime
    category_id: int | None = None
    card_key: str = ""


def evidence_form(text: str) -> str:
    return " ".join(match_form(text).split())


def alias_entry(alias: Alias, numeric: bool, unit: str | None = None) -> LexiconEntry:
    return LexiconEntry(
        attribute=alias.attribute,
        tokens=value_tokens(alias.evidence),
        key=canonical_key(alias.value, None, numeric, target_unit=unit),
        display=alias.value,
    )


def resolve(
    item: ReviewItem,
    action: ReviewAction,
    value: str | None,
    now: datetime,
    *,
    override: bool = False,
    expected_value: str | None = None,
) -> tuple[ReviewItem, Alias | None]:
    if item.status not in {ReviewStatus.PENDING, ReviewStatus.AUTO_ACCEPTED} and not (
        action in {ReviewAction.CORRECT, ReviewAction.REJECT}
        and override
        and expected_value == item.resolved_value
    ):
        raise ReviewAlreadyResolved()
    if action is ReviewAction.CORRECT:
        final = (value or "").strip()
        if not final:
            raise InvalidCorrection()
        status = ReviewStatus.CORRECTED
    elif action is ReviewAction.ACCEPT:
        final = item.value
        status = ReviewStatus.ACCEPTED
    else:
        final = None
        status = ReviewStatus.REJECTED
    resolved = ReviewItem(
        id=item.id,
        card_key=item.card_key,
        category_id=item.category_id,
        title=item.title,
        attribute=item.attribute,
        value=(item.resolved_value or item.value) if action is ReviewAction.REJECT else item.value,
        confidence=item.confidence,
        source=item.source,
        evidence=item.evidence,
        status=status,
        resolved_value=final,
        created_at=item.created_at,
        resolved_at=now,
    )
    alias = (
        Alias(
            attribute=item.attribute,
            evidence=item.evidence,
            value=final,
            created_at=now,
            category_id=item.category_id,
            card_key=item.card_key,
        )
        if final is not None
        else None
    )
    return resolved, alias
