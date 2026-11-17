#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export MODEL_DIR="${MODEL_DIR:-$PWD/models/opus-mt-id-en-ct2}"
export CPU_THREADS="${CPU_THREADS:-2}"
export IDLE_UNLOAD_SECONDS="${IDLE_UNLOAD_SECONDS:-120}"
exec uvicorn app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8789}" --workers 1 --ws none
