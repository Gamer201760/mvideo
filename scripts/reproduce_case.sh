#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf '%s\n' 'Usage: bash scripts/reproduce_case.sh data/<new-run>' >&2
  exit 2
fi

cd "$(dirname "$0")/.."
run_output="$1"
python3 - "$run_output" <<'PY'
import re
import sys
from pathlib import Path

parts = sys.argv[1].split("/")
if len(parts) < 2 or parts[0] != "data" or any(
    re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", part) is None or part in {".", ".."}
    for part in parts
):
    raise SystemExit("Output must be a new relative path under data, without traversal or empty segments")
path = Path.cwd()
for part in parts:
    path = path / part
    if path.is_symlink():
        raise SystemExit("Output path cannot contain symlinks")
    if path.exists() and not path.is_dir():
        raise SystemExit("Output path conflicts with an existing file")
stage = path.with_name(path.name + ".building")
if path.exists() or stage.exists() or stage.is_symlink():
    raise SystemExit("Output or incomplete staging directory already exists; choose a new run")
PY

command -v docker >/dev/null
mkdir -p -- "${run_output%/*}"
mkdir -- "$run_output"
export GATEWAY_API_KEY= OPENAI_API_KEY= GATEWAY_URL= OPENAI_BASE_URL= GATEWAY_MODEL= OPENAI_MODEL=
compose=(docker compose --env-file /dev/null --profile tools)
container_output="/workspace/$run_output"
container_user="$(id -u):$(id -g)"

run_dataset() {
  "${compose[@]}" run --rm --no-deps --user "$container_user" \
    -e HOME=/tmp \
    -e UV_CACHE_DIR=/workspace/.local/uv-cache \
    -e UV_PROJECT_ENVIRONMENT=/workspace/.local/data-env \
    -e PYTHONPATH=/workspace/backend/src:/workspace/backend \
    -e GATEWAY_API_KEY= -e OPENAI_API_KEY= -e GATEWAY_URL= -e OPENAI_BASE_URL= \
    -e GATEWAY_MODEL= -e OPENAI_MODEL= dataset "$@"
}

printf '%s\n' 'Restoring and verifying organizer source files'
python3 scripts/restore_dataset.py --output "$run_output/raw"
"${compose[@]}" build backend
run_dataset python -m app.prepare_data --raw "$container_output/raw" \
  --out "$container_output/processed" --threads 2
run_dataset python -m analysis.execute --raw "$container_output/raw" \
  --processed "$container_output/processed" --notebook "$container_output/eda.ipynb" \
  --report "$container_output/eda.json" --figures "$container_output/figures"
run_dataset python -m batch_predict --data "$container_output/processed" \
  --output "$container_output/predictions" --workers 2
run_dataset python -m batch_predict.verify --data "$container_output/processed" \
  --output "$container_output/predictions" --write-receipt
printf 'Complete: %s\n' "$run_output"
