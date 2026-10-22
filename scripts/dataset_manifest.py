import json
import re
from pathlib import Path
from typing import TypedDict, cast

from dataset_package_io import PART_BYTES, SOURCE_NAMES


class DatasetPart(TypedDict):
    name: str
    size: int
    sha256: str


class DatasetFile(TypedDict):
    name: str
    size: int
    sha256: str
    compressed_size: int
    parts: list[DatasetPart]


class DatasetManifest(TypedDict):
    format: str
    compression: str
    part_bytes: int
    files: list[DatasetFile]


def _object(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Invalid dataset manifest fields")
    return cast(dict[str, object], value)


def _integer(value: object, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("Invalid dataset manifest size")
    if maximum is not None and value > maximum:
        raise ValueError("Dataset manifest size exceeds its limit")
    return value


def _hash(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Invalid dataset SHA-256")
    return value


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for name, value in pairs:
        if name in fields:
            raise ValueError("Duplicate dataset manifest field")
        fields[name] = value
    return fields


def load_manifest(package: Path) -> DatasetManifest:
    path = package / "manifest.json"
    if package.is_symlink() or not package.is_dir() or path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe dataset package")
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Dataset manifest is too large")
    document = _object(
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields),
        {"format", "compression", "part_bytes", "files"},
    )
    if document["format"] != "organizer-source-v1" or document["compression"] != "gzip":
        raise ValueError("Unsupported dataset package format")
    limit = _integer(document["part_bytes"], PART_BYTES)
    raw_files = document["files"]
    if not isinstance(raw_files, list) or len(raw_files) != len(SOURCE_NAMES):
        raise ValueError("Dataset package must contain exactly three organizer files")
    files: list[DatasetFile] = []
    for expected, raw_file in zip(SOURCE_NAMES, raw_files):
        item = _object(raw_file, {"name", "size", "sha256", "compressed_size", "parts"})
        if item["name"] != expected:
            raise ValueError("Unknown, duplicate or unsafe dataset filename")
        parts = item["parts"]
        if not isinstance(parts, list) or not 1 <= len(parts) <= 512:
            raise ValueError("Invalid dataset part count")
        records: list[DatasetPart] = []
        for index, raw_part in enumerate(parts):
            part = _object(raw_part, {"name", "size", "sha256"})
            name = f"parts/{expected}.gz.{index:05d}"
            if part["name"] != name:
                raise ValueError("Unknown, duplicate or unsafe dataset part path")
            size = _integer(part["size"], limit)
            if index < len(parts) - 1 and size != limit:
                raise ValueError("Non-final dataset part must have the declared chunk size")
            records.append({"name": name, "size": size, "sha256": _hash(part["sha256"])})
        compressed_size = _integer(item["compressed_size"])
        if compressed_size != sum(part["size"] for part in records):
            raise ValueError("Dataset compressed size does not match its parts")
        files.append(
            {
                "name": expected,
                "size": _integer(item["size"]),
                "sha256": _hash(item["sha256"]),
                "compressed_size": compressed_size,
                "parts": records,
            }
        )
    parts_root = package / "parts"
    if parts_root.is_symlink() or not parts_root.is_dir():
        raise ValueError("Missing or unsafe dataset parts directory")
    if {p.name for p in package.iterdir()} != {"manifest.json", "parts"}:
        raise ValueError("Unexpected file in dataset package")
    expected_parts = {Path(part["name"]).name for item in files for part in item["parts"]}
    if {p.name for p in parts_root.iterdir()} != expected_parts:
        raise ValueError("Missing or unexpected dataset parts")
    for dataset_file in files:
        for dataset_part in dataset_file["parts"]:
            target = package / dataset_part["name"]
            if (
                target.is_symlink()
                or not target.is_file()
                or target.stat().st_size != dataset_part["size"]
            ):
                raise ValueError(f"Missing, unsafe or resized dataset part: {dataset_part['name']}")
    return {
        "format": "organizer-source-v1",
        "compression": "gzip",
        "part_bytes": limit,
        "files": files,
    }
