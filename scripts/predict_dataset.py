import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from prediction_http import endpoint, predict
from prediction_io import atomic_manifest, fingerprint, inspect_input, rows


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export per-card predictions from the running API")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--engine", choices=("rules", "hybrid"), default="rules")
    parser.add_argument("--timeout", type=float, default=120)
    return parser.parse_args()


def export(args: argparse.Namespace) -> int:
    url = endpoint(args.base_url)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("timeout must be positive and finite")
    total, input_hash = inspect_input(args.input)
    manifest_path = args.manifest or args.output.parent / "manifest.json"
    paths = [
        args.output,
        manifest_path,
        manifest_path.with_name(manifest_path.name + ".tmp"),
    ]
    if args.input.resolve() in {path.resolve() for path in paths}:
        raise ValueError("Output and manifest must be distinct from the input")
    if args.output.resolve() == manifest_path.resolve():
        raise ValueError("Output and manifest paths must differ")
    if any(path.exists() or path.is_symlink() for path in paths):
        raise FileExistsError("Refusing to overwrite output, manifest or incomplete checkpoint")
    for path in paths[:2]:
        path.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "format": "prediction-export-v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "engine": args.engine,
        "endpoint": "/api/v1/extract",
        "base_url": args.base_url.rstrip("/"),
        "input": {"file": args.input.name, "sha256": input_hash, "cards": total},
        "output": {"file": args.output.name},
        "counts": {"processed": 0, "ok": 0, "error": 0},
        "records": [],
        "scope": "Per-card API output; not an independent quality or calibration evaluation",
    }
    counts = {"processed": 0, "ok": 0, "error": 0}
    records: list[dict[str, object]] = []
    digest = hashlib.sha256()
    with args.output.open("xb") as output:
        try:
            with manifest_path.open("x", encoding="utf-8") as stream:
                json.dump(manifest, stream)
        except OSError:
            args.output.unlink()
            raise
        atomic_manifest(manifest_path, manifest)
        for row in rows(args.input):
            result = predict(url, row, args.engine, args.timeout)
            data = (json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n").encode()
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            digest.update(data)
            counts["processed"] += 1
            status = str(result["status"])
            counts[status] += 1
            records.append({"id": row["id"], "line": counts["processed"], "status": status})
            manifest.update(
                {
                    "output": {"file": args.output.name, "sha256": digest.hexdigest()},
                    "counts": counts,
                    "records": records,
                }
            )
            atomic_manifest(manifest_path, manifest)
    if fingerprint(args.input) != input_hash:
        raise ValueError("Input changed during prediction; export is not complete")
    manifest.update({"status": "completed", "finished_at": datetime.now(timezone.utc).isoformat()})
    atomic_manifest(manifest_path, manifest)
    print(json.dumps({"counts": counts, "output_sha256": digest.hexdigest()}))
    return 1 if counts["error"] else 0


def main() -> int:
    try:
        return export(arguments())
    except (OSError, TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(
            "Interrupted; completed records and their checkpoint remain on disk",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
