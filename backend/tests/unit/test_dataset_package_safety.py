import hashlib
import json
from pathlib import Path

import pytest
from tests.unit.dataset_package_cases import execute, package_files


def rejected(package: Path, output: Path) -> None:
    assert execute("verify_dataset.py", "--package", package).returncode == 2
    assert execute("restore_dataset.py", "--package", package, "--output", output).returncode == 2
    assert not output.exists() and not output.with_name(output.name + ".building").exists()


@pytest.mark.parametrize(
    "change", ["part-byte", "raw-hash", "raw-size", "missing", "truncated", "trailing"]
)
def test_corruption_is_rejected_before_any_original_is_published(
    tmp_path: Path, change: str
) -> None:
    _, package = package_files(tmp_path)
    path = package / "manifest.json"
    manifest = json.loads(path.read_text())
    item = manifest["files"][1]
    part = item["parts"][-1]
    target = package / part["name"]
    if change == "part-byte":
        data = bytearray(target.read_bytes())
        data[0] ^= 1
        target.write_bytes(data)
    elif change == "raw-hash":
        item["sha256"] = "0" * 64
    elif change == "raw-size":
        item["size"] = 1
    elif change == "missing":
        target.unlink()
    elif change == "truncated":
        target.write_bytes(target.read_bytes()[:-1])
    else:
        data = target.read_bytes() + b"junk"
        target.write_bytes(data)
        item["compressed_size"] += 4
        part.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    path.write_text(json.dumps(manifest))
    rejected(package, tmp_path / "restored")


def test_duplicate_json_fields_are_rejected(tmp_path: Path) -> None:
    _, package = package_files(tmp_path)
    path = package / "manifest.json"
    content = path.read_text()
    path.write_text(
        content.replace('"compression": "gzip"', '"compression": "gzip", "compression": "gzip"', 1)
    )
    rejected(package, tmp_path / "restored")


@pytest.mark.parametrize("unsafe", ["../escape", "/tmp/escape", "..\\escape", "parts/../../escape"])
@pytest.mark.parametrize("field", ["name", "part"])
def test_manifest_paths_cannot_escape_allowed_exact_names(
    tmp_path: Path, unsafe: str, field: str
) -> None:
    _, package = package_files(tmp_path)
    path = package / "manifest.json"
    manifest = json.loads(path.read_text())
    if field == "name":
        manifest["files"][0]["name"] = unsafe
    else:
        manifest["files"][0]["parts"][0]["name"] = unsafe
    path.write_text(json.dumps(manifest))
    rejected(package, tmp_path / "restored")


@pytest.mark.parametrize("location", ["root", "parts", "manifest", "part"])
def test_package_symlinks_are_rejected(tmp_path: Path, location: str) -> None:
    _, package = package_files(tmp_path)
    if location == "root":
        alias = tmp_path / "alias"
        alias.symlink_to(package, target_is_directory=True)
        package = alias
    elif location == "parts":
        (package / "parts").rename(tmp_path / "relocated")
        (package / "parts").symlink_to(tmp_path / "relocated", target_is_directory=True)
    else:
        target = (
            package / "manifest.json"
            if location == "manifest"
            else next((package / "parts").iterdir())
        )
        target.rename(tmp_path / "outside")
        target.symlink_to(tmp_path / "outside")
    rejected(package, tmp_path / "restored")


@pytest.mark.parametrize("location", ["root", "parts"])
def test_unknown_package_files_are_not_silently_ignored(tmp_path: Path, location: str) -> None:
    _, package = package_files(tmp_path)
    root = package if location == "root" else package / "parts"
    (root / "unknown.partial").write_bytes(b"unexpected")
    rejected(package, tmp_path / "restored")


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "staging"])
def test_restore_refuses_existing_or_incomplete_destinations(tmp_path: Path, kind: str) -> None:
    _, package = package_files(tmp_path)
    output = tmp_path / "restore"
    existing = output.with_name(output.name + ".building") if kind == "staging" else output
    if kind in {"directory", "staging"}:
        existing.mkdir()
        sentinel = existing / "keep"
        sentinel.write_bytes(b"original")
    elif kind == "symlink":
        sentinel = tmp_path / "keep"
        sentinel.write_bytes(b"original")
        existing.symlink_to(sentinel)
    else:
        sentinel = existing
        sentinel.write_bytes(b"original")
    assert execute("restore_dataset.py", "--package", package, "--output", output).returncode == 2
    assert sentinel.read_bytes() == b"original"


@pytest.mark.parametrize(
    "change", ["duplicate-file", "duplicate-part", "unknown-field", "boolean-size"]
)
def test_malformed_manifest_is_rejected(tmp_path: Path, change: str) -> None:
    _, package = package_files(tmp_path)
    path = package / "manifest.json"
    manifest = json.loads(path.read_text())
    if change == "duplicate-file":
        manifest["files"][1] = manifest["files"][0]
    elif change == "duplicate-part":
        manifest["files"][0]["parts"][1] = manifest["files"][0]["parts"][0]
    elif change == "unknown-field":
        manifest["external_url"] = "https://example.invalid"
    else:
        manifest["files"][0]["size"] = True
    path.write_text(json.dumps(manifest))
    rejected(package, tmp_path / "restored")
