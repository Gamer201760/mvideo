import argparse
import json
import sys
from pathlib import Path

from dataset_verification import verify
from restore_dataset import DEFAULT_PACKAGE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify dataset parts, gzip streams and original SHA-256"
    )
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args()
    try:
        manifest = verify(args.package)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "files": len(manifest["files"]),
                "source_bytes": sum(item["size"] for item in manifest["files"]),
                "compressed_bytes": sum(item["compressed_size"] for item in manifest["files"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
