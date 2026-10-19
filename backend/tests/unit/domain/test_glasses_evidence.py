import json
from pathlib import Path

import pytest
from tests.unit.domain.evidence_cases import extract

FIXTURE = json.loads((Path(__file__).parents[2] / "fixtures/glasses-card.json").read_text())


@pytest.mark.parametrize("proposal", FIXTURE["proposals"], ids=lambda p: p["attribute"])
def test_grounded_glasses_fields_keep_exact_quote(proposal: dict[str, str]) -> None:
    card, result = extract(
        FIXTURE["text"],
        proposal["attribute"],
        proposal["kind"],
        proposal["value"],
        proposal["unit"],
        proposal["quote"],
    )
    assert len(result.items) == 1, result.validation_errors
    answer = result.items[0]
    assert card.text[answer.start : answer.end] == answer.quote == proposal["quote"]
    assert not result.rejections


@pytest.mark.parametrize(
    ("attribute", "kind", "text", "value", "unit", "quote"),
    [
        (
            "Разрешение камеры",
            "numeric",
            "Камера 16 Мп, экран разрешением 12 Мп",
            "12",
            "Мп",
            "12 Мп",
        ),
        (
            "Количество микрофонов",
            "numeric",
            "Две камеры и один микрофон",
            "2",
            "",
            "Две камеры и один микрофон",
        ),
        (
            "Количество микрофонов",
            "numeric",
            "Совместим со смартфоном с двумя микрофонами",
            "2",
            "",
            "двумя микрофонами",
        ),
        (
            "Количество микрофонов",
            "numeric",
            "Предусмотрена возможность подключения двух внешних микрофонов",
            "2",
            "",
            "двух внешних микрофонов",
        ),
        (
            "Шумоподавление микрофонов",
            "boolean",
            "Микрофоны без системы шумоподавления",
            "Да",
            "",
            "системы шумоподавления",
        ),
        (
            "Время автономной видеосъемки",
            "numeric",
            "Одного заряда хватает до 4 часов видеосъемки или 8 часов воспроизведения музыки",
            "4",
            "ч",
            "4 часов видеосъемки",
        ),
        (
            "Время автономной видеосъемки",
            "numeric",
            "Одного заряда хватает до 4 часов видеосъемки или 8 часов воспроизведения музыки",
            "8",
            "ч",
            "8 часов воспроизведения музыки",
        ),
        (
            "Совместимые операционные системы",
            "free",
            "Совместима с Android, но не iOS",
            "Android, iOS",
            "",
            "Совместима с Android, но не iOS",
        ),
        (
            "Операционная система",
            "free",
            "Очки совместимы со смартфоном на базе Android",
            "Android",
            "",
            "Android",
        ),
        (
            "Совместимые операционные системы",
            "free",
            "Совместима с Android только при подключении адаптера",
            "Android",
            "",
            "Android",
        ),
        (
            "Функции",
            "free",
            "Поддерживает запись видео, фотографирование не предусмотрено",
            "запись видео, фотографирование",
            "",
            "Поддерживает запись видео, фотографирование не предусмотрено",
        ),
        (
            "Функции",
            "free",
            "Поддерживает запись видео и фотографирование",
            "запись видео, лазерное сканирование",
            "",
            "Поддерживает запись видео и фотографирование",
        ),
        (
            "Комплектация",
            "free",
            "В комплект входит кабель",
            "кабель, футляр",
            "",
            "В комплект входит кабель",
        ),
        (
            "Емкость аккумулятора",
            "numeric",
            "Емкость аккумулятора чехла составляет 1200 мА·ч",
            "1200",
            "мА·ч",
            "1200 мА·ч",
        ),
        (
            "Материал",
            "free",
            "Цвет: красный, материал: сталь",
            "красный, сталь",
            "",
            "Цвет: красный, материал: сталь",
        ),
    ],
)
def test_prose_support_does_not_allow_wrong_scope_range_or_list_item(
    attribute: str, kind: str, text: str, value: str, unit: str, quote: str
) -> None:
    _, result = extract(text, attribute, kind, value, unit, quote)
    assert not result.items
    assert result.rejections


def test_sentence_after_terminal_quote_cannot_change_product_scope() -> None:
    quote = "Габариты очков — 150×145×45 мм."
    _, result = extract(
        f"Очки\n{quote} Модель совместима со смартфоном.",
        "Габариты",
        "free",
        "150×145×45",
        "мм",
        quote,
    )
    assert len(result.items) == 1
