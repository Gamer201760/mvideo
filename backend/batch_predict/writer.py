import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def save_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class Shards:
    def __init__(self, output: Path, limit: int = 16 * 1024 * 1024) -> None:
        self.output = output
        self.limit = limit
        self.shards: list[dict[str, Any]] = []
        self.counts: Counter[str] = Counter()
        self.identities = hashlib.sha256()
        self.stream: gzip.GzipFile | None = None
        self.raw_stream: Any = None
        self.path = output
        self.raw_hash = hashlib.sha256()
        self.raw_bytes = 0
        self.rows = 0
        self.first: int | None = None
        self.last: int | None = None

    def add(self, record: dict[str, Any]) -> None:
        data = (
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode()
        if len(data) > self.limit:
            record = {
                "id": record["id"],
                "input_category_id": record["input_category_id"],
                "engine": "rules",
                "status": "error",
                "error": {"code": "record_too_large"},
            }
            data = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        if self.stream is not None and self.raw_bytes + len(data) > self.limit:
            self.close()
        if self.stream is None:
            self.path = self.output / f"predictions-{len(self.shards):05d}.jsonl.gz"
            self.raw_stream = self.path.open("xb")
            self.stream = gzip.GzipFile(
                filename="", fileobj=self.raw_stream, mode="wb", compresslevel=4, mtime=0
            )
            self.raw_hash = hashlib.sha256()
            self.raw_bytes, self.rows, self.first = 0, 0, record["id"]
        self.stream.write(data)
        self.raw_hash.update(data)
        self.raw_bytes += len(data)
        self.rows += 1
        self.last = record["id"]
        self.identities.update(f"{record['id']}\n".encode())
        self.counts["rows"] += 1
        self.counts[record["status"]] += 1
        result = record.get("result", {})
        values = result.get("values", [])
        self.counts["values"] += len(values)
        self.counts["missing"] += len(result.get("missing", []))
        self.counts["rejections"] += len(result.get("rejections", []))
        self.counts["zero_answers"] += int(not values)
        self.counts["null_input_category"] += int(record["input_category_id"] is None)
        for value in values:
            self.counts[f"value_{value['status']}"] += 1

    def close(self) -> None:
        if self.stream is None:
            return
        self.stream.close()
        self.raw_stream.close()
        self.stream = None
        size = self.path.stat().st_size
        if size > 32 * 1024 * 1024:
            raise ValueError("Compressed shard exceeds 32 MiB")
        self.shards.append(
            {
                "file": self.path.name,
                "rows": self.rows,
                "bytes": size,
                "uncompressed_bytes": self.raw_bytes,
                "sha256": digest(self.path),
                "uncompressed_sha256": self.raw_hash.hexdigest(),
                "first_id": self.first,
                "last_id": self.last,
            }
        )

    def checkpoint(self) -> dict[str, Any]:
        return {
            "counts": dict(self.counts),
            "id_stream_sha256": self.identities.hexdigest(),
            "shards": self.shards,
        }
