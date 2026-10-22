import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from app.domain.acceptance import AcceptancePolicy
from app.domain.attribute_flow import (
    CatalogCandidate,
    CatalogField,
    Extraction,
    FlowCard,
    FlowOutcome,
)
from app.domain.card_text import build_card_text
from app.domain.evidence_risk import AttributeRisk, EvidenceRiskModel, assess_extraction
from app.domain.evidence_validation import validate_extraction
from app.domain.regex_answers import regex_answers
from app.domain.review import UnknownCategory
from app.domain.seller_completion import complete_seller_fields
from app.usecase.attribute_flow import AttributeFlow
from app.usecase.catalog_schemas import CatalogSchemas
from app.usecase.flow_failures import flow_failure
from app.usecase.flow_reviews import FlowReviews
from app.usecase.persistence import UnitOfWorkFactory
from app.usecase.stand_ports import CardInput


class CategoryRetrieval(CatalogSchemas, Protocol):
    def retrieve(self, text: str, k: int = 3) -> tuple[CatalogCandidate, ...]: ...

    def remember(self, category: CatalogCandidate, title: str) -> None: ...

    def add_category(
        self, path: str, fields: tuple[CatalogField, ...], title: str
    ) -> CatalogCandidate: ...


@dataclass(frozen=True, slots=True)
class StandFlowResult:
    text: str
    extraction: Extraction
    category: CatalogCandidate | None
    missing: tuple[str, ...]
    risks: tuple[AttributeRisk, ...] = ()
    review_ids: Mapping[str, str] = field(default_factory=dict)
    confirmed: Mapping[str, str] = field(default_factory=dict)
    threshold: float = 0.95
    automatic: tuple[str, ...] = ()
    auto_accept_enabled: bool = True


class StandAttributeFlow:
    def __init__(
        self,
        flow: AttributeFlow,
        retrieval: CategoryRetrieval,
        risk_model: EvidenceRiskModel | None = None,
        store: UnitOfWorkFactory | None = None,
        acceptance: AcceptancePolicy | None = None,
        read_store: UnitOfWorkFactory | None = None,
    ) -> None:
        self._store = store
        self._flow = flow
        self._retrieval = retrieval
        self._risk_model = risk_model
        self._acceptance = acceptance or AcceptancePolicy()
        self._reviews = FlowReviews(store, self._acceptance, read_store)

    async def prepare(self, card: CardInput, *, limit: int = 3) -> FlowCard:
        return await asyncio.to_thread(self._prepare, card, limit)

    def _prepare(self, card: CardInput, limit: int) -> FlowCard:
        text = build_card_text(card.title, card.description, card.seller_params).text
        candidates = self._retrieval.retrieve(text, k=limit)
        if card.category_id is not None:
            category = next(
                (c for c in self._retrieval.snapshot() if c.category_id == card.category_id),
                None,
            )
            if category is None:
                raise UnknownCategory()
            example = next((c for c in candidates if c.category_id == card.category_id), category)
            example = replace(
                category,
                score=example.score,
                example_text=example.example_text,
                example_values=example.example_values,
            )
            candidates = (example,)
        hints = regex_answers(text, candidates[0]) if candidates else ()
        return FlowCard(0, text, candidates, hints)

    async def execute(self, card: CardInput) -> StandFlowResult:
        prepared = await self.prepare(card)
        outcomes = await self.infer((prepared,))
        if not outcomes or not outcomes[0].final:
            raise flow_failure(outcomes[0].calls if outcomes else ())
        return await self.finalize(card, prepared, outcomes[0].final[0])

    async def infer(self, cards: Sequence[FlowCard]) -> list[FlowOutcome]:
        return await self._flow.run(cards)

    async def finalize(
        self, card: CardInput, prepared: FlowCard, result: Extraction
    ) -> StandFlowResult:
        text, candidates = prepared.text, prepared.candidates
        if candidates and result.category_id == candidates[0].category_id:
            hints = {(a.attribute, a.value, a.quote): a.source for a in prepared.rules}
            result = replace(
                result,
                items=tuple(
                    replace(a, source=hints.get((a.attribute, a.value, a.quote), a.source))
                    for a in result.items
                ),
            )
        category = next((c for c in candidates if c.category_id == result.category_id), None)
        if result.proposed_category and (result.extra_fields or result.rejections):
            result, added_category = await self._add_category(result, card.title)
            category = added_category
            prepared = replace(prepared, candidates=(*candidates, added_category))
        if category is not None and category.category_id >= 0:
            result = await asyncio.to_thread(
                complete_seller_fields, result, category, text, card.seller_params
            )
        result = await asyncio.to_thread(
            validate_extraction, result, category.fields if category else (), text, category
        )
        result = await self._reviews.confirmed(card, result, text, category)
        risk_model = self._risk_model if category and category.category_id >= 0 else None
        risks = await asyncio.to_thread(assess_extraction, prepared, result, risk_model)
        review_ids, confirmed, automatic, suppressed = await self._reviews.record(
            card, result, risks
        )
        result = replace(
            result,
            items=tuple(a for a in result.items if a.attribute not in suppressed),
            extra_fields=tuple(a for a in result.extra_fields if a.attribute not in suppressed),
        )
        found = {a.attribute for a in result.items if a.status == "supported"}
        missing = (
            tuple(f.attribute for f in category.fields if f.attribute not in found)
            if category
            else ()
        )
        return StandFlowResult(
            text,
            result,
            category,
            missing,
            risks,
            review_ids,
            confirmed,
            self._acceptance.threshold,
            tuple(sorted(automatic)),
            self._acceptance.enabled,
        )

    async def _add_category(
        self, result: Extraction, title: str
    ) -> tuple[Extraction, CatalogCandidate]:
        fields = tuple(CatalogField(a.attribute, "free", a.unit) for a in result.extra_fields)
        known_fields = {f.attribute for f in fields}
        fields += tuple(
            CatalogField(name, "free", "")
            for name in dict.fromkeys(r.attribute for r in result.rejections)
            if name not in known_fields
        )
        if self._store is not None:
            async with self._store() as unit:
                category = await unit.catalog.register(result.proposed_category or "", fields)
                await unit.commit()
            await asyncio.to_thread(self._retrieval.remember, category, title)
        else:
            category = await asyncio.to_thread(
                self._retrieval.add_category, result.proposed_category or "", fields, title
            )
        known = {f.attribute for f in category.fields}
        result = replace(
            result,
            category_id=category.category_id,
            items=(*result.items, *(a for a in result.extra_fields if a.attribute in known)),
            extra_fields=tuple(a for a in result.extra_fields if a.attribute not in known),
        )
        return result, category
