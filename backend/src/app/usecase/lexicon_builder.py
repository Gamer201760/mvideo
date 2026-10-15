from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.lexicon import Lexicon, LexiconEntry, value_tokens
from app.domain.profile import BRAND, YES_NO, AttributeProfile, Kind, profile_attribute
from app.domain.values import canonical_key, display_value


@dataclass(frozen=True, slots=True)
class LexiconConfig:
    min_count: int = 2
    max_categorical: int = 3000
    max_free: int = 30000


@dataclass(frozen=True, slots=True)
class TrainValue:
    category_id: int
    attribute: str
    value: str
    unit: str | None


def build_lexicon(rows: Iterable[TrainValue], config: LexiconConfig | None = None) -> Lexicon:
    config = config or LexiconConfig()
    values: dict[str, Counter[tuple[str, str | None]]] = defaultdict(Counter)
    per_category: dict[tuple[int, str], Counter[tuple[str, str | None]]] = defaultdict(Counter)
    for row in rows:
        pair = (row.value, row.unit)
        values[row.attribute][pair] += 1
        per_category[(row.category_id, row.attribute)][pair] += 1
    profiles = {name: profile_attribute(name, counter) for name, counter in values.items()}
    priors: dict[tuple[int, str], dict[str, float]] = {}
    for (category, attribute), counter in per_category.items():
        profile = profiles[attribute]
        keys: Counter[str] = Counter()
        for (value, unit), count in counter.items():
            keys[canonical_key(value, unit, profile.numeric)] += count
        total = sum(keys.values())
        priors[(category, attribute)] = {k: round(c / total, 6) for k, c in keys.items()}
    entries = [e for name, profile in profiles.items()
               for e in attribute_entries(profile, values[name], config)]
    return Lexicon(profiles, entries, priors)


def attribute_entries(
    profile: AttributeProfile, counter: Counter[tuple[str, str | None]], config: LexiconConfig
) -> list[LexiconEntry]:
    if profile.kind in (Kind.NUMERIC, Kind.BOOLEAN):
        return []
    keys: Counter[str] = Counter()
    shown: dict[str, Counter[str]] = defaultdict(Counter)
    for (value, unit), count in counter.items():
        key = canonical_key(value, unit, False)
        if key in YES_NO:
            continue
        keys[key] += count
        shown[key][display_value(value, unit)] += count
    limit = config.max_free if profile.kind is Kind.FREE else config.max_categorical
    min_count = 1 if profile.name == BRAND else config.min_count
    entries: list[LexiconEntry] = []
    for key, count in keys.most_common(limit):
        if count < min_count:
            break
        display = shown[key].most_common(1)[0][0]
        tokens = value_tokens(key)
        if len(tokens) == 1 and tokens[0].replace(".", "").isdigit():
            continue
        entries.append(LexiconEntry(profile.name, tokens, key, display))
    return entries
