import json
from pathlib import Path

from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.domain.card_text import SellerParam
from app.usecase.catalog_pack import catalog_pack
from app.usecase.stand_ports import StandExample, StandPack

SEED = Path(__file__).resolve().parents[4] / "seeds/demo.json"


def seed_categories() -> tuple[CatalogCandidate, ...]:
    raw = json.loads(SEED.read_text())
    return tuple(
        CatalogCandidate(
            c["category_id"],
            c["path"],
            0,
            tuple(
                CatalogField(
                    f["attribute"], f["kind"], f["unit"], tuple(f["values"]), tuple(f["aliases"])
                )
                for f in c["fields"]
            ),
        )
        for c in raw["categories"]
    )


def stand_pack(categories: list[CatalogCandidate]) -> StandPack:
    raw = json.loads(SEED.read_text())
    examples = [
        StandExample(
            sku_id=e["sku_id"],
            category_id=e["category_id"],
            title=e["title"],
            description=e["description"],
            seller_params=tuple(SellerParam(**p) for p in e["seller_params"]),
        )
        for e in raw["examples"]
    ]
    return catalog_pack(
        categories,
        built_at="2026-10-17T00:00:00+00:00",
        threshold=0.8,
        examples=examples,
    )
