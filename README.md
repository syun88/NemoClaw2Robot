# NemoClaw2Robot

NemoClaw2Robot is a project-side bridge for controlling an ALOHA arm robot in MuJoCo from a NemoClaw/OpenClaw Agent.

The first supported target is the official ALOHA 2 MuJoCo model from Google DeepMind's MuJoCo Menagerie. The user gives a Japanese or English prompt, and the Agent can:

1. Parse the prompt into a robot task.
2. Load the official ALOHA MJCF model.
3. Automatically add task objects such as a cube, sphere, target pad, and push lane.
4. Run a scripted MuJoCo controller for grasp/place/push tasks.
5. Write task artifacts for inspection.
6. Optionally show the motion in a live native MuJoCo viewer on the Mac host.

`NemoClaw/` and `external/mujoco_menagerie/` are upstream git submodules. They are treated as read-only. This repository adds the robot-specific skill, plugin, scene builder, controller, scripts, and tests outside those submodules.

## Current Scope

This is a working prototype for Agent-driven MuJoCo scene construction and ALOHA arm control.

The current controller is deterministic and scripted. It opens and closes the official ALOHA gripper joints and moves the arm through approach, pre-grasp, close, lift, place, and push phases. The lift/transfer stage still uses scripted attachment after the close phase, so this is not yet a learned VLA policy or a pure contact-physics grasp.

Supported object prompts include cube and sphere:

- `キューブ`, `cube`, `block`, `box` -> cube geom
- `球体`, `球`, `ボール`, `sphere`, `ball` -> sphere geom

## Requirements

- Python `>=3.10`
- MuJoCo Python package when running simulation or viewer
- NemoClaw/OpenClaw and OpenShell when using the Agent sandbox
- macOS native viewer users should prefer `mjpython`; the provided viewer scripts do this automatically when `.venv/bin/mjpython` exists

## Setup

```bash
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[sim,dev]'
```

If you only need plan/scene generation without MuJoCo execution, `.[dev]` is enough:

```bash
python -m pip install -e '.[dev]'
```

## Local Use Without NemoClaw

Generate plan/scene artifacts without running MuJoCo:

```bash
scripts/run_aloha_prompt.sh \
  "Alohaのアームロボットでキューブを掴んでください" \
  --no-sim
```

Run the scripted MuJoCo controller and write artifacts:

```bash
scripts/run_aloha_prompt.sh \
  "Alohaのアームロボットでキューブを掴んでください"
```

Open a native MuJoCo viewer for a one-off local playback:

```bash
scripts/view_aloha_prompt.sh \
  "Alohaのアームロボットでキューブを掴んでください"
```

Try a sphere instead of a cube:

```bash
scripts/view_aloha_prompt.sh \
  "Alohaのアームロボットで球体を掴んでください"
```

Outputs are written under `artifacts/runs/<timestamp>/`:

- `plan.json`: normalized robot task
- `scene.xml`: generated MuJoCo MJCF scene
- `trajectory.json`: controller frames when MuJoCo ran
- `summary.md`: human-readable run summary

## Install Into NemoClaw/OpenClaw

Start or reuse a NemoClaw sandbox, for example `mujoco-agent-robot`, then install the robot skill, project runtime, official ALOHA model copy, and OpenClaw plugin:

```bash
scripts/install_robot_skill.sh mujoco-agent-robot
```

The installer uploads this project to:

```text
/sandbox/NemoClaw2Robot
```

It also registers the project-side OpenClaw plugin `aloha-mujoco`.

The plugin exposes these tools to the Agent:

- `aloha_mujoco_plan`: parse a prompt into a normalized task
- `aloha_mujoco_run`: build the scene, run the scripted controller, and write artifacts
- `aloha_mujoco_live`: queue a live-viewer request for host-side visual playback

After installation, connect to the sandbox and start the TUI:

```bash
nemoclaw mujoco-agent-robot connect
```

Inside the sandbox shell:

```bash
openclaw tui
```

Then prompt the Agent:

```text
Alohaのアームロボットでキューブを掴んでください。simも自動でシーン構築してください。
```

