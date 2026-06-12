#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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
  "$PYTHON" -m nemoclaw2robot.cli live "$@"
