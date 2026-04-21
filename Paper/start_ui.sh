#!/usr/bin/env bash
# Per-host venv bootstrap + webui launch.
# venv is named .venv-<hostname> so each PC sharing this drive keeps its own
# interpreter/wheels — avoids the "bad interpreter" failure when the drive is
# remounted on a machine that doesn't have the baked-in python path.
set -euo pipefail

cd "$(dirname "$0")"

HOST="$(hostname -s)"
VENV=".venv-${HOST}"

pick_python() {
  for cand in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      ver="$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
      major="${ver%%.*}"; minor="${ver##*.}"
      if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
        echo "$cand"; return 0
      fi
    fi
  done
  return 1
}

if [ ! -x "$VENV/bin/civatas-exp" ]; then
  echo "[start_ui] bootstrapping $VENV for host $HOST ..."
  PY="$(pick_python)" || { echo "[start_ui] need python >= 3.11 (try: brew install python@3.13)"; exit 1; }
  echo "[start_ui] using $PY ($("$PY" --version))"
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -e .
fi

exec "$VENV/bin/civatas-exp" webui serve --port 8765
