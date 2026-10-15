from app.domain.catalog import (
    BRAND,
    MODEL,
    Category,
    Offer,
    Param,
    category_paths,
    has_spec_block,
    split_offer,
)


def make_offer(params: tuple[Param, ...]) -> Offer:
    return Offer(
        sku_id=7,
        available=True,
        vendor="Samsung",
        model="Galaxy S24",
        name="Смартфон Samsung Galaxy S24 256 ГБ черный",
        category_id=100,
        params=params,
    )


def test_split_offer_keeps_search_params_out_of_card_input() -> None:
    offer = make_offer(
        (
            Param("Цвет", "черный"),
            Param("Продавец", "М.Видео"),
            Param("Потратить бонусы", "Да"),
            Param("Цвет_search", "черный"),
            Param("Объем встроенной памяти_search", "256", "ГБ"),
        )
    )

    split = split_offer(offer)

    assert [p.name for p in split.card.seller_params] == ["Цвет"]
    assert all(not p.name.endswith("_search") for p in split.card.seller_params)
    assert split.card.seller == "М.Видео"
    gold = {g.attribute: (g.value, g.unit) for g in split.gold}
    assert gold["Цвет"] == ("черный", None)
    assert gold["Объем встроенной памяти"] == ("256", "ГБ")
    assert gold[BRAND] == ("Samsung", None)
    assert gold[MODEL] == ("Galaxy S24", None)


def test_split_offer_skips_empty_and_duplicate_gold() -> None:
    offer = make_offer(
        (
            Param("Цвет_search", "черный"),
            Param("Цвет_search", "белый"),
            Param("Количество в комплекте_search", None, "шт"),
        )
    )

    gold = {g.attribute: g.value for g in split_offer(offer).gold}

    assert gold["Цвет"] == "черный"
    assert "Количество в комплекте" not in gold


def test_spec_block_detected_by_header_or_bullet_lines() -> None:
    assert has_spec_block("Чашка.\n\nХарактеристики:\n• Объем: 240 мл")
    assert has_spec_block("• Цвет: розовый\n• Тип: брелок\n- Материал: кожа")
    assert not has_spec_block("• Цвет: розовый\n• Тип: брелок")
    assert not has_spec_block("Удобный чайник для дома")
    assert not has_spec_block(None)


def test_category_paths_follow_parents_and_survive_cycles() -> None:
    categories = [
        Category(1, None, "Электроника"),
        Category(2, 1, "Телефоны"),
        Category(3, 2, "Смартфоны"),
        Category(4, 5, "Петля"),
        Category(5, 4, "Кольцо"),
    ]

    paths = category_paths(categories)

    assert paths[3] == "Электроника / Телефоны / Смартфоны"
    assert paths[4] == "Кольцо / Петля"
