# NemoClaw2Robot Agent Guide

## Project Purpose

NemoClaw2Robot connects a NemoClaw/OpenClaw agent to MuJoCo robot simulation tasks.
The first supported robot is the official ALOHA 2 MuJoCo model from Google DeepMind's MuJoCo Menagerie, with project-generated task objects and a scripted controller for cube manipulation.

## Hard Boundary

- `NemoClaw/` is an upstream git submodule.
- `external/mujoco_menagerie/` is an upstream git submodule.
- Do not edit files under `NemoClaw/`.
- Do not edit files under `external/mujoco_menagerie/`.
- Put all project-specific code, skills, docs, and scripts in this repository root outside the submodule.

## Skill Layout

Project agent skills live under `.agents/skills/`.
The current robot skill is:

- `.agents/skills/robot-aloha-mujoco/SKILL.md`

Install it into a running NemoClaw sandbox from the host with:

```bash
scripts/install_robot_skill.sh <sandbox-name>
```

## Common Commands

Generate a task plan and MuJoCo scene without requiring MuJoCo:

```bash
PYTHONPATH=src python3 -m nemoclaw2robot.cli run \
  --prompt "Alohaのアームロボットでキューブを掴んでください" \
  --no-sim
```

Run the same task with MuJoCo installed:

```bash
pip install -e '.[sim]'
PYTHONPATH=src python3 -m nemoclaw2robot.cli run \
  --prompt "Alohaのアームロボットでキューブを掴んでください"
```

Open the native MuJoCo viewer on the host:

```bash
scripts/view_aloha_prompt.sh "Alohaのアームロボットでキューブを掴んでください"
```

The NemoClaw sandbox is headless by default. Use the sandbox for agent/headless runs and the host viewer command for real-time UI.

Run tests:

```bash
python3 -m pytest -q
```

## Implementation Notes

- Prompt parsing is in `src/nemoclaw2robot/prompt.py`.
- Robot metadata is in `src/nemoclaw2robot/robots/aloha.py`.
- MJCF scene generation is in `src/nemoclaw2robot/scene.py`.
- Optional MuJoCo execution is in `src/nemoclaw2robot/simulator.py`.
- Native MuJoCo UI playback is in `src/nemoclaw2robot/viewer.py`.
- End-to-end artifact writing is in `src/nemoclaw2robot/runner.py`.
