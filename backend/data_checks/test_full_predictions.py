import argparse
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from batch_predict.runner import execute
from batch_predict.verify import main as verify_main
from batch_predict.verify import verify

from app.domain.attribute_flow import CatalogCandidate, CatalogField


def test_full_parquet_execution_keeps_every_row_and_verifiable_shards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    rows = [
        {
            "sku_id": 10,
            "category_id": None,
            "title": "Лампы X",
            "description": "Мощность: 100 Вт",
            "seller_params": [],
        },
        {
            "sku_id": 11,
            "category_id": 1,
            "title": "Лампы Y",
            "description": "Нет сведений",
            "seller_params": [],
        },
        {
            "sku_id": 12,
            "category_id": 999,
            "title": "Категория вне схемы",
            "description": "Текст",
            "seller_params": [],
        },
        {
            "sku_id": 13,
            "category_id": None,
            "title": None,
            "description": None,
            "seller_params": [],
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), data / "cards.parquet")
    for name in ["categories", "required_attributes", "splits", "gold"]:
        pq.write_table(pa.table({"row": [1]}), data / f"{name}.parquet")
    schema = CatalogCandidate(
        1, "Освещение / Лампы", 0, (CatalogField("Мощность", "numeric", "Вт"),)
    )
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"categories": [asdict(schema)], "profile_cards": 0}))
    output = tmp_path / "predictions"
    args = argparse.Namespace(data=data, output=output, catalog=catalog, workers=1, limit=None)
    manifest = execute(args)
    assert manifest["status"] == "completed"
    assert manifest["expected_rows"] == manifest["counts"]["rows"] == 4
    assert manifest["counts"]["null_input_category"] == 2
    assert manifest["counts"]["no_schema"] == manifest["counts"]["empty_input"] == 1
    actual: list[dict[str, Any]] = []
    for shard in manifest["shards"]:
        path = output / shard["file"]
        assert path.stat().st_size <= 32 * 1024 * 1024
        assert hashlib.sha256(path.read_bytes()).hexdigest() == shard["sha256"]
        raw = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(raw).hexdigest() == shard["uncompressed_sha256"]
        actual.extend(json.loads(line) for line in raw.splitlines())
    assert [row["id"] for row in actual] == [10, 11, 12, 13]
    assert actual[0]["category_source"] == "retrieved"
    assert actual[0]["result"]["category_id"] == 1
    assert actual[1]["status"] == "ok" and actual[1]["result"]["values"] == []
    assert manifest["id_stream_sha256"] == manifest["input_id_stream_sha256"]
    receipt = verify(data, output)
    assert receipt["rows"] == 4 and receipt["checked_values"] == 1
    argv = ["verify", "--data", str(data), "--output", str(output)]
    monkeypatch.setattr("sys.argv", argv)
    verify_main()
    receipt_path = output / "verification.json"
    assert not receipt_path.exists()
    monkeypatch.setattr("sys.argv", [*argv, "--write-receipt"])
    verify_main()
    receipt_bytes = receipt_path.read_bytes()
    monkeypatch.setattr("sys.argv", argv)
    verify_main()
    assert receipt_path.read_bytes() == receipt_bytes
    monkeypatch.setattr("sys.argv", [*argv, "--write-receipt"])
    with pytest.raises(FileExistsError, match="receipt already exists"):
        verify_main()
    with pytest.raises(FileExistsError):
        execute(args)
    shard_path = output / manifest["shards"][0]["file"]
    shard_path.write_bytes(shard_path.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        verify(data, output)
