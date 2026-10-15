#!/usr/bin/env bash
set -euo pipefail

DATA="${1:-../data/processed}"
OUT="${2:-../data/predictions}"
SHARDS="${SHARDS:-5}"
PARALLEL="${PARALLEL:-3}"
WORK="${WORK:-../data/shards}"
STAGE="${STAGE:-baseline}"
RANKER_MODEL="${RANKER_MODEL:-../data/models/ranker_final}"
FUSION_MODEL="${FUSION_MODEL:-../data/models/fusion}"
REPORTS="${REPORTS:-../reports}"
TWINS="${TWINS:-1}"
TWIN_MODEL="${TWIN_MODEL:-../data/models/twins}"

run_shard() {
  local i="$1"
  if [[ "$STAGE" == "final" ]]; then
    OMP_NUM_THREADS=1 nice -n 10 uv run ranker --data "$WORK/$i" --out "$WORK/out_$i" \
      --name ranker_final --load-model "$RANKER_MODEL" --threads 1
  else
    nice -n 10 uv run baseline --data "$WORK/$i" --out "$WORK/out_$i" \
      --reports "$WORK/reports_$i" --all-cards --no-candidates
  fi
}

rm -rf "$WORK"
uv run shard-cards --data "$DATA" --out "$WORK" --shards "$SHARDS"
for ((first = 0; first < SHARDS; first += PARALLEL)); do
  pids=()
  for ((i = first; i < first + PARALLEL && i < SHARDS; i++)); do
    run_shard "$i" > "$WORK/log_$i.txt" 2>&1 &
    pids+=("$!")
  done
  for pid in "${pids[@]}"; do
    wait "$pid"
  done
done
mkdir -p "$OUT"
if [[ "$STAGE" == "final" ]]; then
  if [[ "$TWINS" == "1" ]]; then
    OMP_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 nice -n 10 uv run twins --data "$DATA" --out "$OUT" \
      --reports "$REPORTS" --stage ranker_final --name twins_final --all-cards --work "$WORK" \
      --shard-count "$SHARDS" --save-model "$TWIN_MODEL"
  fi
  shards=()
  for ((i = 0; i < SHARDS; i++)); do
    shards+=("$WORK/out_$i")
  done
  nice -n 10 uv run final --all-cards --shards "${shards[@]}" --out "$OUT" \
    --reports "$REPORTS" --model "$FUSION_MODEL"
  wc -l "$OUT/final_all.predictions.jsonl"
  exit 0
fi
target="$OUT/baseline_all.predictions.jsonl"
if [[ -f "$target" ]]; then
  mv "$target" "$target.bak"
fi
for ((i = 0; i < SHARDS; i++)); do
  cat "$WORK/out_$i/baseline_all.predictions.jsonl"
done > "$target"
wc -l "$target"
