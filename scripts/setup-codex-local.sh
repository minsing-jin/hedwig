#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OMX_PREFIX="$ROOT/.tools/omx"
OMX_BIN="$OMX_PREFIX/node_modules/.bin/omx"
OMX_VERSION="${OMX_VERSION:-0.9.0}"

PYTHON_BIN="$ROOT/.venv/bin/python"
OUROBOROS_VENV="$ROOT/.tools/ouroboros-venv"
OUROBOROS_PYTHON="$OUROBOROS_VENV/bin/python"
OUROBOROS_BIN="$OUROBOROS_VENV/bin/ouroboros"
OUROBOROS_SPEC="${OUROBOROS_SPEC:-ouroboros-ai==0.26.0b3}"
LOCAL_HOME="$ROOT/.local-home"
LOCAL_OUROBOROS_HOME="$LOCAL_HOME/.ouroboros"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

need_cmd node
need_cmd npm
need_cmd uv
need_cmd codex

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing project Python: $PYTHON_BIN" >&2
  exit 1
fi

mkdir -p "$ROOT/.tools" "$LOCAL_HOME"

echo "[1/4] Installing oh-my-codex locally into $OMX_PREFIX"
npm install --prefix "$OMX_PREFIX" "oh-my-codex@$OMX_VERSION"

echo
echo "[2/4] Installing ouroboros locally into $OUROBOROS_VENV"
uv venv "$OUROBOROS_VENV" --python "$PYTHON_BIN"
uv pip install --python "$OUROBOROS_PYTHON" --upgrade "$OUROBOROS_SPEC"

echo
echo "[3/4] Applying oh-my-codex project-scope setup"
"$ROOT/bin/omx" setup --scope project

echo
echo "[4/4] Initializing repo-local ouroboros home"
HEDWIG_ORIGINAL_HOME="${HOME:-}" HOME="$LOCAL_HOME" ROOT="$ROOT" "$OUROBOROS_PYTHON" - <<'PY'
import os
from pathlib import Path
import yaml

from ouroboros.config.loader import create_default_config

root = Path(os.environ["ROOT"])
config_dir = Path.home() / ".ouroboros"
config_path = config_dir / "config.yaml"
credentials_path = config_dir / "credentials.yaml"

if not config_path.exists() or not credentials_path.exists():
    create_default_config(config_dir, overwrite=False)

with config_path.open() as f:
    data = yaml.safe_load(f) or {}

llm = data.setdefault("llm", {})
llm["backend"] = "codex"
llm["permission_mode"] = "default"

orchestrator = data.setdefault("orchestrator", {})
orchestrator["runtime_backend"] = "codex"
orchestrator["permission_mode"] = "default"
orchestrator["codex_cli_path"] = str(root / "bin" / "omx")

with config_path.open("w") as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

print(f"Configured Ouroboros home at {config_dir}")
PY

echo
echo "Local Codex tooling is ready."
echo "  OMX: $ROOT/bin/omx"
echo "  OOO: $ROOT/bin/ooo"
echo "  Doctor: bash $ROOT/scripts/doctor-codex-local.sh"
