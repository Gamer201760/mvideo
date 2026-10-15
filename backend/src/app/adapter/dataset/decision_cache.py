import json
from pathlib import Path
from typing import Any

from app.domain.decision import Answer, BinaryAnswer, ChoiceAnswer, Decision, ScoreAnswer
from app.domain.inference import Usage


def answer_json(answer: Answer) -> dict[str, Any]:
    match answer:
        case ChoiceAnswer(choice, confidence, probabilities):
            return {"type": "choice", "choice": choice, "confidence": confidence,
                    "probabilities": dict(probabilities)}
        case ScoreAnswer(score, confidence, probabilities):
            return {"type": "score", "score": score, "confidence": confidence,
                    "probabilities": list(probabilities)}
        case BinaryAnswer(probability):
            return {"type": "binary", "probability": probability}


def answer_of(raw: dict[str, Any]) -> Answer:
    kind = raw["type"]
    if kind == "choice":
        return ChoiceAnswer(str(raw["choice"]), float(raw["confidence"]),
                            {str(k): float(v) for k, v in raw["probabilities"].items()})
    if kind == "score":
        return ScoreAnswer(float(raw["score"]), float(raw["confidence"]),
                           tuple(float(v) for v in raw["probabilities"]))
    return BinaryAnswer(float(raw["probability"]))


def decision_json(decision: Decision) -> dict[str, Any]:
    u = decision.usage
    return {
        "answers": {k: answer_json(a) for k, a in decision.answers.items()},
        "usage": {"model": u.model, "duration_ms": u.duration_ms, "input_tokens": u.input_tokens,
                  "output_tokens": u.output_tokens, "cost_usd": u.cost_usd},
    }


def decision_of(raw: dict[str, Any]) -> Decision:
    u = raw["usage"]
    usage = Usage(model=str(u["model"]), duration_ms=int(u["duration_ms"]),
                  input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                  cost_usd=u.get("cost_usd"))
    return Decision(answers={k: answer_of(a) for k, a in raw["answers"].items()}, usage=usage)


class FileDecisionCache:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, fingerprint: str) -> Path:
        return self._dir / fingerprint[:2] / f"{fingerprint}.json"

    def get(self, fingerprint: str) -> Decision | None:
        path = self._path(fingerprint)
        if not path.exists():
            return None
        try:
            return decision_of(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, KeyError, TypeError):
            return None

    def put(self, fingerprint: str, decision: Decision) -> None:
        path = self._path(fingerprint)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(decision_json(decision), ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
