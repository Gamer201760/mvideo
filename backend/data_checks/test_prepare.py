import json
import pickle
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from analysis.grounding import grounding
from analysis.overview import verify_inputs

from app.prepare_data import digest


def raw_files(root: Path) -> Path:
    root.mkdir()
    categories = [{"@id": "1", "#text": "Смартфоны"}]
    offers = [
        {
            "@id": str(sku),
            "@available": "true",
            "vendor": "Example",
            "model": f"A{sku}",
            "name": f"Телефон A{sku}",
            "categoryId": "1",
            "param": [
                {"@name": "Цвет", "#text": "черный"},
                {"@name": "Цвет_search", "#text": "черный"},
            ],
        }
        for sku in range(1, 41)
    ]
    (root / "skus.pkl").write_bytes(
        pickle.dumps(
            {"categories": {"category": categories}, "offers": {"offer": offers}}, protocol=4
        )
    )
    pq.write_table(
        pa.table(
            {
                "sku_id": pa.array([*range(1, 40), 9000], type=pa.uint64()),
                "title": [f"Телефон Example A{sku}" for sku in [*range(1, 40), 9000]],
                "description": ["<p>Цвет: черный</p>"] * 40,
            }
        ),
        root / "sku_desc.parquet",
    )
    pq.write_table(
        pa.table(
            {
                "sku_id": pa.array(list(range(1, 41)), type=pa.uint64()),
                "toValidUTF8(query_text)": ["смартфон черный"] * 40,
            }
        ),
        root / "query_clicks.parquet",
    )
    return root


def command(raw: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.prepare_data", "--raw", str(raw), "--out", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_raw_to_processed_manifest_leakage_and_orphans(tmp_path: Path) -> None:
    raw = raw_files(tmp_path / "raw")
    output = tmp_path / "processed"
    result = command(raw, output)
    assert result.returncode == 0, result.stderr
    manifest = verify_inputs(raw, output)
    cards = pq.read_table(output / "cards.parquet").to_pylist()
    assert len(cards) == 41
    assert next(r for r in cards if r["sku_id"] == 9000)["in_catalog"] is False
    assert next(r for r in cards if r["sku_id"] == 40)["has_text"] is False
    assert all(not p["name"].endswith("_search") for r in cards for p in r["seller_params"] or [])
    assert manifest["outputs"]["gold.parquet"]["rows"] == 120
    assert manifest["model_calls"] == 0
    assert not output.with_name(output.name + ".building").exists()
    evidence = grounding(output, count=10)
    assert evidence["sample_size"] == 10
    assert evidence["literal_overlap"] == 1


def test_source_checksum_change_is_detected(tmp_path: Path) -> None:
    raw = raw_files(tmp_path / "raw")
    output = tmp_path / "processed"
    assert command(raw, output).returncode == 0
    with (raw / "skus.pkl").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_inputs(raw, output)


def test_existing_output_is_not_overwritten_and_missing_input_fails(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep")
    assert command(tmp_path / "missing", output).returncode == 2
    assert marker.read_text() == "keep"
    assert command(tmp_path / "missing", tmp_path / "new").returncode == 2
    assert not (tmp_path / "new").exists()


def test_repeated_builds_have_same_splits_and_required_metadata(tmp_path: Path) -> None:
    raw = raw_files(tmp_path / "raw")
    first, second = tmp_path / "first", tmp_path / "second"
    assert command(raw, first).returncode == 0
    assert command(raw, second).returncode == 0
    for name in ("cards.parquet", "splits.parquet", "gold.parquet", "required_attributes.parquet"):
        assert digest(first / name) == digest(second / name)
    assert json.loads((first / "stats.json").read_text())["skus"]["gold_skus"] == 40
