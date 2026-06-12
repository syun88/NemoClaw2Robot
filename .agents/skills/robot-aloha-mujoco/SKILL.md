---
name: "robot-aloha-mujoco"
description: "Use this for ALOHA arm robot MuJoCo cube/sphere tasks. Do not only explain. If the user asks to watch in real time/live/UI/画面/見たい, call tool_search_code with JavaScript: return await openclaw.tools.call(\"aloha_mujoco_live\", { prompt: <the user's full prompt> }); otherwise call aloha_mujoco_run with simulate true. Do not call openclaw.tools.run_skill, readSkill, runSkill, openclaw.skills.spawn, or fake skill APIs."
license: "Apache-2.0"
---

# ALOHA MuJoCo Robot Skill

Use this skill for prompts such as:

- "Alohaのアームロボットでキューブを掴んでください"
- "Alohaのアームロボットで球体を掴んでください"
- "Use the ALOHA robot arm to pick up the cube."
- "Alohaでキューブを目標位置に置いてください"
- "リアルタイムでAlohaがキューブを掴むところを見たい"

## Required Context

Read `references/robot_aloha.md` before acting.

## Repository Boundary

- Do not edit `NemoClaw/`; it is an upstream submodule.
- Do not edit `external/mujoco_menagerie/`; it is an upstream submodule containing the official ALOHA MJCF.
- Use project files outside the submodule only.
- Write run outputs under `artifacts/runs/`.

## Procedure

Execution contract:

- When the user asks for an ALOHA MuJoCo task, run the command; do not only describe that you can run it.
- Keep the response language aligned with the user's prompt. If the prompt is Japanese, report in Japanese.
- First execute the shell command, then summarize `output_dir`, `simulated`, and artifact paths from the JSON result.
- If no shell/terminal tool is available, explicitly say that execution cannot be performed from the current TUI session and provide the exact command to run.

OpenClaw execution note:

- If the user asks to watch the robot in real time, live, UI, 画面, or 見たい, prefer the OpenClaw tool `aloha_mujoco_live`.
- Otherwise prefer the OpenClaw tool `aloha_mujoco_run` when it is available.
- Call `aloha_mujoco_run` with JSON parameters such as:

  ```json
  {
    "prompt": "Alohaのアームロボットでキューブを掴んでください",
    "simulate": true,
    "strict_sim": true
  }
  ```

- Use `aloha_mujoco_plan` when you only need to parse the prompt before execution.
- `aloha_mujoco_live` requires the host-side Agent viewer watcher to be running on the Mac:

  ```bash
  scripts/live_aloha_agent_viewer.sh mujoco-agent-robot
  ```

- This skill is instruction context, not a JavaScript API.
- Do not try to read `~/.openclaw/skills/robot-aloha-mujoco/SKILL.md` from inside the TUI; this file is already the instruction context.
- Do not call `openclaw.skills["robot-aloha-mujoco"]`, `.task(...)`, or `.execute(...)`.
- Do not call `openclaw.tools.read`, `openclaw.tools.readSkill`, `openclaw.tools.execute`, or `openclaw.tools.runSkill`; these APIs do not exist.
- Do not write `cd /path` as JavaScript code.
- If only the compact `tool_search_code` tool is available, use exactly this JavaScript pattern:

  ```javascript
  return await openclaw.tools.call("aloha_mujoco_run", {
    prompt: "Alohaのアームロボットでキューブを掴んでください",
    simulate: true,
    strict_sim: true
  });
  ```

  For a live viewer request, use:

  ```javascript
  return await openclaw.tools.call("aloha_mujoco_live", {
    prompt: "リアルタイムでAlohaのアームロボットが球体を掴むところを見たい"
  });
  ```

  The compact bridge only exposes `openclaw.tools.search(query)`, `openclaw.tools.describe(id)`, and `openclaw.tools.call(id, args)`.
- If the OpenClaw tool is unavailable, execute the command below through the available shell/terminal mechanism.
- If the only available execution tool is JavaScript code evaluation, run the shell command with Node's `child_process.execFileSync`.

1. Parse the user prompt into a robot task:

   ```bash
   cd /sandbox/NemoClaw2Robot
   .venv/bin/python -m nemoclaw2robot.cli plan --prompt "<prompt>"
   ```

2. Build the MuJoCo scene and run the controller when MuJoCo is installed:

   ```bash
   cd /sandbox/NemoClaw2Robot
   .venv/bin/python -m nemoclaw2robot.cli run --prompt "<prompt>"
   ```

   If using a JavaScript execution tool, use this exact pattern:

   ```javascript
   const { execFileSync } = require("node:child_process");
   const output = execFileSync(
     "bash",
     [
       "-lc",
       'cd /sandbox/NemoClaw2Robot && .venv/bin/python -m nemoclaw2robot.cli run --prompt "Alohaのアームロボットでキューブを掴んでください"',
     ],
     { encoding: "utf8" },
   );
   console.log(output);
   ```

3. If MuJoCo is not installed in the current environment, still build the plan and scene:

   ```bash
   cd /sandbox/NemoClaw2Robot
   PYTHONPATH=src python3 -m nemoclaw2robot.cli run --prompt "<prompt>" --no-sim
   ```

4. Report the created artifact directory and summarize whether MuJoCo simulation actually ran.

## Real-Time UI

The NemoClaw/OpenClaw sandbox is headless by default, so native MuJoCo windows must be opened on the host machine.
For Agent-controlled live UI, tell the user to run this from the host repository checkout and keep it running:

```bash
scripts/live_aloha_agent_viewer.sh mujoco-agent-robot
```

Then call `aloha_mujoco_live` from the OpenClaw agent. The tool queues the prompt under `/sandbox/NemoClaw2Robot/artifacts/live_requests/`, and the host watcher picks it up through `openshell sandbox exec` before opening the native MuJoCo viewer.

The HTTP bridge is still available for environments where direct sandbox-to-host POST is allowed:

```bash
scripts/live_aloha_viewer.sh
```

For a one-off local playback without NemoClaw Agent control, run:

```bash
scripts/view_aloha_prompt.sh "Alohaのアームロボットでキューブを掴んでください"
```

Equivalent direct command on macOS:

```bash
.venv/bin/mjpython -m nemoclaw2robot.cli view --prompt "Alohaのアームロボットでキューブを掴んでください"
```

Use sandbox `run` for headless artifact generation, host `live-agent` for Agent-controlled visual playback, host `live` for optional direct HTTP bridge mode, and host `view` for one-off local playback.

## Supported First Tasks

- `grasp`: approach the cube or sphere, close around it, and lift it.
- `place`: grasp the cube or sphere, lift it, and move it to the target pad.
- `push`: approach the cube or sphere and push it along the table lane.
- `inspect`: generate the scene and inspect object positions.

Current control scope: the project controller opens/closes the official ALOHA gripper joints and plays a deterministic task sequence. It is not yet a learned policy or a pure contact-physics grasp; after the close phase, cube lift/transfer is scripted.

## Installation Into NemoClaw

From the host, install this skill into a running sandbox:

```bash
scripts/install_robot_skill.sh <sandbox-name>
```

The installer uploads the project runtime to `/sandbox/NemoClaw2Robot`, creates `/sandbox/NemoClaw2Robot/.venv`, and installs the project-side OpenClaw plugin `aloha-mujoco`.
After installation, the OpenClaw agent should satisfy normal robot prompts by calling `aloha_mujoco_run`, and live/watch prompts by calling `aloha_mujoco_live`.
