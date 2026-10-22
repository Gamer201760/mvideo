import argparse
import gzip
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

from dataset_package_io import BLOCK_BYTES, PART_BYTES, SOURCE_NAMES, PartWriter, publish, staging


def package(
    source: Path, output: Path, *, part_bytes: int = PART_BYTES, level: int = 1
) -> dict[str, object]:
    if not 1 <= part_bytes <= PART_BYTES or not 1 <= level <= 3:
        raise ValueError("Parts must be 1..32 MiB and compression level 1..3")
    source, output = source.absolute(), output.absolute()
    for name in SOURCE_NAMES:
        path = source / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
            raise ValueError(f"Missing or unsafe source file: {name}")
    stage = staging(output)
    (stage / "parts").mkdir()
    started = time.monotonic()
    files = []

    def report(progress: dict[str, object]) -> None:
        print(
            json.dumps({**progress, "elapsed_s": round(time.monotonic() - started, 2)}), flush=True
        )

    try:
        for name in SOURCE_NAMES:
            path = source / name
            initial = path.stat()
            digest, size = hashlib.sha256(), 0
            writer = PartWriter(stage, name, part_bytes, report)
            try:
                with (
                    path.open("rb") as raw,
                    gzip.GzipFile(
                        fileobj=writer, mode="wb", filename="", mtime=0, compresslevel=level
                    ) as compressed,
                ):
                    for block in iter(lambda: raw.read(BLOCK_BYTES), b""):
                        digest.update(block)
                        size += len(block)
                        compressed.write(block)
                writer.finish()
            finally:
                writer.abort()
            final = path.stat()
            if (initial.st_size, initial.st_mtime_ns) != (
                final.st_size,
                final.st_mtime_ns,
            ) or size != initial.st_size:
                raise ValueError(f"Source changed during packaging: {name}")
            files.append(
                {
                    "name": name,
                    "size": size,
                    "sha256": digest.hexdigest(),
                    "compressed_size": writer.total,
                    "parts": writer.parts,
                }
            )
            report(
                {
                    "file": name,
                    "source_bytes": size,
                    "compressed_bytes": writer.total,
                    "status": "complete",
                }
            )
        manifest: dict[str, object] = {
            "format": "organizer-source-v1",
            "compression": "gzip",
            "part_bytes": part_bytes,
            "files": files,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        publish(stage, output)
        report({"status": "complete", "files": len(files)})
        return manifest
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Package exact organizer files as checksummed gzip parts"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--part-mib", type=int, default=32)
    parser.add_argument("--level", type=int, default=1)
    args = parser.parse_args()
    try:
        package(args.source, args.output, part_bytes=args.part_mib * 1024 * 1024, level=args.level)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
