from dataclasses import dataclass

from app.domain.review import ReviewItem, ReviewStatus


@dataclass(frozen=True, slots=True)
class ReviewQuery:
    status: ReviewStatus | None = None
    card_key: str | None = None
    exclude_card_key: str | None = None
    offset: int = 0
    limit: int | None = 50


@dataclass(frozen=True, slots=True)
class ReviewPage:
    items: list[ReviewItem]
    total: int


@dataclass(frozen=True, slots=True)
class CardReviewState:
    card_key: str
    items: list[ReviewItem]
