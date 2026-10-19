from collections.abc import Mapping, Sequence

from app.domain.review import REVIEW_SOURCE, ReviewItem
from app.usecase.card_result import ExtractedValue


def apply_decisions(
    values: Sequence[ExtractedValue], decisions: Mapping[str, ReviewItem], text: str
) -> list[ExtractedValue]:
    result = {v.attribute: v for v in values}
    for item in decisions.values():
        if item.resolved_value is None:
            result.pop(item.attribute, None)
            continue
        start = text.find(item.evidence) if item.evidence else -1
        if start < 0:
            continue
        previous = result.get(item.attribute)
        result[item.attribute] = ExtractedValue(
            attribute=item.attribute,
            value=item.resolved_value,
            confidence=0,
            source=REVIEW_SOURCE,
            sources=(REVIEW_SOURCE,),
            evidence=item.evidence,
            start=start,
            end=start + len(item.evidence),
            in_review=False,
            review_id=item.id if previous is None else previous.review_id or item.id,
        )
    return list(result.values())
