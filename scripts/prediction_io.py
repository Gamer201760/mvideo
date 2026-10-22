import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path

FIELDS = {"id", "title", "description", "category_id", "seller_params"}


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path: Path) -> Iterator[dict[str, object]]:
    with path.open(encoding="utf-8") as stream:
        for line, text in enumerate(stream, 1):
            if not text.strip():
                raise ValueError(f"Input line {line}: empty JSONL record")
            try:
                row = json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError(f"Input line {line}: invalid JSON") from error
            validate(row, line)
            yield row


def validate(row: object, line: int) -> None:
    prefix = f"Input line {line}: "
    if not isinstance(row, dict) or row.keys() - FIELDS:
        raise ValueError(prefix + "expected only id/title/description/category_id/seller_params")
    identity = row.get("id")
    if (
        isinstance(identity, bool)
        or not isinstance(identity, (str, int))
        or not str(identity).strip()
    ):
        raise ValueError(prefix + "id must be a nonempty string or integer")
    if not isinstance(row.get("title"), str) or not row["title"].strip():
        raise ValueError(prefix + "title must be a nonempty string")
    if not isinstance(row.get("description", ""), str):
        raise TypeError(prefix + "description must be a string")
    category = row.get("category_id")
    if category is not None and (isinstance(category, bool) or not isinstance(category, int)):
        raise ValueError(prefix + "category_id must be an integer or null")
    params = row.get("seller_params", [])
    if not isinstance(params, list):
        raise TypeError(prefix + "seller_params must be a list")
    for param in params:
        if not isinstance(param, dict) or param.keys() - {"name", "value", "unit"}:
            raise ValueError(prefix + "invalid seller parameter")
        if not all(
            isinstance(param.get(key), str) and param[key].strip() for key in ("name", "value")
        ):
            raise ValueError(prefix + "seller name/value must be nonempty strings")
        if param["name"].strip().casefold().endswith("_search"):
            raise ValueError(prefix + "catalog gold is not card input")
        if param.get("unit") is not None and not isinstance(param["unit"], str):
            raise ValueError(prefix + "seller unit must be a string or null")


def inspect_input(path: Path) -> tuple[int, str]:
    identities: set[str] = set()
    for row in rows(path):
        identity = str(row["id"])
        if identity in identities:
            raise ValueError("Input contains duplicate IDs")
        identities.add(identity)
    if not identities:
        raise ValueError("Input contains no cards")
    return len(identities), fingerprint(path)


def atomic_manifest(path: Path, manifest: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    created = False
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            created = True
            json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if created:
            temporary.unlink(missing_ok=True)
