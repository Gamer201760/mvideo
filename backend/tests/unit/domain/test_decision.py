import pytest

from app.domain.decision import BinaryQuestion, ChoiceQuestion, DecisionRequest, ScoreQuestion
from app.domain.errors import InvalidQuestion


def test_choice_needs_two_options() -> None:
    with pytest.raises(InvalidQuestion):
        ChoiceQuestion("Pick one", {"only": "single option"})


def test_score_needs_two_levels() -> None:
    with pytest.raises(InvalidQuestion):
        ScoreQuestion("Rate it", ["only"])


def test_request_needs_a_question() -> None:
    with pytest.raises(InvalidQuestion):
        DecisionRequest(state="text", questions={})


def test_valid_request_keeps_questions() -> None:
    question = BinaryQuestion("Is it urgent?")

    request = DecisionRequest(state={"body": "now"}, questions={"urgent": question})

    assert request.questions == {"urgent": question}
