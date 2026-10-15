from app.domain.candidate import Candidate
from app.domain.card_text import build_card_text
from app.domain.choice import (
    NOT_STATED,
    build_request,
    candidate_slot,
    dictionary_slot,
    mixed_slot,
    request_fingerprint,
    resolve,
)
from app.domain.choice_text import compact_state, locate_stems
from app.domain.decision import ChoiceAnswer
from app.domain.profile import AttributeProfile, Kind

CARD = build_card_text("Смартфон Samsung Galaxy A55 черный",
                       "Экран 6,6 дюйма. Пылесос не входит. Материал корпуса: пластик", ())
COLOR = AttributeProfile("Цвет", Kind.CATEGORICAL, "", ("цвет",))


def candidate(key: str, start: int, source: str = "dictionary", zone: str = "title") -> Candidate:
    end = start + len(key)
    return Candidate("Цвет", key, key, CARD.span(start, end), start, end, source, zone, 0.0, 0.0,
                     0)


def answer(choice: str, probability: float) -> ChoiceAnswer:
    return ChoiceAnswer(choice, probability, {choice: probability})


def test_candidate_slot_dedupes_keys_and_adds_not_stated() -> None:
    start = CARD.text.index("черный")
    slot = candidate_slot("Цвет", "q0", [candidate("черный", start), candidate("черный", start)],
                          COLOR, top_k=5)

    assert slot is not None
    question = slot.question()
    assert list(question.options) == ["черный", NOT_STATED]
    assert "Цвет" in question.instructions


def test_resolve_keeps_quote_and_probability() -> None:
    start = CARD.text.index("черный")
    slot = candidate_slot("Цвет", "q0", [candidate("черный", start)], COLOR, top_k=5)
    assert slot is not None

    chosen = resolve(CARD, slot, answer("черный", 0.83))

    assert chosen is not None and chosen.candidate is not None
    assert chosen.candidate.evidence == "черный"
    assert chosen.probability == 0.83


def test_not_stated_and_unknown_options_give_no_value() -> None:
    start = CARD.text.index("черный")
    slot = candidate_slot("Цвет", "q0", [candidate("черный", start)], COLOR, top_k=5)
    assert slot is not None

    assert resolve(CARD, slot, answer(NOT_STATED, 0.9)) is None
    assert resolve(CARD, slot, answer("розовый", 0.9)) is None


def test_dictionary_option_needs_text_support() -> None:
    slot = dictionary_slot("Цвет", "q0", {"черный": 5.0, "белый": 3.0}, {}, top_k=5)
    assert slot is not None

    found = resolve(CARD, slot, answer("черный", 0.7))
    missing = resolve(CARD, slot, answer("белый", 0.99))

    assert found is not None and found.candidate is not None
    assert CARD.span(found.candidate.start, found.candidate.end) == "черный"
    assert missing is None


def test_mixed_slot_appends_unseen_dictionary_values() -> None:
    start = CARD.text.index("черный")
    slot = mixed_slot("Цвет", "q0", [candidate("черный", start)], COLOR, 5,
                      {"черный": 9.0, "серый": 2.0}, {}, extra_k=3)

    assert slot is not None
    assert [o.name for o in slot.options] == ["черный", "серый"]


def test_locate_stems_matches_word_forms() -> None:
    span = locate_stems(CARD, "пластиковый")

    assert span is not None
    assert CARD.span(*span).lower().startswith("пласт")
    assert locate_stems(CARD, "металлический") is None


def test_compact_state_keeps_title_and_quote_windows() -> None:
    start = CARD.text.index("пластик")
    state = compact_state(CARD, "Смартфоны", [(start, start + 7)])

    assert state["category"] == "Смартфоны"
    assert state["card"].startswith("Смартфон Samsung")
    assert "пластик" in state["card"]


def test_fingerprint_depends_on_model_and_request() -> None:
    start = CARD.text.index("черный")
    slot = candidate_slot("Цвет", "q0", [candidate("черный", start)], COLOR, top_k=5)
    assert slot is not None
    request = build_request({"card": CARD.text}, [slot])

    assert request_fingerprint(request, "a") == request_fingerprint(request, "a")
    assert request_fingerprint(request, "a") != request_fingerprint(request, "b")
