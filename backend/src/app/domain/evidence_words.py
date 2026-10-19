import re

from app.domain.values import canonical_text


def stem(word: str) -> str:
    if len(word) < 4:
        return word
    for ending in (
        "овый",
        "овая",
        "овое",
        "овые",
        "ого",
        "ому",
        "ами",
        "ями",
        "ый",
        "ий",
        "ая",
        "ое",
        "ом",
        "ем",
        "ой",
        "ей",
        "ов",
        "ев",
        "а",
        "я",
        "ы",
        "и",
        "у",
        "ю",
        "ь",
        "е",
    ):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)]
    return word


def tokens(value: str) -> tuple[str, ...]:
    return tuple(stem(w) for w in re.findall(r"[a-zа-я0-9]+", canonical_text(value)))


def contains_value(value: str, evidence: str) -> bool:
    expected, actual = tokens(value), tokens(evidence)
    return bool(expected) and any(
        actual[i : i + len(expected)] == expected for i in range(len(actual))
    )


def field_matches(value: str, forms: tuple[str, ...]) -> bool:
    actual = tokens(value)
    neutral = {"встроенн", "основн", "внутренн", "непрерывн", "с", "систем"}
    return any(
        contains_value(form, value)
        or len(expected := tokens(form)) > 1
        and not set(expected) & {"на", "в", "из", "от", "до", "to", "from"}
        and any(
            sorted(word for word in actual[i : i + size] if word in expected or word not in neutral)
            == sorted(expected)
            for size in range(len(expected), len(expected) + 3)
            for i in range(len(actual) - size + 1)
        )
        for form in forms
    )