Expected behavior:

1. The Agent uses the `robot-aloha-mujoco` skill.
2. The Agent calls `aloha_mujoco_run`.
3. The tool parses the prompt into robot/action/object/hand/target.
4. The tool generates an ALOHA MuJoCo scene from the official MJCF.
5. The scripted controller runs, and artifacts are written under `/sandbox/NemoClaw2Robot/artifacts/runs/<timestamp>/`.

## Real-Time Agent Viewer

NemoClaw/OpenClaw sandboxes are headless by default. The Agent can decide and queue the robot task inside the sandbox, but the visible MuJoCo window must be opened by a process on the Mac host.

Use two terminals.

Terminal A, on the Mac host:

```bash
cd /path/to/NemoClaw2Robot
scripts/live_aloha_agent_viewer.sh mujoco-agent-robot
```

Keep this process running.

Terminal B, connect to the sandbox from the Mac host:

```bash
nemoclaw mujoco-agent-robot connect
```

After the prompt changes to the sandbox shell, start OpenClaw TUI inside the sandbox:

```bash
openclaw tui
```

Then ask for a live task:

```text
リアルタイムでAlohaのアームロボットがキューブを掴むところを見たい
```

Or:

```text
リアルタイムでAlohaのアームロボットが球体を掴むところを見たい
```

Expected live flow:

1. The Agent calls `aloha_mujoco_live`.
2. The tool writes a JSON request under `/sandbox/NemoClaw2Robot/artifacts/live_requests/`.
3. The Mac host watcher polls that queue through `openshell sandbox exec`.
4. The host opens the native MuJoCo viewer and plays the generated ALOHA task.

The optional direct HTTP bridge is still available for environments that allow sandbox-to-host POST:

```bash
scripts/live_aloha_viewer.sh
```

The queue-based `live_aloha_agent_viewer.sh` path is the recommended path because NemoClaw network policy may block direct sandbox-to-host HTTP.

## Prompt Examples

```text
Alohaのアームロボットでキューブを掴んでください
Alohaのアームロボットで球体を掴んでください
Alohaでキューブを目標位置に置いてください
Use the ALOHA robot arm to pick up the cube
Use ALOHA to push the cube
リアルタイムでAlohaのアームロボットが球体を掴むところを見たい
```

Prompt mapping:

- grasp words: `掴`, `つか`, `grab`, `grasp`, `pick`
- place words: `置`, `移動`, `place`, `put`, `move`
- push words: `押`, `push`, `slide`
- inspect words: `確認`, `観察`, `inspect`, `observe`
- left/right arm words: `左`, `right`, `left`, `右`

## Project Layout

```text
NemoClaw/                         # upstream submodule, read-only here
external/mujoco_menagerie/        # upstream official MuJoCo models, read-only here
.agents/skills/robot-aloha-mujoco # NemoClaw/OpenClaw skill package
openclaw-plugins/aloha-mujoco     # project-side OpenClaw tools
src/nemoclaw2robot/               # prompt parser, scene builder, controller, viewer, CLI
scripts/                          # host convenience wrappers
tests/                            # parser, scene, plugin, and skill layout tests
docs/architecture.md              # implementation flow
artifacts/                        # generated outputs, ignored by git
```

## Troubleshooting

If the Agent only says it generated files but no window appears, start the host watcher first:

```bash
scripts/live_aloha_agent_viewer.sh mujoco-agent-robot
```

If `aloha_mujoco_live` is not found in TUI, reinstall the skill/plugin:

```bash
scripts/install_robot_skill.sh mujoco-agent-robot
```

Then reconnect to the sandbox or restart the OpenClaw gateway so the plugin is reloaded.

If the macOS MuJoCo window does not open, use the viewer script or run with `mjpython`:

```bash
.venv/bin/mjpython -m nemoclaw2robot.cli view \
  --prompt "Alohaのアームロボットでキューブを掴んでください"
```

If you only want to verify parsing and scene generation, run with `--no-sim`.

## Validate

```bash
python3 -m pytest -q
python3 -m compileall src
node --check openclaw-plugins/aloha-mujoco/index.js
```
