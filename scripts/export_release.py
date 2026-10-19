import argparse
import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = (
    "README.md",
    ".env.example",
    ".gitignore",
    "docker-compose.yml",
    ".github",
    "backend",
    "frontend",
    "docs",
    "notebooks",
    "reports",
    "scripts",
)
EXCLUDE = frozenset(
    {
        ".git",
        ".local",
        ".venv",
        "node_modules",
        "dist",
        "data",
        "var",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".vite",
        "test-results",
        "playwright-report",
        "blob-report",
        ".ipynb_checkpoints",
        ".aws",
        ".codex",
        ".agents",
        ".claude",
        ".ssh",
        ".idea",
        ".vscode",
        "coverage",
    }
)
SUFFIXES = (
    ".pyc",
    ".pyo",
    ".log",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".tsbuildinfo",
    ".db-wal",
    ".db-shm",
    ".sqlite-wal",
    ".sqlite-shm",
)


def fingerprint(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def files() -> Iterator[Path]:
    for name in INCLUDE:
        path = ROOT / name
        if path.is_file():
            yield path
            continue
        if not path.exists():
            continue
        for directory, directories, filenames in os.walk(path, followlinks=False):
            directories[:] = sorted(
                d
                for d in directories
                if d not in EXCLUDE and not d.endswith(".egg-info")
            )
            for filename in sorted(filenames):
                if filename in {".DS_Store", "AGENTS.md", "CLAUDE.md"}:
                    continue
                if filename.startswith(".env") and filename != ".env.example":
                    continue
                if filename.endswith(SUFFIXES):
                    continue
                yield Path(directory) / filename


def known_keys() -> tuple[bytes, ...]:
    env = ROOT / ".env"
    if not env.is_file():
        return ()
    return tuple(
        value.strip().strip("\"'").encode()
        for line in env.read_text().splitlines()
        if "=" in line
        for name, value in [line.split("=", 1)]
        if name.strip().endswith(("_KEY", "_TOKEN", "_PASSWORD")) and value.strip()
    )


def export(destination: Path) -> None:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Output already exists; choose a new directory")
    selected = list(files())
    secrets = known_keys()
    for source in selected:
        if source.is_symlink():
            raise ValueError(f"Nonportable source symlink: {source.relative_to(ROOT)}")
        if any(secret in source.read_bytes() for secret in secrets):
            raise ValueError(
                f"Credential found in export source: {source.relative_to(ROOT)}"
            )
    destination.mkdir(parents=True)
    manifest = {}
    for source in selected:
        relative = source.relative_to(ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest[str(relative)] = {
            "sha256": fingerprint(target),
            "bytes": target.stat().st_size,
        }
    (destination / "release-manifest.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now(UTC).isoformat(),
                "source": "working tree snapshot",
                "files": manifest,
                "secrets_included": False,
                "scope": "No .git, credentials, caches, raw data or local state; this is not a published clone",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    verify(destination)


def verify(package: Path) -> None:
    root = package.resolve()
    manifest = json.loads((root / "release-manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or fingerprint(path) != expected["sha256"]
        ):
            raise ValueError(f"Package integrity mismatch: {name}")
    print(
        json.dumps(
            {
                "package": str(root),
                "verified_files": len(manifest["files"]),
                "status": "ok",
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path)
    action.add_argument("--verify", type=Path)
    args = parser.parse_args()
    try:
        if args.output:
            export(args.output)
        else:
            verify(args.verify)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
