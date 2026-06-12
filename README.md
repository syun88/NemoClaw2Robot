# NemoClaw2Robot

NemoClaw2Robot is a project-side bridge for using NemoClaw/OpenClaw agents to operate robot tasks in MuJoCo simulation.

The first supported target is the official ALOHA 2 MuJoCo model from Google DeepMind's MuJoCo Menagerie. A user can ask for a task in Japanese or English, and the project can:

1. Parse the prompt into a robot task plan.
2. Automatically generate a MuJoCo scene by loading the official ALOHA MJCF and adding task objects.
3. Run a scripted headless controller when MuJoCo is installed.
4. Provide a NemoClaw `SKILL.md` package and OpenClaw plugin tools so the sandbox agent can run the workflow directly.
5. Optionally run a host-side live MuJoCo viewer watcher that the sandbox agent can control.

`NemoClaw/` and `external/mujoco_menagerie/` are upstream git submodules. Do not edit files inside them for this project.

Current scope: the MuJoCo controller is a deterministic scaffold. It opens and closes the official ALOHA gripper joints, but the cube lift/transfer stage still uses scripted attachment after closing instead of a learned policy or contact-only grasp.
Prompts can request a cube or sphere object; the controller keeps a stable internal object joint while changing the generated MuJoCo geom shape.

## Setup

```bash
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Install MuJoCo support when you want to execute the simulator:

```bash
pip install -e '.[sim,dev]'
```

## Run Locally

Generate a plan and scene without requiring MuJoCo:

```bash
PYTHONPATH=src python3 -m nemoclaw2robot.cli run \
  --prompt "Alohaのアームロボットでキューブを掴んでください" \
  --no-sim
```

Run the same prompt with MuJoCo installed:

```bash
PYTHONPATH=src python3 -m nemoclaw2robot.cli run \
  --prompt "Alohaのアームロボットでキューブを掴んでください"
```

Open a real-time native MuJoCo viewer on the host machine:

```bash
scripts/view_aloha_prompt.sh "Alohaのアームロボットでキューブを掴んでください"
```

On macOS, the script prefers `.venv/bin/mjpython`, which is the most reliable launcher for the native MuJoCo UI.
NemoClaw/OpenClaw sandboxes are headless by default. The sandbox can run tools and write requests, but the visible native MuJoCo window must be opened by a process on the Mac host.

Run an Agent-controlled live viewer watcher on the host:

```bash
scripts/live_aloha_agent_viewer.sh mujoco-agent-robot
```

Keep that process running, then ask the OpenClaw TUI for a live task, for example:

```text
リアルタイムでAlohaのアームロボットが球体を掴むところを見たい
```

The sandbox OpenClaw tool `aloha_mujoco_live` queues the prompt under `/sandbox/NemoClaw2Robot/artifacts/live_requests/`. The host watcher polls that queue through `openshell sandbox exec`, then opens the native MuJoCo viewer and plays the generated task. This avoids direct sandbox-to-host HTTP, which may be blocked by NemoClaw network policy.

The optional direct HTTP bridge is still available for environments that allow sandbox-to-host POST:

```bash
scripts/live_aloha_viewer.sh
```

Outputs are written under `artifacts/runs/<timestamp>/`:

- `plan.json`
- `scene.xml`
- `trajectory.json` when MuJoCo ran
- `summary.md`

## Install The Robot Skill Into NemoClaw

Start or reuse a NemoClaw sandbox, then install the project skill:

```bash
scripts/install_robot_skill.sh <sandbox-name>
```

This installs the `SKILL.md`, uploads the Python runtime to `/sandbox/NemoClaw2Robot`, creates `/sandbox/NemoClaw2Robot/.venv`, installs `nemoclaw2robot` with MuJoCo support inside the sandbox, and registers the project-side OpenClaw plugin `aloha-mujoco`.

The plugin registers these OpenClaw tools:

- `aloha_mujoco_plan`: parse a prompt into a task plan.
- `aloha_mujoco_run`: build the scene, run the controller, and write artifacts.
- `aloha_mujoco_live`: queue a prompt for the host-side live viewer watcher for visible playback.

The skill lives at:

```text
.agents/skills/robot-aloha-mujoco/
```

The installer uploads `external/mujoco_menagerie/aloha/` into the sandbox so generated MuJoCo scenes can load the official meshes and MJCF files.

After installing it, prompt the sandbox agent with a task such as:

```text
Alohaのアームロボットでキューブを掴んでください。simも自動でシーン構築してください。
```

## Project Layout

```text
NemoClaw/                         # upstream submodule, read-only here
external/mujoco_menagerie/        # upstream official MuJoCo models, read-only here
.agents/skills/robot-aloha-mujoco # NemoClaw/OpenClaw skill package
openclaw-plugins/aloha-mujoco     # project-side OpenClaw tools
src/nemoclaw2robot/               # prompt parser, scene builder, controller, CLI
scripts/                          # host convenience wrappers
tests/                            # parser, scene, and skill layout tests
docs/architecture.md              # implementation flow
```

## Validate

```bash
python3 -m pytest -q
python3 -m compileall src
```
