from collections.abc import Sequence

from app.domain.acceptance import AcceptancePolicy
from app.domain.evidence_risk import AttributeRisk
from benchmarks.files import Row


def reviewed_records(
    records: list[Row], original: list[Row], selected: list[Row], policy: AcceptancePolicy
) -> list[Row]:
    ids = {row["card_id"] for row in records}
    if len(ids) != len(records):
        raise ValueError("Duplicate prediction card")
    for rows in [original, selected]:
        if len(rows) != len(records) or {r["card_id"] for r in rows} != ids:
            raise ValueError("Review packet cards differ from frozen predictions")
    canonical = {row["card_id"]: row for row in original}
    packets = {row["card_id"]: row for row in selected}
    result = []
    for row in records:
        card_id = row["card_id"]
        source = row["answers"]
        original_answers = canonical[card_id]["answers"]
        projected = [{key: value for key, value in a.items() if key != "risk"} for a in source]
        if projected != original_answers:
            raise ValueError("Review answers differ from inference values")
        packet = packets[card_id]
        selected_ids = {a["answer_id"] for a in packet["answers"]}
        if len(selected_ids) != len(packet["answers"]):
            raise ValueError("Duplicate selected answer")
        expected = {
            **canonical[card_id],
            "answers": [a for a in original_answers if a["answer_id"] in selected_ids],
        }
        if packet != expected:
            raise ValueError("Review packet text, category or answer values changed")
        accepted = [
            a for a in source if policy.accepts(AttributeRisk(**a["risk"]), row["category_id"])
        ]
        if {a["attribute"] for a in accepted} != set(row["automatic"]):
            raise ValueError("Recorded automatic fields differ from frozen policy")
        if not {a["answer_id"] for a in accepted} <= selected_ids:
            raise ValueError("Review selection omits accepted answers")
        result.append(
            {
                **row,
                "supported_count": len(source),
                "answers": [a for a in source if a["answer_id"] in selected_ids],
            }
        )
    return result


def bind_reviews(reviews: Sequence[list[Row]], packet_sha256: str) -> None:
    identities: list[str] = []
    for rows in reviews:
        reviewers = {row.get("reviewer") for row in rows}
        if len(reviewers) != 1 or not all(
            isinstance(name, str) and name.strip() for name in reviewers
        ):
            raise ValueError("Expected one identified reviewer per review file")
        if any(row.get("input_sha256") != packet_sha256 for row in rows):
            raise ValueError("Review belongs to another input packet")
        for reviewer in reviewers:
            if not isinstance(reviewer, str):
                raise TypeError("Reviewer identity must be a string")
            identities.append(reviewer)
    if len(identities) != 2 or len(set(identities)) != 2:
        raise ValueError("Expected two distinct reviewers")
