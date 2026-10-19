from app.domain.attribute_flow import CatalogCandidate, FieldAnswer
from app.domain.card_text import CardText, match_form, tokenize
from app.domain.extractors import extract_candidates
from app.domain.lexicon import Lexicon, LexiconEntry, value_tokens
from app.domain.profile import AttributeProfile, Kind, name_keywords
from app.domain.scoring import pick_values


def regex_answers(text: str, category: CatalogCandidate) -> tuple[FieldAnswer, ...]:
    profiles = {
        f.attribute: AttributeProfile(f.attribute, Kind(f.kind), f.unit, name_keywords(f.attribute))
        for f in category.fields
    }
    entries = [
        LexiconEntry(f.attribute, value_tokens(v), profiles[f.attribute].value_key(v), v)
        for f in category.fields
        for v in f.values
    ]
    matched = match_form(text)
    card = CardText(
        text, matched, tokenize(matched), text.find("\n") if "\n" in text else len(text), len(text)
    )
    candidates = extract_candidates(
        card, profiles, Lexicon(profiles, entries, {}), category.category_id
    )
    picks = pick_values(candidates, profiles)
    return tuple(
        FieldAnswer(
            name,
            "supported",
            pick.candidate.value,
            "",
            pick.candidate.evidence,
            pick.candidate.start,
            pick.candidate.end,
            source=pick.candidate.source,
        )
        for name, pick in picks.items()
    )
