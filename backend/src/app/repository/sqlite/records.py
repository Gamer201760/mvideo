import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.domain.review import Alias, ReviewItem, ReviewStatus


def encode(record: ReviewItem | Alias | CatalogCandidate) -> str:
    return json.dumps(asdict(record), default=str, ensure_ascii=False, separators=(",", ":"))


def review(payload: str) -> ReviewItem:
    row = json.loads(payload)
    row["status"] = ReviewStatus(row["status"])
    row["created_at"] = datetime.fromisoformat(row["created_at"])
    row["resolved_at"] = datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None
    return ReviewItem(**row)


def alias(payload: str) -> Alias:
    row = json.loads(payload)
    row["created_at"] = datetime.fromisoformat(row["created_at"])
    return Alias(**row)


def category(payload: str) -> CatalogCandidate:
    row: dict[str, Any] = json.loads(payload)
    row["fields"] = tuple(
        CatalogField(f["attribute"], f["kind"], f["unit"], tuple(f["values"]), tuple(f["aliases"]))
        for f in row["fields"]
    )
    row["example_values"] = tuple(tuple(v) for v in row["example_values"])
    return CatalogCandidate(**row)
