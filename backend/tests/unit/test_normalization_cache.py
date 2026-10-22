import pytest

from app.domain.text_normalization import match_character, matching_text


@pytest.mark.parametrize(
    "text", ["ЁЛКИ １２８ ГБ", "١٢٣\u202fВт", "İ ſ Ｂｌａｃｋ", "", "A\nB", "𝟠𝟙_Ω"]
)
def test_text_cache_preserves_exact_character_normalization(text: str) -> None:
    expected = "".join(match_character(character) for character in text)
    assert matching_text(text) == expected
    assert matching_text(text) == expected


def test_text_cache_is_bounded_and_eviction_preserves_results() -> None:
    matching_text.cache_clear()
    for index in range(10000):
        assert matching_text(f"ITEM {index}") == f"item {index}"
    info = matching_text.cache_info()
    assert info.maxsize == info.currsize == 8192
    assert matching_text("ITEM 0") == "item 0"
    assert matching_text("ITEM 9999") == "item 9999"
    matching_text.cache_clear()
