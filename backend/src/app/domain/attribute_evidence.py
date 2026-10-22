from collections.abc import Mapping
from dataclasses import replace

from app.domain.attribute_flow import Extraction, FieldAnswer, FlowCard, identifiers
from app.domain.attribute_normalization import normalize_answer
from app.domain.category_path import category_path
from app.domain.evidence_validation import evidence_error, validate_extraction


def parse_answer(raw: object, attribute: str, text: str) -> FieldAnswer:
    if not isinstance(raw, dict):
        raise TypeError("answer is not an object")
    fields = [raw.get(k) for k in ("v", "u", "q")]
    if not all(isinstance(value, str) for value in fields):
        raise ValueError("answer fields must be strings")
    risks = raw.get("r", 0)
    if type(risks) is not int or not 0 <= risks <= 7:
        raise ValueError("invalid risk flags")
    value, unit, quote = (str(value) for value in fields)
    start = text.find(quote) if quote else -1
    if not value.strip() or start < 0:
        raise ValueError(f"invalid evidence for {attribute}")
    return FieldAnswer(
        attribute,
        "supported",
        value.strip(),
        unit.strip(),
        quote,
        start,
        start + len(quote),
        risks=risks,
    )


def parse_extraction(
    raw: Mapping[str, object],
    card: FlowCard,
    fields: list[str],
    categories: list[int],
) -> Extraction:
    category_index = raw.get("k")
    proposed = category_path(category_index) if isinstance(category_index, str) else None
    if (
        proposed is None
        and category_index is not None
        and (type(category_index) is not int or not 0 <= category_index < len(categories))
    ):
        raise ValueError("invalid category index")
    category = categories[int(category_index)] if type(category_index) is int else None
    schema = next((c for c in card.candidates if c.category_id == category), None)
    if category is not None and schema is None:
        raise ValueError("category is outside retrieved candidates")
    allowed = {field.attribute for field in schema.fields} if schema else set()
    errors: list[str] = []
    answers: dict[str, FieldAnswer] = {}
    extras: dict[str, FieldAnswer] = {}
    duplicates: set[str] = set()
    values, ambiguous = raw.get("a"), raw.get("r")
    if not isinstance(values, list) or not isinstance(ambiguous, list):
        raise TypeError("a/r must be arrays")
    if category is None and ambiguous:
        raise ValueError("unknown category cannot reference ambiguous catalog fields")
    for value in values:
        try:
            if not isinstance(value, dict):
                raise TypeError("invalid answer object")
            field = value.get("f")
            if type(field) is int and 0 <= field < len(fields):
                attribute = fields[field]
                if attribute not in allowed:
                    raise ValueError("field is outside selected category")
                target = answers
            elif isinstance(field, str) and field.strip():
                attribute = field.strip()
                target = answers if attribute in allowed else extras
            else:
                raise ValueError("invalid field index or extra field name")
            if attribute in answers or attribute in extras or attribute in duplicates:
                answers.pop(attribute, None)
                extras.pop(attribute, None)
                duplicates.add(attribute)
                raise ValueError(f"duplicate attribute {attribute}")
            answer = parse_answer(value, attribute, card.text)
            definition = (
                next((f for f in schema.fields if f.attribute == attribute), None)
                if schema
                else None
            )
            position = card.text.find(answer.quote, answer.start + 1)
            while position >= 0 and evidence_error(answer, definition, card.text, schema):
                answer = replace(answer, start=position, end=position + len(answer.quote))
                position = card.text.find(answer.quote, position + 1)
            target[attribute] = normalize_answer(answer, definition)
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
    seen: set[int] = set()
    for field in ambiguous:
        if type(field) is not int or not 0 <= field < len(fields) or fields[field] not in allowed:
            errors.append("invalid ambiguous field index")
            continue
        attribute = fields[field]
        if field in seen or attribute in answers:
            errors.append(f"conflicting ambiguous attribute {attribute}")
        seen.add(field)
        answers[attribute] = FieldAnswer(attribute, "ambiguous", "", "", "")
    extraction = Extraction(
        card.sku_id,
        category,
        tuple(answers.values()),
        tuple(extras.values()),
        bool(ambiguous or errors),
        tuple(errors),
        proposed,
    )
    return validate_extraction(extraction, schema.fields if schema else (), card.text, schema)


def parse_batch(
    output: Mapping[str, object], cards: tuple[FlowCard, ...]
) -> tuple[Extraction, ...]:
    rows = output.get("c")
    if not isinstance(rows, list):
        raise TypeError("response c must be an array")
    by_id: dict[int, Mapping[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("i")) is not int:
            raise ValueError("invalid card index")
        index = row["i"]
        if index in by_id:
            raise ValueError("duplicate card index")
        by_id[index] = row
    if set(by_id) != set(range(len(cards))):
        raise ValueError("response card indices differ from request")
    fields, categories = identifiers(cards)
    return tuple(
        parse_extraction(by_id[i], card, fields, categories) for i, card in enumerate(cards)
    )
