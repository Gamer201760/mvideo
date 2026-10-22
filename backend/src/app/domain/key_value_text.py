import re
from collections.abc import Iterator, Mapping

from app.domain.candidate import best_attributes
from app.domain.card_text import match_form
from app.domain.profile import AttributeProfile

LABEL = re.compile(
    r"(?:^|[,;!?]|[.](?=\s))[ \t]*[•\-–*]?[ \t]*([^:\n,;.!?]{2,60}?)[ \t]*:[ \t]*",
    re.MULTILINE,
)
SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def key_value_spans(
    text: str, profiles: Mapping[str, AttributeProfile]
) -> Iterator[tuple[str, str, int, int]]:
    labels = {match_form(name) for name in profiles}
    labels.update(re.sub(r"\s*\((?:rom|ram)\)\s*$", "", name) for name in tuple(labels))
    literal = (
        re.compile(
            r"(?<!\w)("
            + "|".join(re.escape(name) for name in sorted(labels, key=len, reverse=True))
            + r")[ \t]*:[ \t]*"
        )
        if labels
        else None
    )
    found = {m.end(): m for m in LABEL.finditer(text) if best_attributes(profiles, m[1], 0.5)}
    if literal is not None:
        found.update((m.end(), m) for m in literal.finditer(text))
    matches = sorted(found.values(), key=lambda m: m.start(1))
    for index, match in enumerate(matches):
        start = match.end()
        newline = text.find("\n", start)
        end = newline if newline >= 0 else len(text)
        if index + 1 < len(matches):
            end = min(end, matches[index + 1].start(1))
        end = start + len(text[start:end].rstrip(" \t,;"))
        if start < end:
            yield match[1], text[start:end], start, end
