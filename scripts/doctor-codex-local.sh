#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

check_path() {
  if [ ! -e "$1" ]; then
    echo "Missing expected path: $1" >&2
    exit 1
  fi
}

check_exec() {
  if [ ! -x "$1" ]; then
    echo "Missing executable: $1" >&2
    exit 1
  fi
}

check_exec "$ROOT/bin/omx"
check_exec "$ROOT/bin/ooo"
check_exec "$ROOT/.tools/omx/node_modules/.bin/omx"
check_exec "$ROOT/.tools/ouroboros-venv/bin/ouroboros"

check_path "$ROOT/.codex/config.toml"
check_path "$ROOT/.agents/skills"
check_path "$ROOT/.omx/setup-scope.json"
check_path "$ROOT/AGENTS.md"
check_path "$ROOT/.local-home/.ouroboros/config.yaml"

if ! grep -Eq '"scope"[[:space:]]*:[[:space:]]*"project"' "$ROOT/.omx/setup-scope.json"; then
  echo "Unexpected OMX setup scope in $ROOT/.omx/setup-scope.json" >&2
  exit 1
fi

echo "[1/4] Local OMX version"
"$ROOT/bin/omx" version

echo
echo "[2/4] Local Ouroboros version"
"$ROOT/bin/ooo" --version

echo
echo "[3/4] OMX doctor"
"$ROOT/bin/omx" doctor >/dev/null
echo "omx doctor passed"

echo
echo "[4/4] Ouroboros config validation"
HOME="$ROOT/.local-home" ROOT="$ROOT" "$ROOT/.tools/ouroboros-venv/bin/python" - <<'PY'
import os
from pathlib import Path

from ouroboros.config.loader import load_config

config = load_config()
assert config.llm.backend == "codex", config.llm.backend
assert config.orchestrator.runtime_backend == "codex", config.orchestrator.runtime_backend
assert config.orchestrator.codex_cli_path == str(Path(os.environ["ROOT"]) / "bin" / "omx"), config.orchestrator.codex_cli_path
print("ouroboros config load passed")
PY

echo
echo "Repo-local Codex tooling is healthy."
