import math

import pytest

from app.adapter.decision.lexical import LexicalDecisionModel
from app.domain.decision import (
    BinaryAnswer,
    BinaryQuestion,
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionRequest,
    ScoreAnswer,
    ScoreQuestion,
)

DEPARTMENT = ChoiceQuestion(
    "Which department should handle this?",
    {"billing": "invoices, payments, refunds", "technical": "bugs, outages, errors"},
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def decide(request: DecisionRequest) -> dict[str, object]:
    return dict((await LexicalDecisionModel().decide(request)).answers)


@pytest.mark.anyio
async def test_choice_prefers_option_sharing_words_with_state() -> None:
    answers = await decide(
        DecisionRequest(
            state={"subject": "Refunds", "body": {"text": "I need my payment refunded"}},
            questions={"department": DEPARTMENT},
        )
    )

    answer = answers["department"]
    assert isinstance(answer, ChoiceAnswer)
    assert answer.choice == "billing"
    assert answer.confidence == answer.probabilities["billing"]
    assert answer.probabilities["billing"] > answer.probabilities["technical"]
    assert math.isclose(sum(answer.probabilities.values()), 1)


@pytest.mark.anyio
async def test_matches_russian_word_forms() -> None:
    question = ChoiceQuestion(
        "Какой отдел?", {"оплата": "счета, платежи, возвраты", "поддержка": "ошибки, сбои"}
    )

    answers = await decide(
        DecisionRequest(state="Платёж списали дважды, верните платежа", questions={"q": question})
    )

    answer = answers["q"]
    assert isinstance(answer, ChoiceAnswer)
    assert answer.choice == "оплата"


@pytest.mark.anyio
async def test_score_is_expected_level() -> None:
    question = ScoreQuestion("How urgent?", ["routine request", "blocking outage now"])

    answers = await decide(
        DecisionRequest(state="Total outage, blocking everyone now", questions={"u": question})
    )

    answer = answers["u"]
    assert isinstance(answer, ScoreAnswer)
    assert math.isclose(sum(answer.probabilities), 1)
    assert math.isclose(answer.score, answer.probabilities[1])
    assert answer.score > 0.5
    assert answer.confidence == max(answer.probabilities)


@pytest.mark.anyio
async def test_binary_rises_with_matching_words() -> None:
    question = BinaryQuestion("Is this ticket about billing?")

    hit = await decide(DecisionRequest(state="Billing is wrong", questions={"b": question}))
    miss = await decide(DecisionRequest(state="Login page crashes", questions={"b": question}))

    assert isinstance(hit["b"], BinaryAnswer)
    assert isinstance(miss["b"], BinaryAnswer)
    assert hit["b"].probability > 0.5 > miss["b"].probability


@pytest.mark.anyio
async def test_is_deterministic() -> None:
    request = DecisionRequest(state="Card payment failed", questions={"department": DEPARTMENT})

    assert await decide(request) == await decide(request)
