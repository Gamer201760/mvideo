import math
import re
from dataclasses import dataclass

from app.domain.attribute_flow import CatalogField, FieldAnswer
from app.domain.card_text import match_form
from app.domain.evidence_counts import count_evidence
from app.domain.evidence_quantity_text import quantity_fragments
from app.domain.evidence_signals import field_forms
from app.domain.evidence_words import field_matches
from app.domain.values import NUMBER, Quantity, leading_quantity, quantity_in_unit

SIGNED = rf"[+−-]?\s*{NUMBER}"
NUMBERS = re.compile(rf"(?<![\w.,]){SIGNED}")
INTERVAL = re.compile(
    rf"^\s*(?:от\s*)?({SIGNED})\s*([^\d]*?)\s*(?:[-–—…]|до)\s*({SIGNED})\s*(.*?)\s*$"
)
LIMIT = re.compile(
    rf"^\s*(не более|не менее|до|от|более|менее|свыше|около)\s*({SIGNED})\s*(.*?)\s*$"
)
RANGE = re.compile(rf"\b(?:до|от|более|менее|свыше|около)\s*{SIGNED}|{SIGNED}\s*[-–—…]\s*{SIGNED}")
MODES = {"не более": "max", "до": "max", "не менее": "min", "от": "min", "свыше": "more"}


@dataclass(frozen=True, slots=True)
class QuantityRange:
    mode: str
    endpoints: tuple[Quantity, ...]


def scalar(value: str, unit: str = "") -> Quantity | None:
    value = match_form(value).strip()
    sign = -1 if value.startswith(("-", "−")) else 1
    unsigned = value[1:].lstrip() if value.startswith(("+", "-", "−")) else value
    quantity = leading_quantity(unsigned, unit)
    return Quantity(sign * quantity.number, quantity.unit) if quantity else None


def parse_range(value: str, unit: str = "") -> QuantityRange | None:
    value = match_form(value)
    interval = INTERVAL.fullmatch(value)
    if interval:
        first, first_unit, last, last_unit = interval.groups()
        left = scalar(first, first_unit.strip() or last_unit.strip() or unit)
        right = scalar(last, last_unit.strip() or first_unit.strip() or unit)
        if left and right:
            converted = quantity_in_unit(left, right.unit)
            if converted is None or converted.number > right.number:
                return None
            return QuantityRange("interval", (left, right))
        return None
    limit = LIMIT.fullmatch(value)
    if limit:
        mode, number, suffix = limit.groups()
        endpoint = scalar(number, suffix.strip() or unit)
        if endpoint:
            return QuantityRange(MODES.get(mode, mode), (endpoint,))
    return None


def same_quantity(left: Quantity, right: Quantity) -> bool:
    converted = quantity_in_unit(left, right.unit)
    return converted is not None and math.isclose(
        converted.number, right.number, rel_tol=1e-6, abs_tol=1e-8
    )


def unit_error(quantity: Quantity, answer: FieldAnswer, field: CatalogField | None) -> bool:
    targets = (answer.unit, field.unit if field else "")
    return any(target and quantity_in_unit(quantity, target) is None for target in targets)


def numeric_error(
    answer: FieldAnswer, field: CatalogField | None, evidence: str, quote: str | None = None
) -> str | None:
    separator = re.match(r"^([^\d:]+?)\s+[-–—]\s+(?=\d)", match_form(evidence))
    if separator and field_matches(separator[1], field_forms(answer, field)):
        evidence = match_form(evidence)[separator.end() :]
    unit = answer.unit or (field.unit if field else "")
    evidence = count_evidence(answer, evidence, unit) or evidence
    fragments = quantity_fragments(match_form(evidence), match_form(quote) if quote else None)
    unit = answer.unit or (field.unit if field else "")
    if len(fragments) > 1 and unit:
        fragments = tuple(
            fragment
            for fragment in fragments
            if (
                (quantity := scalar(fragment.removeprefix("до ").removeprefix("от ")))
                and quantity_in_unit(quantity, unit) is not None
            )
        )
    if len(fragments) > 1:
        return "number_unconfirmed"
    if fragments:
        evidence = fragments[0]
    expected_range = parse_range(answer.value, unit)
    actual_range = parse_range(evidence)
    if (
        RANGE.search(match_form(answer.value))
        or INTERVAL.fullmatch(match_form(answer.value))
        or expected_range
    ):
        if not expected_range or not actual_range:
            return "range_mismatch"
        if any(
            unit_error(q, answer, field)
            for q in (*expected_range.endpoints, *actual_range.endpoints)
        ):
            return "unit_mismatch"
        preserved = expected_range.mode == actual_range.mode and len(
            expected_range.endpoints
        ) == len(actual_range.endpoints)
        if preserved and all(
            same_quantity(a, b)
            for a, b in zip(expected_range.endpoints, actual_range.endpoints, strict=True)
        ):
            return None
        return "range_mismatch"
    if actual_range or RANGE.search(match_form(evidence)):
        return "range_lost"
    expected = scalar(answer.value, unit)
    if expected is None:
        literal = rf"(?<![\w.,+−-]){re.escape(match_form(answer.value))}\s*{re.escape(match_form(answer.unit))}(?!\w)"
        if answer.unit and not (field and field.unit) and re.search(literal, match_form(evidence)):
            return None
        return "number_unconfirmed"
    if unit_error(expected, answer, field):
        return "unit_mismatch"
    for match in NUMBERS.finditer(evidence):
        actual = scalar(evidence[match.start() :])
        if actual and same_quantity(actual, expected):
            return None
    return "number_unconfirmed"
