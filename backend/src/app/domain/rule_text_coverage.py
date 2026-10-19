from app.domain.attribute_flow import Extraction, FlowCard
from app.domain.card_text import match_form
from app.domain.evidence_words import tokens
from app.domain.values import canonical_text


def text_covered(card: FlowCard, result: Extraction) -> bool:
    category = card.candidates[0]
    definitions = {f.attribute: f for f in category.fields}
    lines = card.text.splitlines()
    title = lines[0] if lines else ""
    known = set(tokens(category.path))
    for answer in result.items:
        known.update(tokens(f"{answer.attribute} {answer.value} {answer.unit}"))
    if not set(tokens(title)) <= known:
        return False
    for line in lines[1:]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or not value.strip():
            return False
        covered = False
        for answer in result.items:
            field = definitions[answer.attribute]
            names = (field.attribute, *field.aliases)
            if match_form(key).strip() not in {match_form(n).strip() for n in names}:
                continue
            quoted_value = answer.quote.partition(":")[-1] if ":" in answer.quote else answer.quote
            if canonical_text(value) == canonical_text(quoted_value):
                covered = True
                break
        if not covered:
            return False
    return True
