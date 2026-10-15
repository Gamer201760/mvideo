import re
from dataclasses import dataclass

from app.domain.card_text import match_form

NUMBER = r"\d+(?:[.,]\d+)?"
LEADING = re.compile(rf"^\s*({NUMBER})\s*(.*)$")
TRAILING_PUNCT = re.compile(r"[\s.,;:!]+$")
SLASH_SPACES = re.compile(r"\s*/\s*")
SPACES = re.compile(r"\s+")
WORD = re.compile(r"[a-zа-я]+")
UNIT_HEAD = re.compile(r"[^\s(/,;]+")

UNIT_ALIASES: dict[str, str] = {
    "гб": "гб", "gb": "гб", "гбайт": "гб", "гигабайт": "гб",
    "тб": "тб", "tb": "тб", "мб": "мб", "mb": "мб",
    "мач": "мач", "mah": "мач", "ма*ч": "мач", "ма·ч": "мач", "мa*ч": "мач",
    '"': '"', "”": '"', "''": '"', "″": '"', "дюйм": '"', "дюйма": '"', "дюймов": '"',
    "inch": '"', "мм": "мм", "mm": "мм", "см": "см", "cm": "см", "м": "м",
    "кг": "кг", "kg": "кг", "г": "г", "гр": "г",
    "вт": "вт", "w": "вт", "квт": "квт", "kw": "квт", "л": "л", "литр": "л", "литра": "л",
    "мп": "мп", "мпикс": "мп", "mp": "мп", "гц": "гц", "hz": "гц", "ггц": "ггц", "ghz": "ггц",
    "мгц": "мгц", "mhz": "мгц", "шт": "шт", "ч": "ч", "мин": "мин", "дб": "дб", "db": "дб",
    "в": "в", "v": "в", "а": "а", "пикс": "пикс", "°с": "°с", "*с": "°с",
}

COLOR_BASES: dict[str, str] = {
    "черн": "черный", "бел": "белый", "красн": "красный", "зелен": "зеленый",
    "сер": "серый", "желт": "желтый", "розов": "розовый", "фиолетов": "фиолетовый",
    "оранжев": "оранжевый", "коричнев": "коричневый", "бежев": "бежевый",
    "золот": "золотой", "серебрист": "серебристый", "голуб": "голубой", "бирюзов": "бирюзовый",
    "син": "синий",
}
ADJECTIVE_ENDINGS = ("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие", "ого", "его", "ую", "юю")
COLOR_WORDS: dict[str, str] = {
    "black": "черный", "white": "белый", "red": "красный", "алый": "красный",
    "blue": "синий", "green": "зеленый", "grey": "серый", "gray": "серый",
    "silver": "серебристый", "gold": "золотой", "pink": "розовый", "purple": "фиолетовый",
    "violet": "фиолетовый", "yellow": "желтый", "orange": "оранжевый", "brown": "коричневый",
    "beige": "бежевый", "navy": "темно-синий", "lavender": "лавандовый",
}


@dataclass(frozen=True, slots=True)
class Quantity:
    number: float
    unit: str


def parse_number(raw: str) -> float:
    return float(raw.replace(",", "."))


def format_number(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def canonical_unit(raw: str) -> str | None:
    unit = match_form(raw).strip().rstrip(".")
    return UNIT_ALIASES.get(unit)


def leading_quantity(value: str, unit: str | None = None) -> Quantity | None:
    found = LEADING.match(match_form(value))
    if not found:
        return None
    number = parse_number(found.group(1))
    rest = found.group(2).strip()
    if not rest:
        return Quantity(number, (canonical_unit(unit) if unit else None) or "")
    if rest[0] in "\"”″'":
        return Quantity(number, '"')
    first = UNIT_HEAD.match(rest)
    canon = canonical_unit(first.group()) if first else None
    if canon is None:
        return None
    return Quantity(number, canon)


def color_word(word: str) -> str:
    if word in COLOR_WORDS:
        return COLOR_WORDS[word]
    for stem, base in COLOR_BASES.items():
        if word.startswith(stem) and word[len(stem):] in ADJECTIVE_ENDINGS:
            return base
    return word


def canonical_text(value: str) -> str:
    text = match_form(value)
    text = SLASH_SPACES.sub("/", text)
    text = SPACES.sub(" ", text).strip()
    text = TRAILING_PUNCT.sub("", text)
    return WORD.sub(lambda m: color_word(m.group()), text)


def canonical_key(value: str, unit: str | None, numeric: bool) -> str:
    if numeric:
        quantity = leading_quantity(value, unit)
        if quantity is not None:
            return format_number(quantity.number)
    return canonical_text(value)


def display_value(value: str, unit: str | None) -> str:
    if unit and unit not in value:
        return f"{value} {unit}"
    return value
