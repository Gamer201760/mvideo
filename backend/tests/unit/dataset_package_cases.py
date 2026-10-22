import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
NAMES = ("sku_desc.parquet", "query_clicks.parquet", "skus.pkl")


def execute(script: str, *arguments: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *(str(value) for value in arguments)],
        capture_output=True,
        text=True,
        check=False,
    )


def source_files(root: Path) -> Path:
    source = root / "raw"
    source.mkdir(parents=True)
    for index, name in enumerate(NAMES):
        (source / name).write_bytes(random.Random(index).randbytes(4096))
    return source


def package_files(root: Path) -> tuple[Path, Path]:
    source = source_files(root)
    package = root / "package"
    code = (
        "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
        "from package_dataset import package;"
        "package(Path(sys.argv[2]),Path(sys.argv[3]),part_bytes=1024)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(SCRIPTS), str(source), str(package)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return source, package
