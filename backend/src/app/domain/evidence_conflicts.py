import re

from app.domain.attribute_flow import CatalogField, FieldAnswer
from app.domain.card_text import match_form
from app.domain.evidence_signals import field_forms, named_values, value_key

STATEMENTS = re.compile(r"[;\n]|(?<!\d)[.!?](?!\d)")
NEGATED = re.compile(r"^(?:не|нет|not|no)\b")


def conflicting_declarations(answer: FieldAnswer, field: CatalogField | None, text: str) -> bool:
    forms = field_forms(answer, field)
    values = list(named_values(text, forms))
    aliases = "|".join(re.escape(match_form(form).strip()) for form in forms)
    label = re.compile(rf"^(?:{aliases})\s+(?:[-–—]\s+)?(.+)$")
    for statement in STATEMENTS.split(text):
        if ":" in statement:
            continue
        match = label.match(match_form(statement).strip())
        if match is None:
            continue
        value = match[1].strip()
        if not (field and field.kind == "boolean") and NEGATED.search(value):
            continue
        values.append(value)
    return len({value_key(value, field) for value in values}) > 1
