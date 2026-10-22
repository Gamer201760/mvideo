import re

from app.domain.card_text import match_form
from app.domain.evidence_quantity_text import SIGNED, UNIT

SPECULATION = re.compile(
    r"\b(?:возможно|вероятно|предположительно|предполага\w*|неизвест\w*|"
    r"не\s+(?:указ\w*|подтвержден\w*)|может\s+быть|могут\s+быть)\b"
)
ALTERNATIVE = re.compile(r"\b(?:или|либо|or)\b")
POSTFIX = re.compile(
    rf"{SIGNED}\s*(?:{UNIT})?\s*(?:примерно|приблизительно|ориентировочно|"
    r"максимум|минимум|как минимум|как максимум|и более|и менее)(?!\w)"
)


def uncertainty_error(context: str, *, numeric: bool) -> str | None:
    text = match_form(context)
    if SPECULATION.search(text):
        return "conditional_support"
    if not numeric and ALTERNATIVE.search(text):
        return "conflicting_values"
    if numeric and (POSTFIX.search(text) or "±" in text):
        return "number_unconfirmed"
    return None
