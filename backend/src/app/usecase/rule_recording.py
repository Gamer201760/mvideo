from collections.abc import Sequence
from dataclasses import replace

from app.domain.acceptance import AcceptancePolicy
from app.domain.review import Alias, ReviewItem, ReviewStatus, evidence_form
from app.domain.review_decisions import latest_decisions
from app.usecase.card_identity import card_key
from app.usecase.card_result import ExtractedValue
from app.usecase.extraction import CardExtraction
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.review_card import ReviewCard
from app.usecase.review_query import ReviewQuery
from app.usecase.rule_assessment import RuleAssessment
from app.usecase.rule_reviews import apply_decisions
from app.usecase.stand_ports import CardInput, Clock, IdGenerator, ReviewRepository


class RuleRecording:
    def __init__(
        self,
        reviews: ReviewRepository,
        clock: Clock,
        ids: IdGenerator,
        store: UnitOfWorkFactory | None,
        policy: AcceptancePolicy,
    ) -> None:
        self._reviews, self._clock, self._ids = reviews, clock, ids
        self._store, self._policy = store, policy

    async def record(
        self,
        card: CardInput,
        extraction: CardExtraction,
        assessment: RuleAssessment,
        aliases: Sequence[Alias],
    ) -> list[ExtractedValue]:
        if self._store is None:
            return await self._values(card, extraction, assessment, aliases, self._reviews)
        async with self._store() as unit:
            await unit.cards.save(card_key(card), ReviewCard(card, "rules"))
            values = await self._values(
                card, extraction, assessment, await unit.aliases.all(), unit.reviews
            )
            await unit.commit()
            return values

    async def _values(
        self,
        card: CardInput,
        extraction: CardExtraction,
        assessment: RuleAssessment,
        aliases: Sequence[Alias],
        reviews: ReviewRepository,
    ) -> list[ExtractedValue]:
        page = await reviews.page(ReviewQuery(card_key=card_key(card), limit=None))
        decisions = latest_decisions(page.items)
        confirmed = {
            (a.attribute, evidence_form(a.evidence)): a
            for a in aliases
            if a.card_key == card_key(card) and a.category_id == card.category_id
        }
        values = []
        for name in sorted(extraction.profiles):
            if name in decisions:
                continue
            manual = next(
                (
                    confirmed[(name, evidence_form(c.evidence))]
                    for c in extraction.candidates
                    if c.attribute == name and (name, evidence_form(c.evidence)) in confirmed
                ),
                None,
            )
            if manual is not None:
                values.append(_manual(name, manual, extraction.text.text))
                continue
            pick = assessment.picks.get(name)
            if pick is None:
                continue
            risk, c = assessment.risks[name], pick.candidate
            automatic = self._policy.accepts(risk, card.category_id)
            proposed = ReviewItem(
                id=self._ids.new(),
                card_key=card_key(card),
                category_id=card.category_id,
                title=card.title,
                attribute=name,
                value=c.value,
                confidence=risk.score,
                source=c.source,
                evidence=c.evidence,
                status=ReviewStatus.AUTO_ACCEPTED if automatic else ReviewStatus.PENDING,
                resolved_value=None,
                created_at=self._clock.now(),
                resolved_at=None,
            )
            saved = await reviews.upsert_pending(proposed)
            updated = replace(proposed, id=saved.id, created_at=saved.created_at)
            if saved.resolved_at is not None:
                decisions[name] = saved
                continue
            if updated != saved:
                await reviews.save(updated)
            values.append(
                ExtractedValue(
                    attribute=name,
                    value=c.value,
                    confidence=risk.score,
                    source=c.source,
                    sources=pick.sources,
                    evidence=c.evidence,
                    start=c.start,
                    end=c.end,
                    in_review=not automatic,
                    review_id=saved.id,
                    risk=risk,
                )
            )
        return apply_decisions(values, decisions, extraction.text.text)


def _manual(name: str, alias: Alias, text: str) -> ExtractedValue:
    start = text.find(alias.evidence)
    return ExtractedValue(
        attribute=name,
        value=alias.value,
        confidence=0,
        source="review",
        sources=("review",),
        evidence=alias.evidence,
        start=start,
        end=start + len(alias.evidence),
        in_review=False,
        review_id=None,
    )
