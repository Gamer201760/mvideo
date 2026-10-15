from app.domain.card_text import SellerParam, build_card_text
from app.domain.extractors import extract_candidates
from app.domain.scoring import pick_values
from app.usecase.lexicon_builder import TrainValue, build_lexicon

PHONE = 761


def lexicon_rows() -> list[TrainValue]:
    rows = []
    for _ in range(3):
        rows += [
            TrainValue(PHONE, "Бренд", "Samsung", None),
            TrainValue(PHONE, "Модель", "Galaxy S26", None),
            TrainValue(PHONE, "Цвет", "черный", None),
            TrainValue(PHONE, "Цвет", "фиолетовый", None),
            TrainValue(PHONE, "Встроенная память (ROM)", "256 ГБ", None),
            TrainValue(PHONE, "Оперативная память (RAM)", "12 ГБ", None),
            TrainValue(PHONE, "Емкость аккумулятора", "5000", "мАч"),
            TrainValue(PHONE, "Диагональ", "6.7", '"'),
        ]
    return rows


def test_candidates_carry_quotes_and_pick_expected_values() -> None:
    lexicon = build_lexicon(lexicon_rows())
    card = build_card_text(
        "Смартфон Samsung Galaxy S26 12/256GB Black",
        "Экран 6,7 дюйма, аккумулятор 5000 мА*ч.",
        (SellerParam("Вес", "150 - 200 г"),),
    )
    profiles = dict(lexicon.profiles)
    candidates = extract_candidates(card, profiles, lexicon, PHONE)
    for c in candidates:
        assert card.text[c.start:c.end] == c.evidence
    picks = pick_values(candidates, profiles)
    assert picks["Бренд"].candidate.value == "Samsung"
    assert picks["Модель"].candidate.value == "Galaxy S26"
    assert picks["Цвет"].candidate.key == "черный"
    assert picks["Встроенная память (ROM)"].candidate.key == "256"
    assert picks["Оперативная память (RAM)"].candidate.key == "12"
    assert picks["Емкость аккумулятора"].candidate.key == "5000"
    assert picks["Диагональ"].candidate.key == "6.7"


def test_seller_key_value_is_a_candidate_but_ranges_are_not() -> None:
    lexicon = build_lexicon(lexicon_rows())
    card = build_card_text(
        "Смартфон", "", (SellerParam("Цвет", "фиолетовый"), SellerParam("Диагональ экрана", "6.2 - 6.5\""))
    )
    candidates = extract_candidates(card, dict(lexicon.profiles), lexicon, PHONE)
    colors = [c for c in candidates if c.attribute == "Цвет"]
    assert colors and colors[0].source == "seller" and colors[0].key == "фиолетовый"
    assert not [c for c in candidates if c.attribute == "Диагональ"]


def test_no_text_no_candidates() -> None:
    lexicon = build_lexicon(lexicon_rows())
    card = build_card_text("Товар", "Описание без характеристик", ())
    assert extract_candidates(card, dict(lexicon.profiles), lexicon, PHONE) == []


def test_seller_name_feeds_only_the_closest_attribute() -> None:
    rows = lexicon_rows() + [
        TrainValue(PHONE, "Процессор", "Qualcomm Snapdragon 8 Gen 2", None),
        TrainValue(PHONE, "Производитель процессора", "Qualcomm", None),
    ] * 2
    lexicon = build_lexicon(rows)
    card = build_card_text("Смартфон", "", (SellerParam("Производитель процессора", "Qualcomm"),))
    candidates = extract_candidates(card, dict(lexicon.profiles), lexicon, PHONE)
    assert {c.attribute for c in candidates if c.source == "seller"} == {"Производитель процессора"}


def test_open_range_words_mark_seller_value_as_range() -> None:
    lexicon = build_lexicon(lexicon_rows())
    card = build_card_text("Смартфон", "", (SellerParam("Диагональ экрана", '6.6" и более'),))
    found = extract_candidates(card, dict(lexicon.profiles), lexicon, PHONE)
    assert not [c for c in found if c.attribute == "Диагональ"]
