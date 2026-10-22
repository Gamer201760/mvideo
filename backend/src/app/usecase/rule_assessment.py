from collections.abc import Mapping
from dataclasses import dataclass, replace

from app.domain.attribute_flow import (
    CatalogCandidate,
    CatalogField,
    EvidenceRejection,
    Extraction,
    FieldAnswer,
    FlowCard,
)
from app.domain.attribute_normalization import normalize_answer
from app.domain.evidence_risk import AttributeRisk, assess_extraction
from app.domain.evidence_validation import validate_extraction
from app.domain.scoring import Pick
from app.usecase.catalog_schemas import CatalogSchemas
from app.usecase.extraction import CardExtraction
from app.usecase.stand_ports import CardInput


@dataclass(frozen=True, slots=True)
class RuleAssessment:
    picks: Mapping[str, Pick]
    risks: Mapping[str, AttributeRisk]
    rejections: tuple[EvidenceRejection, ...]


def assess_rules(
    card: CardInput, extraction: CardExtraction, schemas: CatalogSchemas | None
) -> RuleAssessment:
    category = (
        next((c for c in schemas.snapshot() if c.category_id == card.category_id), None)
        if schemas
        else None
    )
    if category is None:
        category = CatalogCandidate(
            card.category_id if card.category_id is not None else -1,
            "",
            1,
            tuple(CatalogField(n, p.kind.value, p.unit) for n, p in extraction.profiles.items()),
        )
    category = replace(category, score=1)
    definitions = {f.attribute: f for f in category.fields}
    picks = {**extraction.review, **extraction.picks}
    answers = []
    for name, pick in picks.items():
        c = pick.candidate
        answers.append(
            normalize_answer(
                FieldAnswer(
                    name, "supported", c.value, "", c.evidence, c.start, c.end, source=c.source
                ),
                definitions.get(name),
            )
        )
    result = validate_extraction(
        Extraction(0, category.category_id, tuple(answers), (), False),
        category.fields,
        extraction.text.text,
        category,
    )
    risks = {
        r.attribute: r
        for r in assess_extraction(FlowCard(0, extraction.text.text, (category,)), result)
    }
    supported = {}
    for answer in result.items:
        pick = picks[answer.attribute]
        value = answer.normalized_value if answer.normalized_value is not None else answer.value
        unit = answer.normalized_unit if answer.normalized_unit is not None else answer.unit
        supported[answer.attribute] = replace(
            pick,
            candidate=replace(pick.candidate, value=f"{value} {unit}".strip()),
            confidence=risks[answer.attribute].score,
        )
    return RuleAssessment(supported, risks, result.rejections)
