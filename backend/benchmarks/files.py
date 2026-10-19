import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

type Row = dict[str, Any]

ROOT = Path(__file__).resolve().parents[2]
SOURCE_NAMES = (
    "cards.parquet",
    "gold.parquet",
    "splits.parquet",
    "categories.parquet",
    "required_attributes.parquet",
)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def text_digest(text: str) -> str:
    return hashlib.sha256(" ".join(text.casefold().split()).encode()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def write_lines(path: Path, rows: Iterable[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_lines(path: Path) -> list[Row]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def implementation() -> dict[str, str]:
    paths = sorted((ROOT / "backend/src/app").rglob("*.py"))
    paths += sorted((ROOT / "backend/benchmarks").glob("*.py"))
    return {str(path.relative_to(ROOT)): digest(path) for path in paths}


def identity(seed: int, value: object) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()
