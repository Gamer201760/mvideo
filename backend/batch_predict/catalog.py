import json
from pathlib import Path

from app.domain.attribute_flow import CatalogCandidate, CatalogField


def read_catalog(path: Path) -> dict[int, CatalogCandidate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        category["category_id"]: CatalogCandidate(
            category["category_id"],
            category["path"],
            0.0,
            tuple(
                CatalogField(
                    field["attribute"],
                    field["kind"],
                    field["unit"],
                    tuple(field["values"]),
                    tuple(field["aliases"]),
                )
                for field in category["fields"]
            ),
        )
        for category in payload["categories"]
    }
