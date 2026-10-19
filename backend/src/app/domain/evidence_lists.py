import re
from dataclasses import replace

from app.domain.attribute_flow import FieldAnswer
from app.domain.card_text import match_form
from app.domain.evidence_relations import compatibility_field
from app.domain.evidence_words import tokens


def list_evidence(answer: FieldAnswer) -> tuple[FieldAnswer, ...]:
    if answer.unit:
        return ()
    separator = r"[,;]"
    if compatibility_field(answer.attribute):
        separator += r"|\b(?:и|and)\b"
    parts = tuple(part.strip() for part in re.split(separator, answer.value) if part.strip())
    if len(parts) < 2 or len({tokens(part) for part in parts}) != len(parts):
        return ()
    actual = [
        (token, match.start(), match.end())
        for match in re.finditer(r"[a-zа-я0-9]+", match_form(answer.quote))
        for token in tokens(match[0])
    ]
    result = []
    for part in parts:
        expected = tokens(part)
        position = next(
            (
                i
                for i in range(len(actual))
                if tuple(t[0] for t in actual[i : i + len(expected)]) == expected
            ),
            None,
        )
        if not expected or position is None:
            return ()
        start, end = actual[position][1], actual[position + len(expected) - 1][2]
        if answer.quote[end:].lstrip().startswith(":"):
            return ()
        result.append(
            replace(
                answer,
                value=part,
                quote=answer.quote[start:end],
                start=answer.start + start,
                end=answer.start + end,
            )
        )
    return tuple(result)
