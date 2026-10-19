import asyncio
from dataclasses import asdict
from pathlib import Path

from benchmarks.files import Row, digest, write_json, write_lines
from benchmarks.routing import compare

from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from app.usecase.attribute_flow import AttributeFlow
from app.usecase.attribute_flow_contract import make_request
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_ports import CardInput


def test_comparison_handles_no_cards_eligible_for_routing(tmp_path: Path) -> None:
    async def run() -> None:
        category = CatalogCandidate(
            7,
            "Товары",
            0,
            (
                CatalogField("Цвет", "categorical", "", ("красный",)),
                CatalogField("Вес", "numeric", "г"),
            ),
        )
        schemas = {7: category}
        retrieval = CatalogRetrieval(schemas, ())
        card = CardInput(
            title="Товар",
            description="Цвет: красный\nВес: 500 г",
            seller_params=(),
            category_id=None,
        )
        service = StandAttributeFlow(AttributeFlow(LocalRulesModel()), retrieval)
        request = make_request((await service.prepare(card),))
        write_json(tmp_path / "catalog.json", [asdict(category)])
        write_json(tmp_path / "profiles.json", {})
        write_json(tmp_path / "weights.json", {})
        row: Row = {
            "sku_id": 1,
            "category_id": 7,
            "title": card.title,
            "description": card.description,
            "seller_params": [],
            "gold": [{"attribute": "Цвет", "value": "красный", "unit": ""}],
            "seller": "",
            "train_seller_cards": 0,
            "split": "test",
            "stratum": "test",
            "sampling_weight": 1,
        }
        write_lines(tmp_path / "sample.jsonl", [row])
        write_json(
            tmp_path / "protocol.json",
            {
                "artifacts_sha256": {
                    name: digest(tmp_path / name)
                    for name in ("catalog.json", "profiles.json", "weights.json", "sample.jsonl")
                },
                "withheld_category_ids": [],
                "seed": 1,
                "timeout_s": 2,
            },
        )
        write_json(
            tmp_path / "results/hybrid-1.json",
            {
                "calls": [
                    {
                        "system": request.system,
                        "prompt": request.prompt,
                        "schema": request.schema,
                        "response": {"c": [{"i": 0, "k": 0, "a": [], "r": []}]},
                        "usage": {"model": "saved"},
                        "wall_ms": 10,
                    }
                ]
            },
        )
        protocol: Row = {
            "common": {
                "min_category_score": 0,
                "min_category_margin": 0,
                "min_supported_fields": 100,
            },
            "policies": [{"name": "covered_text", "min_coverage": 1, "require_covered_text": True}],
            "latency": "reconstructed",
        }
        report = await compare(tmp_path, protocol, tmp_path / "report.json")
        result = report["comparisons"]["covered_text"]
        assert result["selected_cards"] == result["saved_calls"] == 0
        assert result["selected_before"] is None
        assert result["selected_after"] is None
        assert report["external_calls_executed"] == 0

    asyncio.run(run())
