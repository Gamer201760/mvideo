import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass

from app.domain.card_text import match_form
from app.domain.values import LEADING, canonical_key, canonical_text, canonical_unit
from benchmarks.files import Row


@dataclass
class Counts:
    tp: float = 0
    fp: float = 0
    fn: float = 0
    filled: float = 0
    slots: float = 0

    def add(self, other: "Counts", weight: float = 1) -> None:
        for name, value in asdict(other).items():
            setattr(self, name, getattr(self, name) + weight * value)

    def metrics(self) -> Row:
        precision = self.tp / (self.tp + self.fp) if self.tp + self.fp else 0
        recall = self.tp / (self.tp + self.fn) if self.tp + self.fn else 0
        f1 = 2 * self.tp / (2 * self.tp + self.fp + self.fn) if self.tp + self.fp + self.fn else 0
        return {
            **asdict(self),
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "coverage": self.filled / self.slots if self.slots else 0,
        }


def key(value: str, unit: str | None, profile: Row, attribute: str, raw: bool = False) -> str:
    if raw:
        return f"{value.strip()} {unit or ''}".strip()
    if profile.get("kind") == "numeric":
        leading = LEADING.match(match_form(value))
        if leading and (not leading.group(2).strip() or canonical_unit(leading.group(2).strip())):
            return canonical_key(value, unit, True)
        return match_form(f"{value} {unit or ''}".strip())
    display = f"{value} {unit or ''}".strip()
    if "цвет" in attribute.casefold():
        return canonical_text(display)
    return " ".join(match_form(display).split()).strip()


def evaluate(
    sample: Row, prediction: Row, profiles: dict[str, Row], raw: bool = False
) -> tuple[Counts, dict[str, Counts], int]:
    expected: dict[str, set[str]] = defaultdict(set)
    for gold in sample["gold"]:
        attribute = gold["attribute"]
        expected[attribute].add(
            key(gold["value"], gold["unit"], profiles.get(attribute, {}), attribute, raw)
        )
    predicted: dict[str, set[str]] = defaultdict(set)
    result = prediction.get("result", {}).get("extraction", {})
    for answer in [*result.get("items", []), *result.get("extra_fields", [])]:
        if answer["status"] != "supported":
            continue
        attribute = answer["attribute"]
        value = (
            answer["normalized_value"]
            if answer.get("normalized_value") is not None
            else answer["value"]
        )
        unit = (
            answer["normalized_unit"]
            if answer.get("normalized_unit") is not None
            else answer["unit"]
        )
        predicted[attribute].add(key(value, unit, profiles.get(attribute, {}), attribute, raw))
    total = Counts()
    attributes = {}
    for attribute, alternatives in expected.items():
        found = predicted.get(attribute, set())
        correct = bool(alternatives & found)
        counts = Counts(
            tp=int(correct),
            fp=len(found - alternatives),
            fn=int(not correct),
            filled=int(bool(found)),
            slots=1,
        )
        total.add(counts)
        attributes[attribute] = counts
    unscored = sum(
        len(values) for attribute, values in predicted.items() if attribute not in expected
    )
    return total, attributes, unscored


def quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ranked = sorted(values)
    index = (len(ranked) - 1) * probability
    low = math.floor(index)
    high = math.ceil(index)
    return ranked[low] + (ranked[high] - ranked[low]) * (index - low)


def paired_bootstrap(rows: list[Row], seed: int, repeats: int = 1000) -> Row:
    rng = random.Random(seed)
    strata: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        strata[row["stratum"]].append(row)
    changes = []
    for _ in range(repeats):
        counts = {mode: Counts() for mode in ("rules", "hybrid")}
        for group in strata.values():
            for row in rng.choices(group, k=len(group)):
                for mode, total in counts.items():
                    total.add(Counts(**row[mode]))
        changes.append(counts["hybrid"].metrics()["f1"] - counts["rules"].metrics()["f1"])
    return {
        "repeats": repeats,
        "seed": seed,
        "unit": "card",
        "stratified": True,
        "delta_f1_ci95": [quantile(changes, 0.025), quantile(changes, 0.975)],
        "scope": "Sampling uncertainty on this fixed stratified dataset, not model rerun variability",
    }
