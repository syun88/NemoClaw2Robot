#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <nemoclaw-sandbox-name>" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX_NAME="$1"
PLUGIN_DIR="$ROOT_DIR/openclaw-plugins/aloha-mujoco"
REMOTE_ROOT="/sandbox/NemoClaw2Robot"
REMOTE_PLUGIN_DIR="$REMOTE_ROOT/openclaw-plugins/aloha-mujoco"

if [[ ! -f "$PLUGIN_DIR/openclaw.plugin.json" ]]; then
  echo "OpenClaw plugin manifest not found: $PLUGIN_DIR/openclaw.plugin.json" >&2
  exit 1
fi

openshell sandbox exec -g nemoclaw -n "$SANDBOX_NAME" -- mkdir -p "$REMOTE_ROOT/openclaw-plugins"
openshell sandbox upload -g nemoclaw "$SANDBOX_NAME" "$PLUGIN_DIR" "$REMOTE_ROOT/openclaw-plugins"

openshell sandbox exec -g nemoclaw -n "$SANDBOX_NAME" --workdir "$REMOTE_ROOT" -- \
  openclaw plugins install "$REMOTE_PLUGIN_DIR" --force --dangerously-force-unsafe-install

openshell sandbox exec -g nemoclaw -n "$SANDBOX_NAME" -- \
  bash -lc 'openclaw plugins list | grep -i "aloha-mujoco"'

echo "Installed OpenClaw ALOHA MuJoCo plugin in $SANDBOX_NAME"
