from dataclasses import replace

from app.domain.attribute_flow import CatalogCandidate, Extraction, FieldAnswer
from app.domain.card_text import SellerParam, match_form, seller_line


def complete_seller_fields(
    extraction: Extraction,
    category: CatalogCandidate | None,
    text: str,
    seller: tuple[SellerParam, ...],
) -> Extraction:
    if category is None:
        return extraction
    known = {match_form(f.attribute): f.attribute for f in category.fields}
    items, extras = list(extraction.items), list(extraction.extra_fields)
    existing = {match_form(a.attribute) for a in (*items, *extras)}
    quotes = [a.quote for a in (*items, *extras) if a.status == "supported"]
    variants: dict[str, set[tuple[str, str | None]]] = {}
    for param in seller:
        variants.setdefault(match_form(param.name), set()).add((param.value.strip(), param.unit))
    for param in seller:
        name = match_form(param.name)
        quote = seller_line(param)
        start = text.find(quote)
        if (
            not name
            or not param.value.strip()
            or name in existing
            or start < 0
            or len(variants[name]) > 1
        ):
            continue
        if any(quote in evidence for evidence in quotes if evidence):
            continue
        answer = FieldAnswer(
            known.get(name, param.name.strip()),
            "supported",
            param.value.strip(),
            param.unit if param.unit and param.unit not in param.value else "",
            quote,
            start,
            start + len(quote),
            source="seller",
        )
        (items if name in known else extras).append(answer)
        existing.add(name)
        quotes.append(quote)
    return replace(extraction, items=tuple(items), extra_fields=tuple(extras))
