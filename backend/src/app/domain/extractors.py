import re
from collections.abc import Iterator, Mapping

from app.domain.candidate import (
    Candidate,
    SellerRange,
    Source,
    best_attributes,
    is_range,
    name_affinity,
    nearby_affinity,
    parse_range,
)
from app.domain.card_text import CardText
from app.domain.lexicon import Lexicon
from app.domain.profile import BRAND, MODEL, AttributeProfile, Kind
from app.domain.values import (
    NUMBER,
    canonical_text,
    canonical_unit,
    format_number,
    leading_quantity,
    parse_number,
)

UNIT = (
    r"гб|gb|тб|tb|мб|mb|мач|mah|ма\*ч|мa\*ч|ма·ч|\"|”|″|''|дюйм[a-zа-я]*|inch|мм|mm|см|cm|"
    r"кг|kg|гр|г|вт|w|квт|kw|л|литр[a-zа-я]*|мпикс|мп|mp|ггц|ghz|мгц|mhz|гц|hz|шт|дб|db"
)
QUANTITY = re.compile(rf"(?<![\d.,])({NUMBER})[\s-]*({UNIT})(?![a-zа-я])")
SLASH_MEMORY = re.compile(r"(?<![\d.,])(\d+)\s*/\s*(\d+)\s*(гб|gb|тб|tb)(?![a-zа-я])")
KEY_VALUE = re.compile(r"^[ \t]*[•\-–*]?[ \t]*([^:\n]{2,60}?)[ \t]*:[ \t]*([^\n]{1,120}?)[ \t]*$",
                       re.MULTILINE)
MIN_AFFINITY = 0.5


def unit_of(raw: str) -> str | None:
    if raw.startswith("дюйм"):
        return '"'
    if raw.startswith("литр"):
        return "л"
    return canonical_unit(raw)


def seller_ranges(
    card: CardText, profiles: Mapping[str, AttributeProfile]
) -> dict[str, SellerRange]:
    ranges: dict[str, SellerRange] = {}
    seller = card.text[card.seller_start:]
    for line in KEY_VALUE.finditer(seller):
        for name in best_attributes(profiles, line.group(1), MIN_AFFINITY):
            if profiles[name].numeric:
                parsed = parse_range(line.group(2))
                if parsed is not None:
                    ranges.setdefault(name, parsed)
    return ranges


def key_value_candidates(
    card: CardText, profiles: Mapping[str, AttributeProfile], lexicon: Lexicon,
    category: int | None,
) -> Iterator[Candidate]:
    for line in KEY_VALUE.finditer(card.text):
        key, value = line.group(1), line.group(2)
        start, end = line.start(2), line.end(2)
        zone = card.zone(line.start())
        source = Source.SELLER if zone == "seller" else Source.KEY_VALUE
        for name in best_attributes(profiles, key, MIN_AFFINITY):
            profile = profiles[name]
            affinity = name_affinity(profile, key)
            if profile.numeric:
                quantity = leading_quantity(value, profile.unit)
                if quantity is None or is_range(value):
                    continue
                canon = format_number(quantity.number)
                shown = f"{canon} {profile.unit}".strip()
            else:
                canon = canonical_text(value)
                shown = lexicon.display(name, canon) or value.strip()
            yield Candidate(name, canon, shown, card.span(start, end), start, end, source, zone,
                            affinity, lexicon.prior(category, name, canon), 0)


def dictionary_candidates(
    card: CardText, profiles: Mapping[str, AttributeProfile], lexicon: Lexicon,
    category: int | None,
) -> Iterator[Candidate]:
    attributes = frozenset(n for n, p in profiles.items() if not p.numeric)
    for found in lexicon.matches(card.tokens, attributes):
        start = card.tokens[found.first].start
        end = card.tokens[found.last].end
        entry = found.entry
        profile = profiles[entry.attribute]
        yield Candidate(entry.attribute, entry.key, entry.display, card.span(start, end), start,
                        end, Source.DICTIONARY, card.zone(start),
                        nearby_affinity(card, profile, start),
                        lexicon.prior(category, entry.attribute, entry.key), 0)


def number_candidates(
    card: CardText, profiles: Mapping[str, AttributeProfile], lexicon: Lexicon,
    category: int | None, ranges: Mapping[str, SellerRange],
) -> Iterator[Candidate]:
    numeric = {n: p for n, p in profiles.items() if p.kind is Kind.NUMERIC and p.unit}
    if not numeric:
        return
    spans: list[tuple[float, str, int, int, int]] = []
    for m in SLASH_MEMORY.finditer(card.match):
        unit = unit_of(m.group(3)) or ""
        spans.append((parse_number(m.group(1)), unit, m.start(1), m.end(1), 0))
        spans.append((parse_number(m.group(2)), unit, m.start(2), m.end(3), 1))
    for m in QUANTITY.finditer(card.match):
        spans.append((parse_number(m.group(1)), unit_of(m.group(2)) or "", m.start(), m.end(), -1))
    for number, unit, start, end, slot in spans:
        if start >= card.seller_start:
            continue
        for name, profile in numeric.items():
            if profile.unit != unit:
                continue
            canon = format_number(number)
            fit = ranges[name].fit(number) if name in ranges else 0
            yield Candidate(name, canon, f"{canon} {unit}", card.span(start, end), start, end,
                            Source.NUMBER, card.zone(start), nearby_affinity(card, profile, start),
                            lexicon.prior(category, name, canon), fit, slot)


def title_model_candidates(
    card: CardText, brands: list[Candidate], lexicon: Lexicon, category: int | None
) -> Iterator[Candidate]:
    in_title = [b for b in brands if b.zone == "title"]
    if not in_title:
        return
    brand = min(in_title, key=lambda b: b.start)
    raw = card.text[brand.end:card.title_end]
    lead = len(raw) - len(raw.lstrip(" -"))
    value = raw.strip(" -")
    if len(value) < 2:
        return
    start = brand.end + lead
    end = start + len(value)
    canon = canonical_text(value)
    yield Candidate(MODEL, canon, value, card.span(start, end), start, end, Source.TITLE_MODEL,
                    "title", 1.0, lexicon.prior(category, MODEL, canon), 0)


def extract_candidates(
    card: CardText, profiles: Mapping[str, AttributeProfile], lexicon: Lexicon,
    category: int | None,
) -> list[Candidate]:
    ranges = seller_ranges(card, profiles)
    found = list(key_value_candidates(card, profiles, lexicon, category))
    found.extend(dictionary_candidates(card, profiles, lexicon, category))
    found.extend(number_candidates(card, profiles, lexicon, category, ranges))
    if MODEL in profiles:
        brands = [c for c in found if c.attribute == BRAND and c.source == Source.DICTIONARY]
        found.extend(title_model_candidates(card, brands, lexicon, category))
    return found
