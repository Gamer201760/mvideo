import re
from dataclasses import dataclass
from decimal import Decimal

from app.domain.card_text import match_form

NUMBER = r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,]\d+)?"
LEADING = re.compile(rf"^\s*({NUMBER})\s*(.*)$")
TRAILING_PUNCT = re.compile(r"[\s.,;:!]+$")
SLASH_SPACES = re.compile(r"\s*/\s*")
SPACES = re.compile(r"\s+")
WORD = re.compile(r"[a-zа-я]+")
UNIT_HEAD = re.compile(r"[^\s(,;]+")
LATIN = re.compile(r"[a-z]")
CYRILLIC = re.compile(r"[а-я]")
UNIT_LETTERS = str.maketrans("абвгекмнорстх", "abbgekmhopctx")

UNIT_ALIASES: dict[str, str] = {
    "гб": "гб",
    "gb": "гб",
    "гбайт": "гб",
    "гигабайт": "гб",
    "gib": "гиб",
    "гиб": "гиб",
    "гибибайт": "гиб",
    "тб": "тб",
    "tb": "тб",
    "мб": "мб",
    "mb": "мб",
    "мач": "мач",
    "mah": "мач",
    "ма*ч": "мач",
    "ма·ч": "мач",
    "мa*ч": "мач",
    '"': '"',
    "”": '"',
    "''": '"',
    "″": '"',
    "дюйм": '"',
    "дюйма": '"',
    "дюймов": '"',
    "inch": '"',
    "мм": "мм",
    "mm": "мм",
    "см": "см",
    "cm": "см",
    "м": "м",
    "км": "км",
    "km": "км",
    "кг": "кг",
    "kg": "кг",
    "г": "г",
    "гр": "г",
    "вт": "вт",
    "w": "вт",
    "квт": "квт",
    "kw": "квт",
    "мл": "мл",
    "л": "л",
    "литр": "л",
    "литра": "л",
    "мп": "мп",
    "мпикс": "мп",
    "mp": "мп",
    "гц": "гц",
    "hz": "гц",
    "ггц": "ггц",
    "ghz": "ггц",
    "мгц": "мгц",
    "mhz": "мгц",
    "шт": "шт",
    "ч": "ч",
    "час": "ч",
    "часа": "ч",
    "часов": "ч",
    "мин": "мин",
    "минута": "мин",
    "минуты": "мин",
    "минут": "мин",
    "дб": "дб",
    "db": "дб",
    "в": "в",
    "v": "в",
    "а": "а",
    "пикс": "пикс",
    "°с": "°с",
    "*с": "°с",
}

UNIT_SCALES: dict[str, tuple[str, float]] = {
    "кг": ("кг", 1.0),
    "г": ("кг", 0.001),
    "мм": ("мм", 1.0),
    "см": ("мм", 10.0),
    "м": ("мм", 1000.0),
    "км": ("мм", 1000000.0),
    '"': ("мм", 25.4),
    "вт": ("вт", 1.0),
    "квт": ("вт", 1000.0),
    "л": ("л", 1.0),
    "мл": ("л", 0.001),
    "гц": ("гц", 1.0),
    "мгц": ("гц", 1000000.0),
    "ггц": ("гц", 1000000000.0),
}
UNIT_SIGNATURES = {alias.translate(UNIT_LETTERS): unit for alias, unit in UNIT_ALIASES.items()}

