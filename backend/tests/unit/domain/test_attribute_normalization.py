import pytest

from app.domain.attribute_flow import CatalogField, FieldAnswer
from app.domain.attribute_normalization import normalize_answer


@pytest.mark.parametrize("raw", ["green", "зеленая", "зеленый", "зелёный"])
@pytest.mark.parametrize("vocabulary", [(), ("green",), ("зеленая",), ("синий",)])
def test_color_canon_does_not_depend_on_catalog_vocabulary(
    raw: str, vocabulary: tuple[str, ...]
) -> None:
    text = f"Цвет: {raw}"
    answer = FieldAnswer("Цвет", "supported", raw, "", raw, 6, len(text))
    normalized = normalize_answer(answer, CatalogField("Цвет", "categorical", "", vocabulary))
    assert normalized.normalized_value == "зеленый"
    assert text[normalized.start : normalized.end] == normalized.quote == raw
    assert normalized.value == raw


def test_schema_free_extra_color_uses_the_same_canon() -> None:
    answer = FieldAnswer("Цвет корпуса", "supported", "green", "", "green", 0, 5)
    assert normalize_answer(answer, None).normalized_value == "зеленый"


@pytest.mark.parametrize("attribute", ["Описание", "Модель", "Материал", "Бренд"])
def test_arbitrary_free_text_does_not_use_color_canon(attribute: str) -> None:
    answer = FieldAnswer(attribute, "supported", "Green", "", "Green", 0, 5)
    assert normalize_answer(answer, CatalogField(attribute, "free", "")).normalized_value == "Green"
