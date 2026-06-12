#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <nemoclaw-sandbox-name> [--skip-runtime]" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX_NAME="$1"
SKIP_RUNTIME="${2:-}"
SKILL_DIR="$ROOT_DIR/.agents/skills/robot-aloha-mujoco"
REMOTE_ROOT="/sandbox/NemoClaw2Robot"

if [[ "$SKIP_RUNTIME" != "" && "$SKIP_RUNTIME" != "--skip-runtime" ]]; then
  echo "Unknown option: $SKIP_RUNTIME" >&2
  exit 2
fi

nemoclaw "$SANDBOX_NAME" skill install "$SKILL_DIR"

if [[ "$SKIP_RUNTIME" == "--skip-runtime" ]]; then
  exit 0
fi

openshell sandbox exec -g nemoclaw -n "$SANDBOX_NAME" -- mkdir -p "$REMOTE_ROOT"
openshell sandbox exec -g nemoclaw -n "$SANDBOX_NAME" -- mkdir -p "$REMOTE_ROOT/external/mujoco_menagerie"
openshell sandbox upload -g nemoclaw "$SANDBOX_NAME" "$ROOT_DIR/src" "$REMOTE_ROOT"
openshell sandbox upload -g nemoclaw "$SANDBOX_NAME" "$ROOT_DIR/external/mujoco_menagerie/aloha" "$REMOTE_ROOT/external/mujoco_menagerie"
openshell sandbox upload -g nemoclaw "$SANDBOX_NAME" "$ROOT_DIR/pyproject.toml" "$REMOTE_ROOT"
openshell sandbox upload -g nemoclaw "$SANDBOX_NAME" "$ROOT_DIR/README.md" "$REMOTE_ROOT"

openshell sandbox exec -g nemoclaw -n "$SANDBOX_NAME" --workdir "$REMOTE_ROOT" -- \
  bash -lc 'python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -e ".[sim]"'

"$ROOT_DIR/scripts/install_openclaw_robot_plugin.sh" "$SANDBOX_NAME"

echo "Installed robot skill, runtime, and OpenClaw plugin in $SANDBOX_NAME:$REMOTE_ROOT"
