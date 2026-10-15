from app.domain.twin import (
    TwinEntry,
    TwinQuery,
    TwinValue,
    accepted,
    is_twin,
    title_numbers,
    twin_title,
    vote,
)


def entry(sku: int, title: str, brand: str = "samsung", color: str = "черный") -> TwinEntry:
    normalized = twin_title(title)
    return TwinEntry(sku, normalized, title_numbers(normalized), brand, f"m{sku}",
                     {"Цвет": TwinValue(color, color), "Вес": TwinValue("190", "190 г")})


def query(title: str, brand: str | None = None) -> TwinQuery:
    normalized = twin_title(title)
    return TwinQuery(normalized, title_numbers(normalized), brand)


def test_title_numbers_normalize_format() -> None:
    assert title_numbers(twin_title("Galaxy A55 8/256GB 6,60\"")) == {"55", "8", "256", "6.6"}
    assert title_numbers(twin_title("Кабель 1.0 м, 007")) == {"1", "7"}


def test_twin_requires_same_numbers() -> None:
    near = entry(1, "Смартфон Samsung Galaxy A55 8/128GB")
    assert not is_twin(near, query("Смартфон Samsung Galaxy A55 8/256GB", "samsung"), 0.95, 0.5)
    same = entry(2, "Смартфон Samsung Galaxy A55 8/256GB")
    assert is_twin(same, query("Смартфон Samsung Galaxy A55 8/256GB", "samsung"), 0.95, 0.5)


def test_twin_requires_brand_match_or_brand_in_title() -> None:
    twin = entry(1, "Смартфон Galaxy A55 8/256GB")
    assert not is_twin(twin, query("Смартфон Galaxy A55 8/256GB", "xiaomi"), 0.9, 0.5)
    assert not is_twin(twin, query("Смартфон Galaxy A55 8/256GB"), 0.9, 0.5)
    assert is_twin(twin, query("Смартфон Samsung Galaxy A55 8/256GB"), 0.9, 0.5)


def test_twin_requires_similarity_floor() -> None:
    twin = entry(1, "Смартфон Samsung A55 8/256GB")
    assert not is_twin(twin, query("Смартфон Samsung A55 8/256GB", "samsung"), 0.4, 0.5)


def test_vote_weights_by_similarity_and_skips_false_twins() -> None:
    q = query("Смартфон Samsung Galaxy A55 8/256GB", "samsung")
    neighbors = [
        (entry(1, "Смартфон Samsung Galaxy A55 8/256GB", color="черный"), 0.99),
        (entry(2, "Samsung Galaxy A55 8/256GB синий", color="синий"), 0.7),
        (entry(3, "Samsung Galaxy A55 8/256GB синий", color="синий"), 0.6),
        (entry(4, "Смартфон Samsung Galaxy A55 8/128GB", color="белый"), 0.98),
    ]
    transfers = vote(q, neighbors, ["Цвет", "Вес", "Диагональ"], 0.5)
    assert transfers["Цвет"].key == "синий"
    assert transfers["Цвет"].support == 2
    assert transfers["Вес"].twin_sku == 1
    assert transfers["Вес"].exact
    assert "Диагональ" not in transfers
    assert set(accepted(transfers, 0.8)) == {"Вес"}
