#!/usr/bin/env bash
# Wait for model-proxy quota to return, then push and run the benchmark.
#
# The proxy reserves quota per request from input tokens plus maximum output,
# and refuses a request before sending it when the reservation exceeds the
# remaining balance. While the balance is low, every request fails with a 403
# and the benchmark records a failed cell for each one.
#
# This polls cheaply, and only acts once a request actually succeeds.
#
#   nohup scripts/wait_for_quota.sh > quota-watch.log 2>&1 &

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
POLL_SECONDS="${POLL_SECONDS:-1800}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"

probe() {
  # A tiny request. Success means there is enough balance for real work.
  python3 - <<'PY' >/dev/null 2>&1
import kaggle_benchmarks as kbench
with kbench.chats.new("quota-probe"):
    kbench.llm.prompt("Reply with one word: ok", extra_api_params={"max_tokens": 512})
PY
}

echo "[quota-watch] started $(date -u +%H:%M:%S)"
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  source scripts/kbench-env.sh >/dev/null 2>&1
  if probe; then
    echo "[quota-watch] quota available at $(date -u +%H:%M:%S), starting run"
    kaggle b t push engineering-discipline \
      -f tasks/engineering_discipline.py \
      -d digitamo/engineering-discipline-haystack 2>&1 | tail -3
    kaggle b t run engineering-discipline -m gemini-3.7-flash --wait 2>&1 | tail -8
    kaggle b t download engineering-discipline -o ./runs 2>&1 | tail -3
    echo "[quota-watch] run finished $(date -u +%H:%M:%S)"
    python3 scripts/analyze.py runs/engineering-discipline/**/*.run.json 2>&1 | head -60
    exit 0
  fi
  echo "[quota-watch] attempt $attempt: no quota at $(date -u +%H:%M:%S), sleeping ${POLL_SECONDS}s"
  sleep "$POLL_SECONDS"
done
echo "[quota-watch] gave up after $MAX_ATTEMPTS attempts"
exit 1
