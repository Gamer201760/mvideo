import json
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / "scripts/export_release.py"


def repository(path: Path) -> Path:
    (path / "scripts").mkdir(parents=True)
    shutil.copy2(SOURCE, path / "scripts/export_release.py")
    (path / "README.md").write_text("Release instructions")
    (path / ".env.example").write_text("GATEWAY_API_KEY=\n")
    (path / ".env").write_text("GATEWAY_API_KEY=fixture-credential-not-real\n")
    for relative in (
        "frontend/src/app.ts",
        "frontend/node_modules/library/index.js",
        "backend/.venv/private.txt",
        "backend/data/raw.txt",
        "reports/technical-checkpoint.md",
        "docs/acceptance-validation.md",
        "reports/benchmark-v1.json",
        "examples/validation/cards.jsonl",
        "artifacts/validation/predictions.jsonl",
    ):
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture")
    return path / "scripts/export_release.py"


def execute(script: Path, action: str, target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), action, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_export_excludes_credentials_raw_data_and_caches(tmp_path: Path) -> None:
    script = repository(tmp_path / "repo")
    output = tmp_path / "export"
    result = execute(script, "--output", output)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((output / "release-manifest.json").read_text())
    assert "frontend/src/app.ts" in manifest["files"]
    assert (output / ".env.example").exists()
    assert not (output / ".env").exists()
    assert not (output / "frontend/node_modules").exists()
    assert not (output / "backend/.venv").exists()
    assert not (output / "backend/data").exists()
    assert not (output / "reports/technical-checkpoint.md").exists()
    assert not (output / "docs/acceptance-validation.md").exists()
    assert (output / "reports/benchmark-v1.json").exists()
    assert (output / "examples/validation/cards.jsonl").exists()
    assert (output / "artifacts/validation/predictions.jsonl").exists()
    assert execute(script, "--verify", output).returncode == 0


def test_credential_leak_is_rejected_before_export(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    script = repository(root)
    (root / "README.md").write_text("fixture-credential-not-real")
    output = tmp_path / "export"
    result = execute(script, "--output", output)
    assert result.returncode == 2
    assert "Credential found" in result.stderr
    assert "fixture-credential-not-real" not in result.stderr
    assert not output.exists()


def test_verification_rejects_changed_source_and_export_refuses_overwrite(tmp_path: Path) -> None:
    script = repository(tmp_path / "repo")
    output = tmp_path / "export"
    assert execute(script, "--output", output).returncode == 0
    assert execute(script, "--output", output).returncode == 2
    (output / "README.md").write_text("changed")
    assert execute(script, "--verify", output).returncode == 2
