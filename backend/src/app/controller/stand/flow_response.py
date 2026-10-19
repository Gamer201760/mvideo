from app.controller.stand.schemas import (
    AttributeRiskSchema,
    CategorySchema,
    EvidenceRejectionSchema,
    ExtractedValueSchema,
    ExtractResponse,
)
from app.usecase.stand_attribute_flow import StandFlowResult


def flow_response(result: StandFlowResult) -> ExtractResponse:
    category = result.category
    risks = {risk.attribute: risk for risk in result.risks}
    values: list[ExtractedValueSchema] = []
    extras: list[ExtractedValueSchema] = []
    for answers, target in (
        (result.extraction.items, values),
        (result.extraction.extra_fields, extras),
    ):
        for answer in answers:
            if answer.status != "supported":
                continue
            value = answer.normalized_value or answer.value
            unit = answer.normalized_unit if answer.normalized_unit is not None else answer.unit
            risk = risks.get(answer.attribute)
            manual = answer.attribute in result.confirmed
            automatic = answer.attribute in result.automatic
            target.append(
                ExtractedValueSchema(
                    attribute=answer.attribute,
                    value=result.confirmed.get(answer.attribute, f"{value} {unit}".strip()),
                    confidence=risk.score if risk and not manual else None,
                    risk=AttributeRiskSchema(
                        level=risk.level,
                        score=risk.score,
                        reasons=list(risk.reasons),
                        method=risk.method,
                    )
                    if risk and not manual
                    else None,
                    source="review" if answer.attribute in result.confirmed else answer.source,
                    sources=[answer.source],
                    evidence=answer.quote,
                    start=answer.start,
                    end=answer.end,
                    status="accepted" if manual or automatic else "review",
                    review_id=result.review_ids.get(answer.attribute),
                    acceptance="manual" if manual else "automatic" if automatic else "review",
                )
            )
    filled = {v.attribute for v in (*values, *extras)}
    return ExtractResponse(
        text=result.text,
        threshold=result.threshold,
        auto_accept_enabled=result.auto_accept_enabled,
        values=values,
        extra_values=extras,
        missing=list(result.missing),
        rejections=[
            EvidenceRejectionSchema(attribute=r.attribute, reason=r.reason, evidence=r.quote)
            for r in result.extraction.rejections
            if r.attribute not in filled
        ],
        engine="hybrid",
        category=CategorySchema(
            category_id=category.category_id,
            name=category.path.split("/")[-1].strip(),
            path=category.path,
            attributes=[f.attribute for f in category.fields],
        )
        if category
        else None,
    )
