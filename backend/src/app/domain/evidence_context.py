import re
from dataclasses import dataclass, replace

from app.domain.attribute_flow import CatalogField, FieldAnswer
from app.domain.card_text import match_form
from app.domain.evidence_relations import (
    compatibility_error,
    compatibility_field,
    measurement_named,
)
from app.domain.evidence_signals import field_forms, words
from app.domain.evidence_uncertainty import SPECULATION
from app.domain.evidence_words import contains_value, field_matches, tokens
from app.domain.values import COLOR_BASES, COLOR_WORDS, canonical_text

SENTENCE = re.compile(r"[;!?\n]|(?<!\d)[.]|[.](?!\d)")
CLAUSE = re.compile(r",(?!\d|\s*(?:если|только|при)\b)|\b(?:но|однако|а также|а|и)\b")
OBJECT = re.compile(r"\b(упаков|короб|чех|аксессуар)\w*\b")
FOREIGN = re.compile(
    r"\b(?:совместим\w*|подходит\w*|для\s+(?:телефон\w*|смартфон\w*|модел\w*|ноутбук\w*)"
    r"|друг\w*\s+(?:модел\w*|товар\w*|телефон\w*)|предыдущ\w*\s+модел\w*|в отличие от)\b"
)
MODEL_REFERENCE = re.compile(r"\bу модели\s+([^\s,;.!?]+)")
NEGATION = re.compile(r"\b(?:не|нет|без|отсутств\w*|not|without|no)\b")
POSITIVE = frozenset({"да", "yes", "true", "есть", "поддерживается"})
NEGATIVE = frozenset({"нет", "no", "false", "отсутствует", "не поддерживается"})


@dataclass(frozen=True, slots=True)
class EvidenceContext:
    text: str
    value: str
    field_named: bool
    error: str | None = None


def sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    boundaries = tuple(SENTENCE.finditer(text))
    return (
        max((m.end() for m in boundaries if m.end() <= start), default=0),
        min((m.start() for m in boundaries if m.end() >= end), default=len(text)),
    )


def object_error(sentence: str, title: str, forms: tuple[str, ...]) -> bool:
    if FOREIGN.search(match_form(sentence)) and not any(
        compatibility_field(form) for form in forms
    ):
        return True
    reference = MODEL_REFERENCE.search(match_form(sentence))
    if reference and not re.search(rf"(?<!\w){re.escape(reference[1])}(?!\w)", match_form(title)):
        return True
    references = OBJECT.findall(match_form(sentence))
    product = re.split(r"\b(?:с|для|и|в комплекте)\b", match_form(title), maxsplit=1)[0]
    allowed = " ".join((*forms, product))
    allowed_objects = set(OBJECT.findall(match_form(allowed)))
    return any(w not in allowed_objects for w in references)


