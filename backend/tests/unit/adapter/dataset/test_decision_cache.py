from pathlib import Path

from app.adapter.dataset.decision_cache import FileDecisionCache
from app.domain.decision import BinaryAnswer, ChoiceAnswer, Decision, ScoreAnswer
from app.domain.inference import Usage


def test_round_trips_decisions(tmp_path: Path) -> None:
    cache = FileDecisionCache(tmp_path)
    decision = Decision(
        answers={
            "q0": ChoiceAnswer("256 ГБ", 0.9, {"256 ГБ": 0.9, "не указано": 0.1}),
            "q1": ScoreAnswer(1.0, 0.6, (0.2, 0.6, 0.2)),
            "q2": BinaryAnswer(0.3),
        },
        usage=Usage("typesafe/jev-1.13", 380, 598, 154, 0.000025),
    )

    assert cache.get("ab12") is None
    cache.put("ab12", decision)

    assert cache.get("ab12") == decision


def test_corrupt_entry_is_a_miss(tmp_path: Path) -> None:
    cache = FileDecisionCache(tmp_path)
    (tmp_path / "zz").mkdir()
    (tmp_path / "zz" / "zz99.json").write_text("{", encoding="utf-8")

    assert cache.get("zz99") is None
