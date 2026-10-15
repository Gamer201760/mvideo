from app.domain.fusion import (
    BASELINE,
    DECISION,
    KNOWN,
    NEW,
    RANKER,
    TWIN,
    FusionRules,
    Rule,
    RuleBook,
    resolve,
)


def test_ranker_primary_falls_back_to_twin_only_when_enabled() -> None:
    options = {RANKER: None, TWIN: "black"}
    assert resolve(options, Rule(RANKER, False)) is None
    assert resolve(options, Rule(RANKER, True)) == TWIN


def test_decision_answer_wins_and_its_refusal_blocks_the_ranker() -> None:
    assert resolve({DECISION: "red", RANKER: "blue"}, Rule(DECISION, False)) == DECISION
    assert resolve({DECISION: None, RANKER: "blue"}, Rule(DECISION, False)) is None
    assert resolve({RANKER: "blue"}, Rule(DECISION, False)) == RANKER


def test_baseline_primary_ignores_the_ranker() -> None:
    assert resolve({BASELINE: "a55", RANKER: "a5"}, Rule(BASELINE, False)) == BASELINE


def test_rule_book_picks_per_attribute_rule_with_enough_gold() -> None:
    book = RuleBook()
    for _ in range(40):
        book.add("Модель", KNOWN, {BASELINE: "a55", RANKER: "a5"}, "a55")
        book.add("Цвет", KNOWN, {BASELINE: "red", RANKER: "black"}, "black")
    for _ in range(5):
        book.add("Вес", KNOWN, {TWIN: "2"}, "2")
    rules = book.choose(min_gold=30)
    assert rules.rule("Модель", KNOWN).primary == BASELINE
    assert rules.rule("Цвет", KNOWN).primary == RANKER
    assert rules.rule("Вес", KNOWN) == rules.defaults[KNOWN]


def test_rules_round_trip_through_json() -> None:
    rules = FusionRules({KNOWN: Rule(RANKER, True), NEW: Rule(DECISION, False)},
                        {("Модель", KNOWN): Rule(BASELINE, False)})
    restored = FusionRules.from_json(rules.to_json())
    assert restored.rule("Модель", KNOWN) == Rule(BASELINE, False)
    assert restored.rule("Цвет", NEW) == Rule(DECISION, False)
