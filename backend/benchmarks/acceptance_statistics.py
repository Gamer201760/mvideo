import math
from collections.abc import Sequence

from app.domain.acceptance import AcceptancePolicy
from app.domain.evidence_risk import AttributeRisk
from benchmarks.files import Row


def binomial_tail(successes: int, total: int, probability: float) -> float:
    if probability <= 0:
        return float(successes == 0)
    if probability >= 1:
        return 1.0
    logs = [
        math.lgamma(total + 1)
        - math.lgamma(k + 1)
        - math.lgamma(total - k + 1)
        + k * math.log(probability)
        + (total - k) * math.log1p(-probability)
        for k in range(successes, total + 1)
    ]
    peak = max(logs)
    return min(1.0, math.exp(peak) * sum(math.exp(value - peak) for value in logs))


def lower_bound(successes: int, total: int, alpha: float = 0.05) -> float | None:
    if not 0 <= successes <= total or not 0 < alpha < 1:
        raise ValueError("Invalid binomial counts or alpha")
    if not total:
        return None
    if not successes:
        return 0.0
    left, right = 0.0, 1.0
    for _ in range(80):
        middle = (left + right) / 2
        if binomial_tail(successes, total, middle) < alpha:
            left = middle
        else:
            right = middle
    return (left + right) / 2


def agreed(left: object, right: object) -> bool:
    return left is True and right is True


def validate_reviews(records: list[Row], reviews: Sequence[list[Row]]) -> None:
    expected = {row["card_id"]: {a["answer_id"] for a in row["answers"]} for row in records}
    if len(expected) != len(records) or len(reviews) != 2:
        raise ValueError("Expected unique cards and two independent reviews")
    for rows in reviews:
        found = {row["card_id"]: row for row in rows}
        if len(found) != len(rows) or set(found) != set(expected):
            raise ValueError("Review cards missing, duplicated or out of selection")
        for card_id, row in found.items():
            if row.get("full_input_reviewed") is not True:
                raise ValueError("Review must cover the full card")
            if (
                "category_correct" not in row
                or row["category_correct"] is not None
                and type(row["category_correct"]) is not bool
            ):
                raise ValueError("Invalid category judgement")
            answers = row["answers"]
            if len({a["answer_id"] for a in answers}) != len(answers):
                raise ValueError("Duplicate reviewed answer")
            if {a["answer_id"] for a in answers} != expected[card_id]:
                raise ValueError("Review answer set differs")
            for answer in answers:
                if "correct" not in answer or (
                    answer["correct"] is not None and type(answer["correct"]) is not bool
                ):
                    raise ValueError("Invalid answer judgement")
                if not isinstance(answer.get("reason"), str) or not answer["reason"].strip():
                    raise ValueError("Missing answer rationale")


def evaluate(records: list[Row], reviews: Sequence[list[Row]], threshold: float) -> Row:
    validate_reviews(records, reviews)
    indexed = [{row["card_id"]: row for row in rows} for rows in reviews]
    policy = AcceptancePolicy(threshold)
    nonempty = confirmed_cards = accepted = confirmed_fields = proposed = disagreements = (
        unknown
    ) = 0
    category_disagreements = category_unknowns = 0
    for row in records:
        judges = [lookup[row["card_id"]] for lookup in indexed]
        judgements = [{a["answer_id"]: a["correct"] for a in judge["answers"]} for judge in judges]
        category_ok = agreed(judges[0]["category_correct"], judges[1]["category_correct"])
        fields = []
        proposed += row.get("supported_count", len(row["answers"]))
        for answer in row["answers"]:
            risk = AttributeRisk(**answer["risk"])
            if not policy.accepts(risk, row["category_id"]):
                continue
            accepted += 1
            opinions = [judge[answer["answer_id"]] for judge in judgements]
            known = category_ok and agreed(*opinions)
            fields.append(known)
            confirmed_fields += known
            disagreements += opinions[0] != opinions[1]
            unknown += any(opinion is None for opinion in opinions)
        if fields:
            nonempty += 1
            confirmed_cards += all(fields)
            category_disagreements += judges[0]["category_correct"] != judges[1]["category_correct"]
            category_unknowns += any(judge["category_correct"] is None for judge in judges)
    lower = lower_bound(confirmed_cards, nonempty)
    return {
        "threshold": threshold,
        "input_cards": len(records),
        "nonempty_accepted_cards": nonempty,
        "confirmed_cards": confirmed_cards,
        "unconfirmed_cards": nonempty - confirmed_cards,
        "card_confirmation_rate": confirmed_cards / nonempty if nonempty else None,
        "one_sided_exact95_card_lower": lower,
        "accepted_fields": accepted,
        "confirmed_fields": confirmed_fields,
        "field_confirmation_rate": confirmed_fields / accepted if accepted else None,
        "field_acceptance_coverage": accepted / proposed if proposed else None,
        "card_acceptance_coverage": nonempty / len(records) if records else None,
        "answer_disagreements": disagreements,
        "answer_unknowns": unknown,
        "accepted_card_category_disagreements": category_disagreements,
        "accepted_card_category_unknowns": category_unknowns,
        "gate": "passed_agent_reference"
        if lower is not None and lower >= 0.95
        else "failed_agent_reference"
        if confirmed_cards < nonempty
        else "insufficient_evidence",
        "human_verified": False,
    }
