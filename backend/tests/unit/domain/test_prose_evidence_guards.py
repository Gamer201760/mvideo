import pytest
from tests.unit.domain.evidence_cases import extract


@pytest.mark.parametrize(
    "text",
    [
        "Модель оснащена не двумя микрофонами",
        "Модель оснащена не более чем двумя микрофонами",
        "Модель оснащена примерно двумя микрофонами",
        "Модель оснащена приблизительно двумя микрофонами",
        "Модель оснащена двумя микрофонами опционально",
        "Модель оснащена двумя микрофонами только при подключении адаптера",
        "Модель оснащена не 2 микрофонами",
        "Модель оснащена примерно 2 микрофонами",
        "Модель оснащена минимум двумя микрофонами",
        "Модель оснащена максимум двумя микрофонами",
        "Модель оснащена как минимум двумя микрофонами",
        "Модель оснащена свыше двух микрофонов",
        "Модель оснащена больше двух микрофонов",
        "Модель оснащена меньше двух микрофонов",
    ],
)
def test_count_does_not_discard_negation_uncertainty_or_condition(text: str) -> None:
    _, result = extract(text, "Количество микрофонов", "numeric", "2", "", text)
    assert not result.items
    assert result.rejections


@pytest.mark.parametrize(
    ("attribute", "unit", "compound"),
    [
        ("Мощность", "Вт", "Вт·ч"),
        ("Мощность", "Вт", "Вт*ч"),
        ("Мощность", "Вт", "Вт^2"),
        ("Вес", "кг", "кг·м"),
        ("Вес", "кг", "кг * м"),
        ("Вес", "кг", "кг/м"),
        ("Вес", "кг", "кг²"),
        ("Мощность", "Вт", "Вт ⋅ ч"),
        ("Мощность", "Вт", "Вт × ч"),
        ("Длина", '"', "″/ч"),
        ("Длина", '"', '" * ч'),
    ],
)
def test_quantity_does_not_shorten_compound_unit(attribute: str, unit: str, compound: str) -> None:
    quote = f"5 {compound}"
    _, result = extract(f"{attribute} составляет {quote}", attribute, "numeric", "5", unit, quote)
    assert not result.items
    assert result.rejections


@pytest.mark.parametrize(
    "text",
    [
        "Модель не совместима с Android",
        "Модель несовместима с Android",
        "Модель совместима не с Android, а с iOS",
        "Модель не поддерживает Android",
        "Устройство работает на Android",
        "Совместимость с Android неизвестна",
        "Совместимость с Android не указана",
        "Модель может быть совместима с Android",
        "Проверяется совместимость с Android",
        "Модель совместима с Android-приложениями",
    ],
)
def test_compatibility_requires_positive_relation(text: str) -> None:
    _, result = extract(text, "Совместимые операционные системы", "free", "Android", "", "Android")
    assert not result.items
    assert result.rejections


@pytest.mark.parametrize("kind", ["boolean", "free"])
def test_repeated_boolean_value_cannot_pass_by_list_decomposition(kind: str) -> None:
    _, result = extract(
        "Шумоподавление: Да", "Шумоподавление", kind, "Да, Да", "", "Шумоподавление: Да"
    )
    assert not result.items
    assert result.rejections
