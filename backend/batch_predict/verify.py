import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.domain.card_text import SellerParam, build_card_text
from batch_predict.runner import chunks
from batch_predict.writer import digest, save_json


def verify(data: Path, output: Path) -> dict[str, Any]:
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["status"] != "completed":
        raise ValueError("Prediction run is incomplete")
    for name, source in manifest["sources"].items():
        if digest(data / name) != source["sha256"]:
            raise ValueError(f"Source checksum differs: {name}")
    if digest(output / manifest["catalog"]["file"]) != manifest["catalog"]["sha256"]:
        raise ValueError("Catalog checksum differs")
    inputs = (row for batch in chunks(data / "cards.parquet", None) for row in batch)
    counts: Counter[str] = Counter()
    identities, records = hashlib.sha256(), hashlib.sha256()
    checked_values = 0
    for shard in manifest["shards"]:
        path = output / shard["file"]
        if path.name != shard["file"] or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Invalid shard path or size")
        if digest(path) != shard["sha256"]:
            raise ValueError(f"Shard checksum differs: {path.name}")
        raw_hash = hashlib.sha256()
        shard_rows = 0
        with gzip.open(path, "rb") as stream:
            for line in stream:
                raw_hash.update(line)
                records.update(line)
                row = json.loads(line)
                original = next(inputs, None)
                if original is None or row["id"] != original["sku_id"]:
                    raise ValueError("Output ID order differs from input")
                if row["input_category_id"] != original["category_id"] or row["engine"] != "rules":
                    raise ValueError("Input category or engine differs")
                identities.update(f"{row['id']}\n".encode())
                counts["rows"] += 1
                counts[row["status"]] += 1
                counts["null_input_category"] += int(original["category_id"] is None)
                result = row.get("result", {})
                values = result.get("values", [])
                counts["values"] += len(values)
                counts["missing"] += len(result.get("missing", []))
                counts["rejections"] += len(result.get("rejections", []))
                counts["zero_answers"] += int(not values)
                if result:
                    text = build_card_text(
                        original["title"],
                        original["description"],
                        tuple(SellerParam(**param) for param in original["seller_params"] or []),
                    ).text
                    if result["text"] != text:
                        raise ValueError("Output text differs from production card text")
                for value in values:
                    if (
                        not value["quote"]
                        or result["text"][value["start"] : value["end"]] != value["quote"]
                    ):
                        raise ValueError("Output quote span differs from source text")
                    if value["start"] < 0 or value["end"] <= value["start"]:
                        raise ValueError("Output quote span is invalid")
                    checked_values += 1
                    counts[f"value_{value['status']}"] += 1
                shard_rows += 1
        if shard_rows != shard["rows"] or raw_hash.hexdigest() != shard["uncompressed_sha256"]:
            raise ValueError("Uncompressed shard row count or checksum differs")
    if next(inputs, None) is not None:
        raise ValueError("Some input rows are absent from predictions")
    if dict(counts) != manifest["counts"] or counts["rows"] != manifest["expected_rows"]:
        raise ValueError("Coverage counts differ from manifest")
    if (
        identities.hexdigest() != manifest["input_id_stream_sha256"]
        or identities.hexdigest() != manifest["id_stream_sha256"]
    ):
        raise ValueError("ID stream checksum differs")
    return {
        "status": "verified",
        "rows": counts["rows"],
        "checked_values": checked_values,
        "shards": len(manifest["shards"]),
        "id_stream_sha256": identities.hexdigest(),
        "records_sha256": records.hexdigest(),
        "input_sha256": manifest["sources"]["cards.parquet"]["sha256"],
        "counts": dict(counts),
        "verification_code_sha256": digest(Path(__file__)),
        "checks": [
            "Every input ID and category in original order",
            "All source and shard checksums",
            "Every output text equals production-cleaned original input",
            "Every value has an exact nonempty source span",
            "Counts include zero-answer, no-schema, unclassified and error rows",
        ],
        "scope": "Integrity and complete execution coverage, not independent correctness or calibration",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args()
    path = args.output / "verification.json"
    if args.write_receipt and path.exists():
        raise FileExistsError("Verification receipt already exists")
    report = verify(args.data, args.output)
    if args.write_receipt:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        manifest_path = args.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["verification"] = {"file": path.name, "sha256": digest(path)}
        save_json(manifest_path, manifest)
    print(json.dumps(report["counts"], indent=2))


if __name__ == "__main__":
    main()
