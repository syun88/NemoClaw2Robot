#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <prompt> [extra nemoclaw2robot view args...]" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROMPT="$1"
shift

if [[ -x "$ROOT_DIR/.venv/bin/mjpython" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/mjpython"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PYTHON="python3"
fi

if [[ "$(basename "$PYTHON")" == "mjpython" ]]; then
  export NEMOCLAW2ROBOT_MJPYTHON=1
fi

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON" -m nemoclaw2robot.cli view --prompt "$PROMPT" "$@"
