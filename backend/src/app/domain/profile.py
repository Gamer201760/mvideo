import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from app.domain.card_text import match_form
from app.domain.values import canonical_unit, leading_quantity

STEM = 5
STOP_WORDS = frozenset({"для", "или", "при", "без", "под", "над", "тип", "вид", "and", "the"})
NAME_WORD = re.compile(r"[a-zа-я]+")
YES_NO = frozenset({"да", "нет", "yes", "no", "есть", "отсутствует", "присутствует"})
NUMERIC_SHARE = 0.8
CATEGORICAL_DISTINCT = 400
CATEGORICAL_TOP_SHARE = 0.8
CATEGORICAL_TOP = 50

BRAND = "Бренд"
MODEL = "Модель"

TZ_REQUIRED: dict[int, tuple[str, ...]] = {
    761: (
        "Бренд",
        "Модель",
        "Встроенная память (ROM)",
        "Диагональ",
        "Емкость аккумулятора",
        "Цвет",
    ),
    987: (
        "Бренд",
        "Процессор",
        "Оперативная память (RAM)",
        "Общий объем накопителя",
        "Диагональ экрана",
        "Цвет",
    ),
}


class Kind(StrEnum):
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    BOOLEAN = "boolean"
    FREE = "free"


@dataclass(frozen=True, slots=True)
class AttributeProfile:
    name: str
    kind: Kind
    unit: str
    keywords: tuple[str, ...]

    @property
    def numeric(self) -> bool:
        return self.kind is Kind.NUMERIC


def name_keywords(name: str) -> tuple[str, ...]:
    words = NAME_WORD.findall(match_form(name))
    stems = [w[:STEM] for w in words if len(w) >= 3 and w not in STOP_WORDS]
    return tuple(dict.fromkeys(stems))


def keyword_overlap(keywords: tuple[str, ...], text: str) -> float:
    if not keywords:
        return 0.0
    stems = set(name_keywords(text))
    return sum(1 for k in keywords if k in stems) / len(keywords)


def name_similarity(keywords: tuple[str, ...], text: str) -> float:
    stems = set(name_keywords(text))
    union = stems | set(keywords)
    return len(stems & set(keywords)) / len(union) if union else 0.0


def profile_attribute(name: str, values: Counter[tuple[str, str | None]]) -> AttributeProfile:
    total = sum(values.values())
    keywords = name_keywords(name)
    if total == 0:
        return AttributeProfile(name, Kind.FREE, "", keywords)
    yes_no = sum(c for (v, _), c in values.items() if match_form(v).strip() in YES_NO)
    if yes_no / total >= NUMERIC_SHARE:
        return AttributeProfile(name, Kind.BOOLEAN, "", keywords)
    units: Counter[str] = Counter()
    numeric = 0
    for (value, unit), count in values.items():
        quantity = leading_quantity(value, unit)
        if quantity is not None:
            numeric += count
            units[quantity.unit or (canonical_unit(unit) if unit else "") or ""] += count
    if numeric / total >= NUMERIC_SHARE:
        unit = units.most_common(1)[0][0] if units else ""
        return AttributeProfile(name, Kind.NUMERIC, unit, keywords)
    distinct = len(values)
    top = sum(c for _, c in values.most_common(CATEGORICAL_TOP))
    if distinct <= CATEGORICAL_DISTINCT or top / total >= CATEGORICAL_TOP_SHARE:
        return AttributeProfile(name, Kind.CATEGORICAL, "", keywords)
    return AttributeProfile(name, Kind.FREE, "", keywords)
