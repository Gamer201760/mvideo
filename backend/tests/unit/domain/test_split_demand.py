from collections import Counter

from app.domain.demand import ngrams, tokens, value_key
from app.domain.requirement import AttributeUsage, CategoryUsage, rank_required
from app.domain.split import Split, pick_new_categories, split_of


def test_split_is_deterministic_and_close_to_shares() -> None:
    first = [split_of(sku, 42, 0.1, 0.1) for sku in range(20_000)]
    again = [split_of(sku, 42, 0.1, 0.1) for sku in range(20_000)]
    counts = Counter(first)

    assert first == again
    assert 0.08 < counts[Split.TEST] / 20_000 < 0.12
    assert 0.08 < counts[Split.VAL] / 20_000 < 0.12
    assert first != [split_of(sku, 7, 0.1, 0.1) for sku in range(20_000)]


def test_new_categories_respect_size_bounds_and_exclusions() -> None:
    sizes = {1: 50, 2: 500, 3: 800, 4: 900, 5: 10_000, 6: 700}

    picked = pick_new_categories(sizes, 42, 2, 100, 1000, exclude={3})

    assert len(picked) == 2
    assert set(picked) <= {2, 4, 6}
    assert picked == pick_new_categories(sizes, 42, 2, 100, 1000, exclude={3})


def test_tokens_split_digits_and_units() -> None:
    assert tokens("Смартфон 256Гб, экран 6,7″ Ёлка") == [
        "смартфон",
        "256",
        "гб",
        "экран",
        "6.7",
        "елка",
    ]


def test_value_key_requires_unit_for_numbers() -> None:
    assert value_key("256", "ГБ") == "256 гб"
    assert value_key("256", None) is None
    assert value_key("черный", None) == "черный"
    assert value_key("очень длинное название модели", None) is None


def test_ngrams_cover_unit_phrases() -> None:
    grams = set(ngrams("iphone 15 256гб черный"))

    assert {"256 гб", "черный", "iphone 15"} <= grams


def test_rank_required_puts_brand_model_first_and_filters_low_coverage() -> None:
    category = CategoryUsage(10, cards=100, clicks=1000, query_clicks=500)
    usages = {
        "Бренд": AttributeUsage("Бренд", 100, 1000),
        "Модель": AttributeUsage("Модель", 90, 900),
        "Цвет": AttributeUsage("Цвет", 80, 950),
        "Объем памяти": AttributeUsage("Объем памяти", 70, 600),
        "Гарантия": AttributeUsage("Гарантия", 100, 1000),
        "Редкий": AttributeUsage("Редкий", 5, 10),
    }

    rows = rank_required(category, usages, {"Цвет": 100}, top_n=6, min_coverage=0.3)

    assert [r.attribute for r in rows] == ["Бренд", "Модель", "Цвет", "Объем памяти"]
    color = rows[2]
    assert color.query_share == 0.2
    assert color.weight == 210.0
