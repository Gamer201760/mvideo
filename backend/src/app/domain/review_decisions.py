from collections.abc import Iterable

from app.domain.review import ReviewItem, ReviewStatus


def latest_decisions(items: Iterable[ReviewItem]) -> dict[str, ReviewItem]:
    decisions: dict[str, ReviewItem] = {}
    for item in items:
        if item.resolved_at is None or item.status in {
            ReviewStatus.PENDING,
            ReviewStatus.AUTO_ACCEPTED,
        }:
            continue
        previous = decisions.get(item.attribute)
        if (
            previous is None
            or previous.resolved_at is None
            or previous.resolved_at < item.resolved_at
        ):
            decisions[item.attribute] = item
    return decisions
