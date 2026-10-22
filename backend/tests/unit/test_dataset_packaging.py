import ast
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from tests.unit.dataset_package_cases import NAMES, SCRIPTS, execute, package_files, source_files


def test_parts_are_deterministic_and_restore_exact_opaque_original_bytes(tmp_path: Path) -> None:
    source, package = package_files(tmp_path / "first")
    _, second = package_files(tmp_path / "second")
    assert (package / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    manifest = json.loads((package / "manifest.json").read_text())
    assert str(tmp_path) not in json.dumps(manifest)
    assert [item["name"] for item in manifest["files"]] == list(NAMES)
    for item in manifest["files"]:
        assert item["size"] == (source / item["name"]).stat().st_size
        assert item["sha256"] == hashlib.sha256((source / item["name"]).read_bytes()).hexdigest()
        assert len(item["parts"]) > 1
        for part in item["parts"]:
            data = (package / part["name"]).read_bytes()
            assert data == (second / part["name"]).read_bytes()
            assert len(data) == part["size"] <= 1024
            assert hashlib.sha256(data).hexdigest() == part["sha256"]
    output = tmp_path / "restored"
    result = execute("restore_dataset.py", "--package", package, "--output", output)
    assert result.returncode == 0, result.stderr
    assert {path.name for path in output.iterdir()} == set(NAMES)
    assert all((output / name).read_bytes() == (source / name).read_bytes() for name in NAMES)
    assert not output.with_name(output.name + ".building").exists()
    assert execute("verify_dataset.py", "--package", package).returncode == 0


def test_default_package_location_survives_standalone_repository_copy(tmp_path: Path) -> None:
    source, package = package_files(tmp_path / "fixture")
    standalone = tmp_path / "standalone"
    (standalone / "scripts").mkdir(parents=True)
    for name in (
        "restore_dataset.py",
        "dataset_manifest.py",
        "dataset_package_io.py",
        "dataset_verification.py",
    ):
        shutil.copy2(SCRIPTS / name, standalone / "scripts" / name)
    shutil.copytree(package, standalone / "artifacts/source")
    output = standalone / "data/raw"
    result = subprocess.run(
        [sys.executable, str(standalone / "scripts/restore_dataset.py"), "--output", str(output)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert all((output / name).read_bytes() == (source / name).read_bytes() for name in NAMES)


def test_builder_cli_emits_only_expected_files_and_refuses_overwrite(tmp_path: Path) -> None:
    source = source_files(tmp_path)
    package = tmp_path / "bundle"
    arguments = ("--source", source, "--output", package, "--part-mib", "1")
    result = execute("package_dataset.py", *arguments)
    assert result.returncode == 0, result.stderr
    before = (package / "manifest.json").read_bytes()
    assert execute("package_dataset.py", *arguments).returncode == 2
    assert (package / "manifest.json").read_bytes() == before
    assert execute("verify_dataset.py", "--package", package).returncode == 0


def test_scripts_use_python310_syntax_and_only_standard_library(tmp_path: Path) -> None:
    names = (
        "dataset_manifest.py",
        "dataset_package_io.py",
        "dataset_verification.py",
        "package_dataset.py",
        "restore_dataset.py",
        "verify_dataset.py",
    )
    local = {Path(name).stem for name in names}
    for name in names:
        tree = ast.parse((SCRIPTS / name).read_text(), feature_version=(3, 10))
        for node in ast.walk(tree):
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            )
            assert all(
                module.split(".")[0] in sys.stdlib_module_names | local for module in modules
            )
