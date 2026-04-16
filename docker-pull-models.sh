#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-host}"
TARGET_URL="http://localhost:11434"

if [[ "$MODE" == "docker" ]]; then
  TARGET_URL="http://localhost:11435"
fi

export OLLAMA_HOST="$TARGET_URL"

for model in qwen2.5:14b llama3.1:8b; do
  echo "Pulling $model via $TARGET_URL"
  ollama pull "$model"
done
