import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from dataset_manifest import load_manifest
from dataset_package_io import publish, staging
from dataset_verification import verified_blocks

DEFAULT_PACKAGE = Path(__file__).resolve().parents[1] / "artifacts/source"


def restore(package: Path, output: Path) -> None:
    manifest = load_manifest(package)
    output = output.absolute()
    stage = staging(output)
    try:
        for item in manifest["files"]:
            with (stage / item["name"]).open("xb") as stream:
                for block in verified_blocks(package, item):
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
        publish(stage, output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and restore all three organizer files")
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        restore(args.package, args.output)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({"status": "ok", "restored_files": 3}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
