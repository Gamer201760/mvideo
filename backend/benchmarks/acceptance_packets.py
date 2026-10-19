import hashlib
from pathlib import Path

from benchmarks.files import Row, digest, write_json, write_lines


def write_review_packet(output: Path, records: list[Row], packets: list[Row]) -> None:
    indexed = {row["card_id"]: row for row in records}
    selected = []
    for packet in packets:
        automatic = set(indexed[packet["card_id"]]["automatic"])
        controls = [a for a in packet["answers"] if a["attribute"] not in automatic]
        controls.sort(
            key=lambda answer: hashlib.sha256(
                f"acceptance-controls-v1:{answer['answer_id']}".encode()
            ).hexdigest()
        )
        selected_ids = {a["answer_id"] for a in controls[:1]}
        selected_ids.update(
            a["answer_id"] for a in packet["answers"] if a["attribute"] in automatic
        )
        selected.append(
            {**packet, "answers": [a for a in packet["answers"] if a["answer_id"] in selected_ids]}
        )
    write_lines(output / "review-subset.jsonl", selected)
    for i in range(0, len(selected), 10):
        write_lines(output / f"review-chunk-{i // 10:02}.jsonl", selected[i : i + 10])
    write_json(
        output / "review-protocol.json",
        {
            "version": "acceptance-review-v1",
            "predictions_sha256": digest(output / "predictions.jsonl"),
            "original_blind_packet_sha256": digest(output / "blind-review.jsonl"),
            "review_subset_sha256": digest(output / "review-subset.jsonl"),
            "selection": "All fixed-policy accepted answers plus one SHA256(acceptance-controls-v1:answer_id) nonaccepted control per card; no gold or review outcome filtering",
            "blinding": "Full input, predicted category, normalized answer and quote; no score, status, partition, gold or other review",
            "frozen_before_reviews": True,
            "cards": len(packets),
            "reviewed_answers": sum(len(row["answers"]) for row in selected),
            "supported_answers": sum(len(row["answers"]) for row in records),
            "provenance": "Two independent agents, not human gold",
        },
    )
