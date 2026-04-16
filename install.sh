#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -m pip install -e "$REPO_DIR"

if command -v playwright >/dev/null 2>&1; then
  playwright install chromium --with-deps || true
fi

if [[ ! -f "$REPO_DIR/.env" && -f "$REPO_DIR/.env.example" ]]; then
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
fi

echo "Installed crewops-core."
echo "Run: crewops-core-dashboard"
