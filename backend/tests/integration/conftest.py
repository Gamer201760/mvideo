import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.seed import seed


@pytest.fixture
def database(tmp_path: Path) -> Path:
    binary = os.environ.get("DBMATE_BIN") or shutil.which("dbmate")
    if not binary or not Path(binary).is_file():
        pytest.fail("dbmate is required; install it or set DBMATE_BIN to its executable")
    database = tmp_path / "app.db"
    migrations = Path(__file__).resolve().parents[2] / "migrations/sqlite"
    result = subprocess.run(
        [
            binary,
            "--url",
            f"sqlite:{database}",
            "--migrations-dir",
            str(migrations),
            "--no-dump-schema",
            "up",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        pytest.fail(f"dbmate migrations failed: {result.stderr}")
    asyncio.run(seed(database))
    return database
