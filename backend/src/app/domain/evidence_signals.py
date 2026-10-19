import math
import re
from collections.abc import Mapping
from difflib import SequenceMatcher

from app.domain.attribute_flow import CatalogCandidate, CatalogField, FieldAnswer, FlowCard
from app.domain.card_text import match_form
from app.domain.values import (
    NUMBER,
    UNIT_SCALES,
    canonical_text,
    leading_quantity,
    quantity_in_unit,
)

VERSION = "evidence-signals-v3"
WORDS = re.compile(r"[a-zа-я0-9]+")
NUMBERS = re.compile(NUMBER)
RANGE = re.compile(r"(?:\b(?:до|от|более|менее)\s*\d|\d\s*[-–—]\s*\d)")
NEGATION = re.compile(r"\b(?:не|нет|без|отсутствует|отсутствуют)\b")
OTHER_OBJECT = re.compile(r"\b(?:упаков\w*|совместим\w*|аксессуар\w*|чехол\w*)\b")
BOUNDARY = re.compile(r"[.;!?](?!\d)|(?<!\d),(?!\d)|\n")
NEGATIVE_VALUE = frozenset({"нет", "no", "false", "отсутствует", "не поддерживается"})
NEGATIVE_STATEMENT = re.compile(
    r"\b(?:отсутств\w*|без)\b|\bне\s+поддерж\w*|\bнет\b(?!\s+(?:данных|информации))"
)
NAMES = (
    "value_overlap",
    "value_similarity",
    "number_supported",
    "number_unconfirmed",
    "field_overlap",
    "named_value",
    "category_score",
    "category_margin",
    "category_rank",
    "seller_source",
    "title_source",
    "known_field",
    "vocabulary_match",
    "context_negation",
    "other_object",
    "range_lost",
    "conflicting_values",
    "model_scope",
    "model_conflict",
    "model_inference",
)


def words(value: str) -> set[str]:
    return set(WORDS.findall(canonical_text(value)))


def overlap(value: str, text: str) -> float:
    tokens = words(value)
    return len(tokens & words(text)) / len(tokens) if tokens else 0.0


def number_support(answer: FieldAnswer) -> tuple[float, float]:
    if RANGE.search(match_form(answer.value)):
        return 0.0, 0.0
    quantity = leading_quantity(answer.value, answer.unit)
    if quantity is None:
        return 0.0, 0.0
    for match in NUMBERS.finditer(answer.quote):
        candidate = leading_quantity(answer.quote[match.start() :])
        if candidate is None:
            continue
        converted = quantity_in_unit(candidate, quantity.unit)
        if converted and math.isclose(
            converted.number, quantity.number, rel_tol=1e-6, abs_tol=1e-8
        ):
            return 1.0, 0.0
    return 0.0, 1.0


def field_forms(answer: FieldAnswer, definition: CatalogField | None) -> tuple[str, ...]:
    aliases = definition.aliases if definition else ()
    brands = ("бренд", "brand", "марка", "торговая марка")
    if match_form(answer.attribute).strip() in brands:
        aliases = (*aliases, *brands)
    return (answer.attribute, *aliases)


def named_values(text: str, forms: tuple[str, ...]) -> tuple[str, ...]:
    aliases = {match_form(f).strip() for f in forms}
    return tuple(
        value.strip()
        for line in text.splitlines()
        for key, separator, value in (line.partition(":"),)
        if separator and match_form(key).strip() in aliases and value.strip()
    )


def value_key(value: str, definition: CatalogField | None) -> str:
    quantity = leading_quantity(value, definition.unit if definition else "")
    if quantity is not None:
        target = (
            definition.unit
            if definition and definition.unit
            else UNIT_SCALES.get(quantity.unit, (quantity.unit, 1.0))[0]
        )
        converted = quantity_in_unit(quantity, target)
        if converted:
            return f"{converted.number:.8g} {converted.unit}"
    return canonical_text(value)


def evidence_signals(
    card: FlowCard,
    category: CatalogCandidate,
    answer: FieldAnswer,
) -> Mapping[str, float]:
    definition = next((f for f in category.fields if f.attribute == answer.attribute), None)
    forms = field_forms(answer, definition)
    start = max(0, answer.start)
    left = list(BOUNDARY.finditer(card.text, max(0, start - 120), start))
    right_start = max(start, answer.end - len(answer.quote) + len(answer.quote.rstrip()) - 1)
    right = BOUNDARY.search(card.text, right_start, min(len(card.text), answer.end + 120))
    context = card.text[
        left[-1].end() if left else max(0, start - 120) : right.start()
        if right
        else min(len(card.text), answer.end + 120)
    ]
    named = named_values(card.text, forms)
    quote_named = named_values(answer.quote, forms)
    number, unconfirmed = number_support(answer)
    rank = next(
        (i for i, c in enumerate(card.candidates) if c.category_id == category.category_id),
        len(card.candidates),
    )
    alternative = max(
        (c.score for c in card.candidates if c.category_id != category.category_id), default=0.0
    )
    normalized_value = canonical_text(answer.value)
    boolean_supported = normalized_value in NEGATIVE_VALUE and bool(
        NEGATIVE_STATEMENT.search(match_form(answer.quote))
    )
    negative_preserved = boolean_supported or bool(NEGATION.search(normalized_value))
    quote_words = WORDS.findall(canonical_text(answer.quote))
    size = max(1, len(WORDS.findall(normalized_value)))
    similarity = max(
        (
            SequenceMatcher(None, normalized_value, " ".join(quote_words[i : i + size])).ratio()
            for i in range(len(quote_words))
        ),
        default=0.0,
    )
    return dict(
        zip(
            NAMES,
            (
                max(overlap(answer.value, answer.quote), float(boolean_supported)),
                similarity,
                number,
                unconfirmed,
                max(overlap(f, context) for f in forms),
                float(bool(quote_named)),
                category.score,
                category.score - alternative,
                float(rank),
                float(answer.source == "seller"),
                float(start < card.text.find("\n") if "\n" in card.text else True),
                float(definition is not None),
                float(
                    bool(
                        definition
                        and any(canonical_text(v) == normalized_value for v in definition.values)
                    )
                ),
                float(bool(NEGATION.search(match_form(context))) and not negative_preserved),
                float(bool(OTHER_OBJECT.search(match_form(context)))),
                float(
                    bool(RANGE.search(match_form(answer.quote)))
                    and not RANGE.search(match_form(answer.value))
                ),
                float(len({value_key(v, definition) for v in named}) > 1),
                float(bool(answer.risks & 1)),
                float(bool(answer.risks & 2)),
                float(bool(answer.risks & 4)),
            ),
            strict=True,
        )
    )
