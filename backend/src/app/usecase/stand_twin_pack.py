from collections.abc import Iterator, Sequence
from typing import Protocol

from app.domain.lexicon import Lexicon
from app.domain.profile import BRAND, MODEL, TZ_REQUIRED
from app.domain.twin import twin_title
from app.domain.values import canonical_key, display_value
from app.usecase.baseline_ports import CardRecord, RequiredRecord
from app.usecase.stand_ports import StandTwin
from app.usecase.twin_pass import numeric_of
from app.usecase.twin_ports import GoldRow

TRAIN = frozenset({"train"})


class TwinRows(Protocol):
    def cards(self, splits: frozenset[str] | None, batch: int) -> Iterator[list[CardRecord]]: ...

    def gold_rows(
        self, splits: frozenset[str], attributes: frozenset[str]
    ) -> Iterator[Sequence[GoldRow]]: ...


def twin_attributes(required: Sequence[RequiredRecord],
                    chosen: frozenset[int]) -> dict[int, frozenset[str]]:
    wanted: dict[int, set[str]] = {c: {BRAND, MODEL, *TZ_REQUIRED.get(c, ())} for c in chosen}
    for record in required:
        if record.category_id in wanted:
            wanted[record.category_id].add(record.attribute)
    return {c: frozenset(names) for c, names in wanted.items()}


def build_stand_twins(rows: TwinRows, lexicon: Lexicon, required: Sequence[RequiredRecord],
                      chosen: frozenset[int], per_category: int) -> list[StandTwin]:
    wanted = twin_attributes(required, chosen)
    left = dict.fromkeys(chosen, per_category)
    titles: dict[int, tuple[int, str]] = {}
    for batch in rows.cards(TRAIN, 5000):
        for card in batch:
            category = card.category_id
            if category is None or left.get(category, 0) <= 0:
                continue
            title = twin_title(card.title)
            if title:
                titles[card.sku_id] = (category, title)
                left[category] -= 1
    values: dict[int, dict[str, tuple[str, str]]] = {}
    names = frozenset(a for group in wanted.values() for a in group)
    for chunk in rows.gold_rows(TRAIN, names):
        for sku, attribute, value, unit in chunk:
            owner = titles.get(sku)
            if owner is None or not value or attribute not in wanted[owner[0]]:
                continue
            key = canonical_key(value, unit, numeric_of(lexicon, attribute))
            values.setdefault(sku, {})[attribute] = (key, display_value(value, unit))
    twins = []
    for sku in sorted(titles):
        found = values.get(sku, {})
        if not found:
            continue
        brand, model = found.get(BRAND), found.get(MODEL)
        twins.append(StandTwin(sku_id=sku, title=titles[sku][1], brand=brand[0] if brand else "",
                               model=model[0] if model else "", values=found))
    return twins
