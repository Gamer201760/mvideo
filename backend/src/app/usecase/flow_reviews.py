from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from app.domain.acceptance import AcceptancePolicy
from app.domain.attribute_flow import CatalogCandidate, Extraction, FieldAnswer
from app.domain.attribute_normalization import normalize_answer
from app.domain.evidence_risk import AttributeRisk
from app.domain.review import ReviewItem, ReviewStatus, evidence_form
from app.domain.review_decisions import latest_decisions
from app.usecase.extract_card import card_key
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.review_card import ReviewCard
from app.usecase.review_query import ReviewQuery
from app.usecase.stand_ports import CardInput


class FlowReviews:
    def __init__(self, store: UnitOfWorkFactory | None, policy: AcceptancePolicy) -> None:
        self._store, self._policy = store, policy

    async def confirmed(
        self, card: CardInput, result: Extraction, text: str, category: CatalogCandidate | None
    ) -> Extraction:
        if self._store is None:
            return result
        key = card_key(replace(card, category_id=result.category_id))
        async with self._store() as unit:
            page = await unit.reviews.page(ReviewQuery(card_key=key, limit=None))
        decisions = latest_decisions(page.items)
        rejected = {a for a, d in decisions.items() if d.status is ReviewStatus.REJECTED}
        items = {a.attribute: a for a in result.items if a.attribute not in rejected}
        extras = {a.attribute: a for a in result.extra_fields if a.attribute not in rejected}
        definitions = {f.attribute: f for f in category.fields} if category else {}
        for decision in decisions.values():
            start = text.find(decision.evidence) if decision.evidence else -1
            if start < 0 or decision.resolved_value is None:
                continue
            answer = FieldAnswer(
                decision.attribute,
                "supported",
                decision.resolved_value,
                "",
                decision.evidence,
                start,
                start + len(decision.evidence),
                decision.resolved_value,
                "",
                source="review",
            )
            target = items if decision.attribute in definitions else extras
            target[decision.attribute] = normalize_answer(
                answer, definitions.get(decision.attribute)
            )
        return replace(result, items=tuple(items.values()), extra_fields=tuple(extras.values()))

    async def record(
        self, card: CardInput, result: Extraction, risks: tuple[AttributeRisk, ...]
    ) -> tuple[dict[str, str], dict[str, str], frozenset[str], frozenset[str]]:
        assessments = {r.attribute: r for r in risks}
        automatic = {
            a.attribute
            for a in (*result.items, *result.extra_fields)
            if a.source != "review"
            and self._policy.accepts(assessments.get(a.attribute), result.category_id)
        }
        if self._store is None:
            return {}, {}, frozenset(automatic), frozenset()
        key = card_key(replace(card, category_id=result.category_id))
        ids, confirmed = {}, {}
        suppressed: set[str] = set()
        async with self._store() as unit:
            await unit.cards.save(
                key, ReviewCard(replace(card, category_id=result.category_id), "hybrid")
            )
            aliases = {
                (a.attribute, evidence_form(a.evidence)): a
                for a in await unit.aliases.all()
                if a.card_key == key and a.category_id == result.category_id
            }
            page = await unit.reviews.page(ReviewQuery(card_key=key, limit=None))
            decisions = latest_decisions(page.items)
            for answer in (*result.items, *result.extra_fields):
                if answer.status != "supported":
                    continue
                decision = decisions.get(answer.attribute)
                if decision is not None and decision.status is ReviewStatus.REJECTED:
                    suppressed.add(answer.attribute)
                    automatic.discard(answer.attribute)
                    continue
                value = (
                    f"{answer.normalized_value or answer.value} "
                    f"{answer.normalized_unit if answer.normalized_unit is not None else answer.unit}"
                ).strip()
                alias = aliases.get((answer.attribute, evidence_form(answer.quote)))
                if alias is not None:
                    confirmed[answer.attribute] = alias.value
                    automatic.discard(answer.attribute)
                    continue
                risk = assessments.get(answer.attribute)
                item = ReviewItem(
                    id=str(uuid4()),
                    card_key=key,
                    category_id=result.category_id,
                    title=card.title,
                    attribute=answer.attribute,
                    value=value,
                    confidence=risk.score if risk else 0,
                    source=answer.source,
                    evidence=answer.quote,
                    status=ReviewStatus.AUTO_ACCEPTED
                    if answer.attribute in automatic
                    else ReviewStatus.PENDING,
                    resolved_value=None,
                    created_at=datetime.now(UTC),
                    resolved_at=None,
                )
                saved = await unit.reviews.upsert_pending(item)
                if saved.resolved_value is not None:
                    confirmed[answer.attribute] = saved.resolved_value
                    automatic.discard(answer.attribute)
                else:
                    updated = replace(item, id=saved.id, created_at=saved.created_at)
                    if updated != saved:
                        await unit.reviews.save(updated)
                    ids[answer.attribute] = saved.id
            await unit.commit()
        return ids, confirmed, frozenset(automatic), frozenset(suppressed)
