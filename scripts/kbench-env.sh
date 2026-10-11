#!/usr/bin/env bash
# Load Kaggle + model-proxy credentials into the current shell.
#
#   source scripts/kbench-env.sh
#
# Two things this handles that the CLI does not:
#   1. Model-proxy credentials expire (MODEL_PROXY_EXPIRY_TIME). This refreshes
#      them when they are close to expiry, so long runs do not die mid-flight.
#   2. `kaggle b auth` overwrites .env with only the three proxy variables.
#      The LLM_* variables are set here so they survive every refresh.
#
# Must be sourced, not executed.

_kbench_root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
_kbench_env="$_kbench_root/.env"

# KAGGLE_API_TOKEN lives in the shell profile
if [ -z "${KAGGLE_API_TOKEN:-}" ] && [ -f "$HOME/.zprofile" ]; then
  set -a; . "$HOME/.zprofile" 2>/dev/null; set +a
fi

if [ -z "${KAGGLE_API_TOKEN:-}" ]; then
  echo "[kbench-env] ERROR: KAGGLE_API_TOKEN not set (expected in ~/.zprofile)" >&2
  return 1
fi

# refresh proxy creds if missing or expiring within 5 minutes
_kbench_need_auth=1
if [ -f "$_kbench_env" ]; then
  _kbench_exp="$(grep -oP '^MODEL_PROXY_EXPIRY_TIME=\K.*' "$_kbench_env" 2>/dev/null | head -1)"
  if [ -n "$_kbench_exp" ]; then
    _kbench_exp_s="$(date -d "${_kbench_exp%%Z*}" +%s 2>/dev/null || echo 0)"
    _kbench_now_s="$(date -u +%s)"
    if [ "$_kbench_exp_s" -gt $(( _kbench_now_s + 300 )) ]; then
      _kbench_need_auth=0
    fi
  fi
fi

if [ "$_kbench_need_auth" -eq 1 ]; then
  echo "[kbench-env] refreshing model-proxy credentials"
  ( cd "$_kbench_root" && kaggle b auth -y >/dev/null 2>&1 ) || {
    echo "[kbench-env] ERROR: 'kaggle b auth' failed" >&2; return 1; }
fi

set -a
. "$_kbench_env"
set +a

# LLM_* are not written by `kaggle b auth`; set them here so refresh cannot clobber them.
# The local staging proxy exposes a fixed set; list it with:
#   curl -H "Authorization: Bearer $MODEL_PROXY_API_KEY" "$MODEL_PROXY_URL"
export LLM_DEFAULT="${LLM_DEFAULT:-google/gemini-3.7-flash}"
export LLM_DEFAULT_JUDGE="${LLM_DEFAULT_JUDGE:-anthropic/claude-sonnet-5@default}"
export LLMS_AVAILABLE="${LLMS_AVAILABLE:-google/gemini-3.7-flash,anthropic/claude-sonnet-5@default}"

if [ -z "${MODEL_PROXY_API_KEY:-}" ]; then
  echo "[kbench-env] ERROR: MODEL_PROXY_API_KEY missing after auth" >&2
  return 1
fi

echo "[kbench-env] ready — proxy expires ${MODEL_PROXY_EXPIRY_TIME:-unknown}"

unset _kbench_root _kbench_env _kbench_need_auth _kbench_exp _kbench_exp_s _kbench_now_s