COLOR_BASES: dict[str, str] = {
    "черн": "черный",
    "бел": "белый",
    "красн": "красный",
    "зелен": "зеленый",
    "сер": "серый",
    "желт": "желтый",
    "розов": "розовый",
    "фиолетов": "фиолетовый",
    "оранжев": "оранжевый",
    "коричнев": "коричневый",
    "бежев": "бежевый",
    "золот": "золотой",
    "серебрист": "серебристый",
    "голуб": "голубой",
    "бирюзов": "бирюзовый",
    "син": "синий",
}
ADJECTIVE_ENDINGS = ("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие", "ого", "его", "ую", "юю")
COLOR_WORDS: dict[str, str] = {
    "black": "черный",
    "white": "белый",
    "red": "красный",
    "алый": "красный",
    "blue": "синий",
    "green": "зеленый",
    "grey": "серый",
    "gray": "серый",
    "silver": "серебристый",
    "gold": "золотой",
    "pink": "розовый",
    "purple": "фиолетовый",
    "violet": "фиолетовый",
    "yellow": "желтый",
    "orange": "оранжевый",
    "brown": "коричневый",
    "beige": "бежевый",
    "navy": "темно-синий",
    "lavender": "лавандовый",
}


@dataclass(frozen=True, slots=True)
class Quantity:
    number: float
    unit: str


def parse_number(raw: str) -> float:
    return float("".join(match_form(raw).split()).replace(",", "."))


def format_number(value: float) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def canonical_unit(raw: str) -> str | None:
    unit = match_form(raw).strip().rstrip(".")
    canonical = UNIT_ALIASES.get(unit)
    if canonical is None and LATIN.search(unit) and CYRILLIC.search(unit):
        return UNIT_SIGNATURES.get(unit.translate(UNIT_LETTERS))
    return canonical


def leading_quantity(value: str, unit: str | None = None) -> Quantity | None:
    found = LEADING.match(match_form(value))
    if not found:
        return None
    number = parse_number(found.group(1))
    rest = found.group(2).strip()
    if not rest:
        canonical = canonical_unit(unit) if unit else ""
        return Quantity(number, canonical) if canonical is not None else None
    if rest[0] in "\"”″'":
        if re.match(r"\s*[/·⋅×*^²³]", rest.lstrip("\"”″'")):
            return None
        return Quantity(number, '"')
    first = UNIT_HEAD.match(rest)
    if first and re.match(r"\s*[/·⋅×*^²³]", rest[first.end() :]):
        return None
    canon = canonical_unit(first.group()) if first else None
    if canon is None:
        return None
    return Quantity(number, canon)


def quantity_in_unit(quantity: Quantity, unit: str) -> Quantity | None:
    target = canonical_unit(unit) if unit else ""
    if target is None:
        return None
    if quantity.unit == target:
        return Quantity(quantity.number, target)
    source_scale = UNIT_SCALES.get(quantity.unit)
    target_scale = UNIT_SCALES.get(target)
    if source_scale is None or target_scale is None or source_scale[0] != target_scale[0]:
        return None
    number = Decimal(str(quantity.number)) * Decimal(str(source_scale[1]))
    number /= Decimal(str(target_scale[1]))
    return Quantity(float(number), target)


def color_word(word: str) -> str:
    if word in COLOR_WORDS:
        return COLOR_WORDS[word]
    for stem, base in COLOR_BASES.items():
        if word.startswith(stem) and word[len(stem) :] in ADJECTIVE_ENDINGS:
            return base
    return word


def canonical_text(value: str) -> str:
    text = match_form(value)
    text = SLASH_SPACES.sub("/", text)
    text = SPACES.sub(" ", text).strip()
    text = TRAILING_PUNCT.sub("", text)
    return WORD.sub(lambda m: color_word(m.group()), text)


def canonical_key(
    value: str,
    unit: str | None,
    numeric: bool,
    *,
    target_unit: str | None = None,
) -> str:
    if numeric:
        quantity = leading_quantity(value, unit or target_unit)
        if quantity is not None:
            target = target_unit
            if target is None:
                target = UNIT_SCALES.get(quantity.unit, (quantity.unit, 1.0))[0]
            converted = quantity_in_unit(quantity, target)
            if converted is not None:
                number = format_number(converted.number)
                return number if target_unit is not None else f"{number} {converted.unit}".strip()
        return canonical_text(display_value(value, unit))
    return canonical_text(value)


def display_value(value: str, unit: str | None) -> str:
    if unit and unit not in value:
        return f"{value} {unit}"
    return value
