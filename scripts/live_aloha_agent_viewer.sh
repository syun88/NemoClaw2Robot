#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <sandbox-name> [live-agent options...]" >&2
  echo "Example: $0 mujoco-agent-robot" >&2
  exit 2
fi

SANDBOX_NAME="$1"
shift

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
  "$PYTHON" -m nemoclaw2robot.cli live-agent --sandbox "$SANDBOX_NAME" "$@"