def resolve_context(
    answer: FieldAnswer,
    definition: CatalogField | None,
    text: str,
    *,
    numeric: bool = False,
    fields: tuple[CatalogField, ...] = (),
) -> EvidenceContext:
    forms = field_forms(answer, definition)
    start, end = sentence_span(text, answer.start, answer.end)
    sentence = text[start:end]
    title = text.splitlines()[0] if "\n" in text else ""
    clauses = tuple(CLAUSE.finditer(match_form(sentence)))
    relative_start, relative_end = answer.start - start, answer.end - start
    left = max((m.end() for m in clauses if m.end() <= relative_start), default=0)
    right = min((m.start() for m in clauses if m.start() >= relative_end), default=len(sentence))
    local = sentence[left:right].strip()
    inherited = sentence[:left]
    speculative = SPECULATION.search(match_form(inherited))
    if speculative and not re.search(r"\w", inherited[speculative.end() :]):
        return EvidenceContext(local, answer.quote, False, "conditional_support")
    if any(
        re.search(rf"(?<!\w){re.escape(match_form(form))}\s*:", match_form(answer.value))
        for other in fields
        if other.attribute != answer.attribute
        for form in field_forms(replace(answer, attribute=other.attribute), other)
    ):
        return EvidenceContext(local, answer.quote, False, "field_mismatch")
    compatible = compatibility_field(answer.attribute)
    if compatible and (
        error := compatibility_error(answer, sentence, field_matches(sentence, forms))
    ):
        return EvidenceContext(local, answer.quote, False, error)
    if (FOREIGN.search(match_form(inherited)) and not compatible) or object_error(
        local, title, forms
    ):
        return EvidenceContext(local, answer.quote, False, "object_context")
    colon = sentence.find(":", left, right)
    if colon >= 0 and answer.end > start + colon:
        key, _, value = local.partition(":")
        literal = re.search(re.escape(match_form(answer.value)), match_form(local))
        labels = ("модель", "бренд", "цвет", "серия", *(f.attribute for f in fields))
        labels = (*labels, *(alias for f in fields for alias in f.aliases))
        labelled = field_matches(key, forms) or any(
            tokens(key)[: len(tokens(label))] == tokens(label) for label in labels if label
        )
        labelled = labelled or bool(
            re.match(
                r"^(?:да|нет|yes|no|true|false|неизвестно|не указано)\b", match_form(value).strip()
            )
        )
        inside_value = not labelled and literal is not None and literal.start() < local.index(":")
        if not inside_value:
            if not field_matches(key.strip(), forms):
                return EvidenceContext(local, value.strip(), False, "field_mismatch")
            return EvidenceContext(local, value.strip(), True)
    named = (
        field_matches(local, forms) or numeric and measurement_named(answer, local) or compatible
    )
    if not named and re.search(r",\s*а\s*$", inherited):
        previous = re.sub(r",\s*а\s*$", "", inherited).rsplit(",", 1)[-1]
        named = field_matches(previous, forms)
    if not named:
        literal = re.search(re.escape(match_form(answer.value)), match_form(local))
        prefix = local[: literal.start()] if literal else local[: max(0, relative_start - left)]
        for other in fields:
            if other.attribute != answer.attribute and field_matches(
                prefix, (other.attribute, *other.aliases)
            ):
                return EvidenceContext(local, answer.quote, False, "field_mismatch")
    if (
        not named
        and re.search(r"^(?:бренд|brand|марка|производитель)\b", match_form(answer.attribute))
        and canonical_text(answer.value) in set(COLOR_BASES.values()) | set(COLOR_WORDS.values())
    ):
        return EvidenceContext(local, answer.quote, False, "field_unconfirmed")
    if not named and numeric:
        first_number = re.search(r"\d", local)
        prefix = local[: first_number.start()] if first_number else local
        if definition or re.search(r"[a-zа-я]", match_form(prefix)):
            return EvidenceContext(local, answer.quote, False, "field_unconfirmed")
    if not named and (
        definition
        and definition.kind == "boolean"
        or canonical_text(answer.value) in POSITIVE | NEGATIVE
    ):
        return EvidenceContext(local, answer.quote, False, "field_unconfirmed")
    return EvidenceContext(local, answer.quote, named)


def negation_error(
    answer: FieldAnswer, context: EvidenceContext, forms: tuple[str, ...] = ()
) -> str | None:
    normalized = canonical_text(answer.value)
    local = context.text
    if normalized in POSITIVE | NEGATIVE:
        if re.search(
            r"\b(?:неизвест\w*|нет\s+(?:данных|информации)|не\s+указ\w*)\b", match_form(local)
        ):
            return "value_unconfirmed"
        negative = bool(NEGATION.search(match_form(local))) or bool(words(local) & NEGATIVE)
        positive = bool(words(local) & POSITIVE) or bool(
            re.search(
                r"\b(?:поддерж\w*|оснащ\w*|имеет|предусмотр\w*|встроен\w*)\b"
                r"|\bс\s+(?:встроенн\w*\s+)?(?:систем\w*|функци\w*|поддержк\w*)\b",
                match_form(local),
            )
        )
        if normalized in NEGATIVE:
            return None if negative else "negation_unconfirmed"
        return "negation" if negative else None if positive else "value_unconfirmed"
    for match in NEGATION.finditer(match_form(local)):
        tail_text = re.sub(
            r"^\s*(?:является|составляет|равен|равна|равно|соответствует)\b\s*",
            "",
            match_form(local[match.end() :]),
        )
        tail = tokens(tail_text)
        expected = tokens(answer.value)
        direct = tail[: len(expected)] == expected
        direct = direct or any(
            tail[: len(tokens(f)) + len(expected)] == (*tokens(f), *expected)
            for f in (answer.attribute, *forms)
        )
        absent = match[0].startswith("отсутств") and contains_value(
            answer.value, local[: match.start()]
        )
        previous = tokens(local[: match.start()])
        denied = previous[-len(expected) :] == expected and bool(
            re.match(r"(?:поддерж\w*|доступ\w*|предусмотр\w*)\b", tail_text.lstrip())
        )
        if (direct or absent or denied) and not NEGATION.search(normalized):
            return "negation"
    return None
