import re

from app.domain.attribute_flow import FieldAnswer
from app.domain.card_text import match_form
from app.domain.evidence_counts import count_evidence
from app.domain.evidence_words import field_matches


def compatibility_field(attribute: str) -> bool:
    return bool(
        re.search(
            r"^(?:совместим\w*|поддерживаем\w*)\s+(?:операцион\w*\s+систем\w*|ос|устройств\w*|платформ\w*)$",
            match_form(attribute).strip(),
        )
    )


def compatibility_error(answer: FieldAnswer, sentence: str, named: bool) -> str | None:
    text = match_form(sentence)
    if re.search(
        r"\b(?:неизвест\w*|не\s+указ\w*|может|могут|возможно|вероятно|проверяется|планиру\w*)\b",
        text,
    ):
        return "conditional_support"
    if re.search(r"\b(?:несовместим\w*|не\s+(?:совместим\w*|поддержива\w*|с|со|для))\b", text):
        return "negation"
    if re.search(rf"(?<!\w){re.escape(match_form(answer.value))}[-‑–]\w", text):
        return "object_context"
    if not named and not re.search(
        r"\b(?:совместим(?:а|о|ы)?|поддержива(?:ет|ют|ется|ются))\b", text
    ):
        return "field_unconfirmed"
    return None


def measurement_named(answer: FieldAnswer, local: str) -> bool:
    if count_evidence(answer, answer.quote) is not None:
        return True
    duration = re.match(r"^время\s+(.+)$", match_form(answer.attribute))
    if not duration or answer.unit not in {"ч", "час", "часа", "часов", "мин", "минут"}:
        return False
    form = duration[1]
    if form.startswith("автономн"):
        if not re.search(r"\b(?:одного заряда|заряд\w* аккумулятор\w*)\b", match_form(local)):
            return False
        form = form.split(" ", 1)[1] if " " in form else form
    return field_matches(answer.quote, (form,))
