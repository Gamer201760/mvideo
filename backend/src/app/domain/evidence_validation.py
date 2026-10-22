from dataclasses import replace

from app.domain.attribute_flow import (
    CatalogCandidate,
    CatalogField,
    EvidenceRejection,
    Extraction,
    FieldAnswer,
)
from app.domain.card_text import match_form
from app.domain.evidence_composites import flag_evidence
from app.domain.evidence_conflicts import conflicting_declarations
from app.domain.evidence_constraints import constraint_error, identity_field
from app.domain.evidence_context import (
    NEGATIVE,
    POSITIVE,
    negation_error,
    resolve_context,
)
from app.domain.evidence_lists import list_evidence
from app.domain.evidence_quantities import RANGE, numeric_error, scalar
from app.domain.evidence_signals import field_forms
from app.domain.evidence_uncertainty import uncertainty_error
from app.domain.evidence_words import contains_value


def evidence_error(
    answer: FieldAnswer,
    field: CatalogField | None,
    text: str,
    category: CatalogCandidate | None = None,
) -> str | None:
    if answer.status != "supported" or answer.source == "review":
        return None
    if not answer.quote or answer.start < 0 or text[answer.start : answer.end] != answer.quote:
        return "invalid_evidence"
    forms = field_forms(answer, field)
    if conflicting_declarations(answer, field, text):
        return "conflicting_values"
    if answer.risks & 3:
        return "model_conflict" if answer.risks & 2 else "object_context"
    flags = flag_evidence(answer, field)
    if flags and all(evidence_error(a, f, text, category) is None for a, f in flags):
        return None
    parts = (
        list_evidence(answer)
        if not identity_field(answer.attribute)
        and (not field or field.kind in {"free", "categorical"})
        else ()
    )
    if parts and all(evidence_error(part, field, text, category) is None for part in parts):
        return None
    numeric = not identity_field(answer.attribute) and bool(
        field
        and field.kind == "numeric"
        or scalar(answer.value, answer.unit)
        or RANGE.search(match_form(answer.value))
    )
    context = resolve_context(
        answer, field, text, numeric=numeric, fields=category.fields if category else ()
    )
    if context.error:
        return context.error
    error = uncertainty_error(context.text, numeric=numeric)
    if error:
        return error
    if not numeric or not RANGE.search(match_form(answer.value)):
        error = negation_error(answer, context, forms)
        if error:
            return error
    error = constraint_error(answer, field, context)
    if error:
        return error
    if identity_field(answer.attribute):
        return None
    if numeric:
        evidence = context.text
        error = numeric_error(answer, field, evidence, answer.quote)
        if error:
            return error
        return numeric_error(answer, field, answer.quote.split(":", 1)[-1].strip())
    if match_form(answer.value) in POSITIVE | NEGATIVE:
        return None
    if field and field.kind == "boolean":
        return "value_unconfirmed"
    if not contains_value(answer.value, context.value):
        return "value_unconfirmed"
    return None


def validate_extraction(
    extraction: Extraction,
    fields: tuple[CatalogField, ...],
    text: str,
    category: CatalogCandidate | None = None,
) -> Extraction:
    definitions = {f.attribute: f for f in fields}
    errors = list(extraction.validation_errors)
    rejections = list(extraction.rejections)

    def validated(answers: tuple[FieldAnswer, ...]) -> tuple[FieldAnswer, ...]:
        result = []
        for answer in answers:
            reason = evidence_error(answer, definitions.get(answer.attribute), text, category)
            if reason:
                errors.append(f"{reason}: {answer.attribute}")
                rejection = EvidenceRejection(answer.attribute, reason, answer.quote)
                if rejection not in rejections:
                    rejections.append(rejection)
            else:
                result.append(answer)
        return tuple(result)

    items = validated(extraction.items)
    extras = validated(extraction.extra_fields)
    return replace(
        extraction,
        items=items,
        extra_fields=extras,
        review=extraction.review or bool(errors),
        validation_errors=tuple(errors),
        rejections=tuple(rejections),
    )
