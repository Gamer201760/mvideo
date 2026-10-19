import pytest
from tests.unit.domain.evidence_cases import extract

from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import CatalogCandidate, CatalogField, Extraction, FlowCard


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit"),
    [
        ("Бренд", "free", "Торговая марка: Novaline", "Novaline", ""),
        ("Диаметр щипцов для завивки", "numeric", "Щипцы для завивки диаметром 14 мм", "14", "мм"),
        ("Модель", "free", "Шторы Лес: совы AB-71", "Лес: совы AB-71", ""),
        ("Вид принта", "categorical", "Милые лесные звери: совы, зайцы", "лесные звери", ""),
        ("Вид принта", "free", "Шторы от бренда Novaline с дизайном — Лес: совы", "Лес: совы", ""),
        ("Вид принта", "categorical", "С рисунком — Лес: совы, зайцы", "Лес: совы, зайцы", ""),
        (
            "Модель",
            "free",
            "Коврик ZX-123-4 ряда для Orion 2022-н.в.",
            "ZX-123-4 ряда для Orion 2022-н.в.",
            "",
        ),
    ],
)
def test_aliases_word_order_and_colons_preserve_exact_evidence(
    attribute: str, kind: str, text: str, value: str, unit: str
) -> None:
    card, result = extract(text, attribute, kind, value, unit, text)
    assert len(result.items) == 1, result.validation_errors
    answer = result.items[0]
    assert card.text[answer.start : answer.end] == answer.quote == text
    assert not result.rejections


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit"),
    [
        ("Бренд", "free", "Модель: Novaline", "Novaline", ""),
        ("Бренд", "free", "Модель: Novaline", "Модель", ""),
        ("Модель", "free", "Цвет: Лес: совы AB-71", "Лес: совы AB-71", ""),
        ("Модель", "free", "Модель: AB-71 Pro", "AB-71", ""),
        ("Модель", "free", "Модель: 123", "123", "кг"),
        ("Модель", "free", "Модель: не ZX-123-4", "ZX-123-4", ""),
        ("Модель", "free", "Совместим с моделью ZX-123-4", "ZX-123-4", ""),
        ("Переход HDMI на USB", "boolean", "Переход USB на HDMI: Да", "Да", ""),
        ("Бренд", "free", "Торговая марка: не Novaline", "Novaline", ""),
        ("Бренд", "free", "Торговая марка: Novaline\nБренд: Aquila", "Novaline", ""),
        ("Особенности", "free", "Ортопедический матрас: Нет", "ортопедический матрас", ""),
        ("Особенности", "free", "Ортопедический матрас: неизвестно", "ортопедический матрас", ""),
        ("Диаметр щипцов для завивки", "numeric", "Щипцы для завивки длиной 14 мм", "14", "мм"),
        (
            "Диаметр щипцов для завивки",
            "numeric",
            "Щипцы для завивки диаметром до 14 мм",
            "14",
            "мм",
        ),
    ],
)
def test_alias_and_colon_fixes_keep_field_negation_and_range_guards(
    attribute: str, kind: str, text: str, value: str, unit: str
) -> None:
    _, result = extract(text, attribute, kind, value, unit, text)
    assert not result.items
    assert result.rejections


def composite(
    text: str, value: str, quote: str | None = None, flags: int = 0, unit: str = ""
) -> Extraction:
    field = CatalogField("Жанр", "categorical", "", ("Драма, Триллер", "Комедия"))
    card = FlowCard(1, text, (CatalogCandidate(7, "Фильмы", 0.99, (field,)),))
    return parse_batch(
        {
            "c": [
                {
                    "i": 0,
                    "k": 0,
                    "a": [{"f": 0, "v": value, "u": unit, "q": quote or text, "r": flags}],
                    "r": [],
                }
            ]
        },
        (card,),
    )[0]


def test_composite_uses_only_positive_flags_in_schema_vocabulary() -> None:
    text = "Драма: Да\nКомедия: Нет\nТриллер: Да"
    result = composite(text, "Драма, Триллер")
    assert len(result.items) == 1, result.validation_errors
    assert result.items[0].quote == text
    assert not result.rejections


def test_composite_cannot_add_a_unit_absent_from_flags() -> None:
    result = composite("Драма: Да\nТриллер: Да", "Драма, Триллер", unit="кг")
    assert not result.items
    assert result.rejections


@pytest.mark.parametrize(
    ("text", "value", "quote", "flags"),
    [
        ("Драма: Да\nТриллер: Нет", "Драма, Триллер", None, 0),
        ("Драма: Да\nТриллер: неизвестно", "Драма, Триллер", None, 0),
        ("Драма: Да", "Драма, Триллер", None, 0),
        ("Драма: Да\nТриллер: Да", "Драма, Комедия", None, 0),
        ("Драма: Да\nБалет: Да", "Драма, Балет", None, 0),
        ("Драма: Да\nТриллер: Да", "Драма, Драма", None, 0),
        ("Драма: Да\nТриллер: Да\nДрама: Нет", "Драма, Триллер", "Драма: Да\nТриллер: Да", 0),
        ("Драма: Да\nТриллер: Да", "Драма, Триллер", "Драма: Да", 0),
        ("Драма: Да\nТриллер: Да", "Драма, Триллер", None, 1),
        ("Драма: Да\nТриллер: Да", "Драма, Триллер", None, 2),
        ("Драма: Да только при покупке модуля\nТриллер: Да", "Драма, Триллер", None, 0),
    ],
)
def test_composite_rejects_unconfirmed_parts_and_conflicts(
    text: str, value: str, quote: str | None, flags: int
) -> None:
    result = composite(text, value, quote, flags)
    assert not result.items
    assert result.rejections
