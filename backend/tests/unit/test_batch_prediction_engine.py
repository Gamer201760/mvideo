import asyncio
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from batch_predict.engine import initialize, predict, predict_batch
from batch_predict.writer import Shards

from app.adapter.llm.local_rules import LocalRulesModel
from app.domain.attribute_flow import CatalogCandidate, CatalogField
from app.domain.card_text import SellerParam
from app.repository.memory.catalog_retrieval import CatalogRetrieval
from app.usecase.attribute_flow import AttributeFlow
from app.usecase.stand_attribute_flow import StandAttributeFlow
from app.usecase.stand_ports import CardInput


def schemas() -> dict[int, CatalogCandidate]:
    return {
        1: CatalogCandidate(
            1,
            "Освещение / Лампы",
            0,
            (
                CatalogField("Мощность", "numeric", "Вт"),
                CatalogField("Вес", "numeric", "кг"),
                CatalogField("Цвет", "categorical", "", ("красный", "синий")),
            ),
        ),
        2: CatalogCandidate(2, "Мебель / Столы", 0, (CatalogField("Ширина", "numeric", "см"),)),
    }


def initialize_catalog(path: Path) -> None:
    path.write_text(json.dumps({"categories": [asdict(schema) for schema in schemas().values()]}))
    initialize(str(path))


@pytest.mark.parametrize("category", [1, None])
@pytest.mark.parametrize(
    "description",
    [
        "Мощность: 100 Вт\nВес: 500 г\nЦвет: красный",
        "Мощность: примерно 100 Вт\nВес: до 2 кг",
        "Мощность: 100 Вт\nМощность: 200 Вт",
        "Упаковка: 3 кг\nВес: 500 г",
    ],
)
def test_offline_engine_matches_real_stand_usecase(
    tmp_path: Path, category: int | None, description: str
) -> None:
    initialize_catalog(tmp_path / "catalog.json")
    seller = [{"name": "Материал", "value": "сталь", "unit": None}]
    row: dict[str, Any] = {
        "sku_id": 42,
        "category_id": category,
        "title": "Лампы X",
        "description": description,
        "seller_params": seller,
    }
    output = predict(row)
    service = StandAttributeFlow(AttributeFlow(LocalRulesModel()), CatalogRetrieval(schemas(), ()))
    actual = asyncio.run(
        service.execute(
            CardInput(
                title=row["title"],
                description=description,
                seller_params=(SellerParam("Материал", "сталь"),),
                category_id=category,
            )
        )
    )
    assert output["status"] == "ok"
    result = output["result"]
    assert result["text"] == actual.text
    assert result["category_id"] == actual.extraction.category_id
    assert result["missing"] == list(actual.missing)
    assert result["rejections"] == [asdict(rejection) for rejection in actual.extraction.rejections]
    answers = (*actual.extraction.items, *actual.extraction.extra_fields)
    assert len(result["values"]) == len(answers)
    for value, answer in zip(result["values"], answers, strict=True):
        assert value["attribute"] == answer.attribute
        assert value["value"] == (
            answer.normalized_value if answer.normalized_value is not None else answer.value
        )
        assert value["unit"] == (
            answer.normalized_unit if answer.normalized_unit is not None else answer.unit
        )
        assert value["quote"] == answer.quote
        assert (value["start"], value["end"]) == (answer.start, answer.end)
        assert value["source"] == answer.source
        assert value["status"] == ("accepted" if answer.attribute in actual.automatic else "review")


def test_no_schema_and_empty_inputs_are_explicit_rows(tmp_path: Path) -> None:
    initialize_catalog(tmp_path / "catalog.json")
    base: dict[str, Any] = {
        "sku_id": 7,
        "category_id": 999,
        "title": "Лампы X",
        "description": "",
        "seller_params": [],
    }
    assert predict(base)["status"] == "no_schema"
    base.update({"sku_id": 8, "category_id": None, "title": None, "description": None})
    result = predict(base)
    assert result["id"] == 8 and result["status"] == "empty_input"
    assert result["result"]["values"] == []


def test_shards_are_bounded_ordered_and_deterministic(tmp_path: Path) -> None:
    rows: list[dict[str, Any]] = [
        {
            "id": index,
            "input_category_id": None,
            "engine": "rules",
            "status": "unclassified",
            "result": {"text": "x" * 30, "values": [], "missing": []},
        }
        for index in range(20)
    ]
    runs = []
    for name in ["first", "second"]:
        folder = tmp_path / name
        folder.mkdir()
        writer = Shards(folder, limit=512)
        for row in rows:
            writer.add(row)
        writer.close()
        assert len(writer.shards) > 1
        recovered: list[dict[str, Any]] = []
        for shard in writer.shards:
            path = folder / shard["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == shard["sha256"]
            with gzip.open(path, "rt") as stream:
                recovered.extend(json.loads(line) for line in stream)
        assert recovered == rows
        assert writer.counts["rows"] == 20
        assert writer.counts["zero_answers"] == 20
        assert (
            writer.identities.hexdigest()
            == hashlib.sha256("".join(f"{index}\n" for index in range(20)).encode()).hexdigest()
        )
        runs.append(writer.shards)
    assert runs[0] == runs[1]


def test_batched_engine_keeps_scalar_results_for_retrieved_supplied_and_empty_inputs(
    tmp_path: Path,
) -> None:
    initialize_catalog(tmp_path / "catalog.json")
    rows: list[dict[str, Any]] = [
        {
            "sku_id": index,
            "category_id": category,
            "title": title,
            "description": "Мощность: 100 Вт\nВес: 500 г",
            "seller_params": [],
        }
        for index, (category, title) in enumerate(
            [(1, "Лампы X"), (None, "Лампы Y"), (999, "Столы"), (None, "")]
        )
    ]
    rows[-1]["description"] = ""
    assert predict_batch(rows) == [predict(row) for row in rows]
