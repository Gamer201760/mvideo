from app.domain.page_text import clean_page, find_quote

PAGE = (
    "<html><head><title>Магазин</title><style>.a{color:red}</style></head><body>"
    "<nav><a href='/'>Каталог</a> <a href='/cart'>Корзина</a></nav>"
    "<h1 class=\"title\">Утюг Philips&nbsp;GC1740</h1>"
    "<script>var price = 'Утюг Bosch';</script>"
    "<p>Мощность&nbsp;2000 Вт,\n   цвет   синий.</p>"
    "<aside><h2>Похожие товары</h2><p>Утюг Tefal FV1711</p></aside>"
    "<footer>© 2026 Все права защищены</footer></body></html>"
)


def test_html_page_keeps_product_text_and_drops_scripts_and_chrome() -> None:
    page = clean_page(PAGE)

    assert page.text == "Утюг Philips GC1740\nМощность 2000 Вт, цвет синий."


def test_quote_offsets_point_into_the_original_html() -> None:
    page = clean_page(PAGE)

    start, end = page.source_span(*_span(page.text, "Philips GC1740"))
    assert PAGE[start:end] == "Philips&nbsp;GC1740"
    start, end = page.source_span(*_span(page.text, "цвет синий"))
    assert PAGE[start:end] == "цвет   синий"


def test_plain_text_drops_repeated_lines_and_noise_tail() -> None:
    raw = ("Войти\nКорзина\nСтиральная машина LG F2J3\nКорзина\nЗагрузка 7 кг\n"
           + "Описание модели. " * 20 + "\nПохожие товары\nСтиральная машина Haier HW60")

    page = clean_page(raw)

    assert page.text.startswith("Стиральная машина LG F2J3\nЗагрузка 7 кг")
    assert "Haier" not in page.text
    assert "Корзина" not in page.text


def test_find_quote_ignores_case_and_spacing() -> None:
    text = "Смартфон Samsung  Galaxy A55, черный"

    assert find_quote(text, "samsung galaxy a55") == (9, 28)
    assert find_quote(text, "Galaxy A56") is None


def _span(text: str, fragment: str) -> tuple[int, int]:
    start = text.index(fragment)
    return start, start + len(fragment)


def test_header_and_form_keep_the_product_and_repeated_values_survive() -> None:
    raw = ("<form><article><header><h1>Смартфон Xiaomi 14</h1></header>"
           "<table><tr><td>Wi-Fi</td><td>Есть</td></tr>"
           "<tr><td>NFC</td><td>Есть</td></tr></table></article></form>")

    page = clean_page(raw)

    assert page.text.startswith("Смартфон Xiaomi 14")
    assert page.text.count("Есть") == 2


def test_sentence_starting_like_a_noise_heading_does_not_cut_the_text() -> None:
    raw = ("Чайник Bosch TWK3A011\n" + "Описание модели. " * 15
           + "\nРекомендуем хранить в сухом месте\nМощность: 2400 Вт\nОтзывы (12)\nОтличный чайник")

    page = clean_page(raw)

    assert "Мощность: 2400 Вт" in page.text
    assert "Отличный чайник" not in page.text
