#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "python tidak ditemukan" >&2
  exit 1
fi

build() {
  local repo_id="$1" out_dir="$2" tmp_dir
  tmp_dir="$(mktemp -d)"
  echo "[1/2] unduh $repo_id"
  "$PY" - "$repo_id" "$tmp_dir" <<'PYEOF'
import sys
from huggingface_hub import snapshot_download
repo_id, local_dir = sys.argv[1], sys.argv[2]
snapshot_download(
    repo_id=repo_id,
    local_dir=local_dir,
    allow_patterns=["config.json", "generation_config.json", "pytorch_model.bin",
                    "source.spm", "target.spm", "vocab.json", "tokenizer_config.json"],
)
PYEOF
  echo "[2/2] konversi ke CTranslate2 INT8 -> $out_dir"
  rm -rf "$out_dir"
  "$PY" -m ctranslate2.converters.transformers \
    --model "$tmp_dir" --output_dir "$out_dir" --quantization int8 --force
  cp -f "$tmp_dir"/source.spm "$tmp_dir"/target.spm "$tmp_dir"/vocab.json "$tmp_dir"/tokenizer_config.json "$out_dir"/
  rm -rf "$tmp_dir"
  du -sh "$out_dir"
}

build Helsinki-NLP/opus-mt-id-en models/opus-mt-id-en-ct2
build Helsinki-NLP/opus-mt-en-id models/opus-mt-en-id-ct2
echo "selesai. jalankan ./start.sh lalu cek /api/health"
