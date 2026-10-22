import hashlib
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

SOURCE_NAMES = ("sku_desc.parquet", "query_clicks.parquet", "skus.pkl")
BLOCK_BYTES = 1024 * 1024
PART_BYTES = 32 * 1024 * 1024


def fingerprint(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(BLOCK_BYTES), b""):
            result.update(block)
    return result.hexdigest()


def staging(output: Path) -> Path:
    if output.exists() or output.is_symlink():
        raise FileExistsError("Output already exists; choose a new directory")
    stage = output.with_name(output.name + ".building")
    if stage.exists() or stage.is_symlink():
        raise FileExistsError("Incomplete staging directory exists; inspect it before retrying")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage.mkdir()
    return stage


def publish(stage: Path, output: Path) -> None:
    created: list[tuple[Path, Path]] = []
    directories: list[Path] = []
    output.mkdir()
    try:
        for source in sorted(
            stage.rglob("*"), key=lambda path: (path.name == "manifest.json", str(path))
        ):
            target = output / source.relative_to(stage)
            if source.is_dir():
                target.mkdir()
                directories.append(target)
            else:
                os.link(source, target)
                created.append((source, target))
    except BaseException:
        for source, target in reversed(created):
            if target.exists() and target.samefile(source):
                target.unlink()
        for directory in reversed(directories):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            output.rmdir()
        except OSError:
            pass
        raise
    shutil.rmtree(stage)


class PartWriter:
    def __init__(
        self, root: Path, name: str, limit: int, report: Callable[[dict[str, object]], None]
    ) -> None:
        self.root, self.name, self.limit, self.report = root, name, limit, report
        self.parts: list[dict[str, object]] = []
        self.stream: BinaryIO | None = None
        self.size = 0
        self.total = 0
        self.digest = hashlib.sha256()
        self.path = Path()

    def write(self, data: bytes) -> int:
        pending = memoryview(data)
        while pending:
            if self.stream is None:
                self.path = Path("parts") / f"{self.name}.gz.{len(self.parts):05d}"
                self.stream = (self.root / self.path).open("xb")
            block = pending[: self.limit - self.size]
            self.stream.write(block)
            self.digest.update(block)
            self.size += len(block)
            self.total += len(block)
            pending = pending[len(block) :]
            if self.size == self.limit:
                self.finish()
        return len(data)

    def flush(self) -> None:
        if self.stream is not None:
            self.stream.flush()

    def finish(self) -> None:
        if self.stream is None:
            return
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.stream.close()
        self.parts.append(
            {"name": self.path.as_posix(), "size": self.size, "sha256": self.digest.hexdigest()}
        )
        self.report({"file": self.name, "part": len(self.parts), "compressed_bytes": self.total})
        self.stream, self.size = None, 0
        self.digest = hashlib.sha256()

    def abort(self) -> None:
        if self.stream is not None:
            self.stream.close()
            self.stream = None
