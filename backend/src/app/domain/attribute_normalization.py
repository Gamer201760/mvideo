from dataclasses import replace

from app.domain.attribute_flow import CatalogField, FieldAnswer
from app.domain.card_text import match_form
from app.domain.values import (
    canonical_text,
    canonical_unit,
    format_number,
    leading_quantity,
    quantity_in_unit,
)


def normalize_answer(answer: FieldAnswer, field: CatalogField | None) -> FieldAnswer:
    if answer.status != "supported":
        return answer
    value, unit = answer.value, answer.unit
    if field is not None and field.kind == "numeric" and field.unit:
        quantity = leading_quantity(value, unit)
        converted = quantity_in_unit(quantity, field.unit) if quantity is not None else None
        if converted is not None:
            value, unit = format_number(converted.number), field.unit
    elif field is not None:
        equivalent = canonical_text if "цвет" in field.attribute.casefold() else match_form
        value = next((v for v in field.values if equivalent(v) == equivalent(value)), value)
    return replace(answer, normalized_value=value, normalized_unit=canonical_unit(unit) or unit)
