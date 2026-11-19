#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export MODEL_DIR_ID_EN="${MODEL_DIR_ID_EN:-$PWD/models/opus-mt-id-en-ct2}"
export MODEL_DIR_EN_ID="${MODEL_DIR_EN_ID:-$PWD/models/opus-mt-en-id-ct2}"
export CPU_THREADS="${CPU_THREADS:-2}"
export IDLE_UNLOAD_SECONDS="${IDLE_UNLOAD_SECONDS:-120}"
exec uvicorn app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8789}" --workers 1 --ws none
