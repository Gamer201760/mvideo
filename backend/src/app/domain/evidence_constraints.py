import re

from app.domain.attribute_flow import CatalogField, FieldAnswer
from app.domain.card_text import match_form
from app.domain.evidence_context import NEGATIVE, POSITIVE, EvidenceContext
from app.domain.evidence_counts import COUNTER
from app.domain.evidence_relations import compatibility_field

IDENTITY = re.compile(
    r"^(?:модель|model|артикул|sku|серия|series|бренд|brand|марка|производитель)\b"
)
BRAND = re.compile(r"^(?:бренд|brand|марка|производитель)\b")
CONDITION = re.compile(
    r"\b(?:только\s+(?:с|при|для)|при\s+(?:наличии|покупке|подключении|использовании)"
    r"|если|опциональ\w*|дополнительн\w*\s+модул\w*)\b"
)


def constraint_error(
    answer: FieldAnswer,
    field: CatalogField | None,
    context: EvidenceContext,
) -> str | None:
    value = match_form(answer.value).strip()
    boolean = value in POSITIVE | NEGATIVE
    counted = bool(COUNTER.match(match_form(answer.attribute)))
    if counted and re.search(
        r"\b(?:не|нет|без|примерно|приблизительно|около|порядка|почти|минимум|максимум|свыше|больше|меньше)\b",
        match_form(context.text),
    ):
        return "number_unconfirmed"
    if (
        COUNTER.match(match_form(answer.attribute))
        and re.search(r"\b(?:внешн\w*|подключ\w*)\b", match_form(context.text))
        and not re.search(r"\b(?:внешн\w*|подключ\w*)\b", match_form(answer.attribute))
    ):
        return "object_context"
    if boolean and field and field.kind not in {"boolean", "free"}:
        return "field_type_mismatch"
    if (boolean or counted or compatibility_field(answer.attribute)) and CONDITION.search(
        match_form(context.text)
    ):
        return "conditional_support"
    if IDENTITY.search(match_form(answer.attribute)):
        if answer.unit:
            return "unit_mismatch"
        if re.search(r"\b(?:не|not)\s+", value) or value in NEGATIVE:
            return "negation"
        if (
            not BRAND.search(match_form(answer.attribute))
            and context.field_named
            and value != match_form(context.value).strip()
        ):
            return "value_unconfirmed"
        pattern = rf"(?<![\w-]){re.escape(value)}(?![\w-])"
        if not re.search(pattern, match_form(context.value)):
            return "value_unconfirmed"
    return None


def identity_field(attribute: str) -> bool:
    return bool(IDENTITY.search(match_form(attribute)))
