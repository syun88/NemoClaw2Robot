---
name: "robot-aloha-mujoco"
description: "Use this for ALOHA arm robot MuJoCo tasks. Do not only explain. If prompt says realtime/live/UI/見たい/画面, call openclaw.tools.call(\"aloha_mujoco_live\", {prompt:\"<full user prompt>\", mode:\"control\"}) for movement/object/drawing prompts, or mode:\"auto\" for fixed grasp/place/push demos. Otherwise call aloha_prompt_control for natural control prompts. Never use openclaw.tools[\"robot-aloha-mujoco\"] or bare aloha_*() calls."
license: "Apache-2.0"
---

# ALOHA MuJoCo Robot Skill

Use this skill for prompts such as:

- "Alohaのアームロボットでキューブを掴んでください"
- "Alohaのアームロボットで球体を掴んでください"
- "Use the ALOHA robot arm to pick up the cube."
- "Alohaでキューブを目標位置に置いてください"
- "リアルタイムでAlohaがキューブを掴むところを見たい"
- "右アームを右に10cm動かしてください"
- "紙を置いて簡単な線を描いてください"

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

- If the user asks to watch the robot in real time, live, UI, 画面, or 見たい, first call the OpenClaw tool `aloha_mujoco_live`.
- For live relative movement, gripper, object, paper, or drawing prompts, call `aloha_mujoco_live` with `mode: "control"`.
- For live fixed grasp/place/push demos, call `aloha_mujoco_live` with `mode: "auto"` or omit `mode`.
- If the prompt is not a live/viewer request and asks the ALOHA arm to move, open/close the gripper, create an object, place paper, draw a line, or perform any broad control instruction, call the OpenClaw tool `aloha_prompt_control` with the full user prompt.
- If the user asks for a fixed grasp/place/push artifact run, use `aloha_mujoco_run`.
- Use the low-level session tools only when `aloha_prompt_control` is unavailable or when the user explicitly asks you to debug/compose primitives:
  - `aloha_session_start`
  - `aloha_get_state`
  - `aloha_solve_ik`
  - `aloha_move_relative`
  - `aloha_move_to_pose`
  - `aloha_execute_cartesian_path`
  - `aloha_set_gripper`
  - `aloha_add_object`
  - `aloha_add_trace`
  - `aloha_check_pose`
  - `aloha_check_contacts`
- Call `aloha_prompt_control` with JSON parameters such as:

  ```json
  {
    "prompt": "右アームを右に10cm動かしてください"
  }
  ```

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
- If only the compact `tool_search_code` tool is available and the user asks for live/realtime/viewer, use exactly this JavaScript pattern:

  ```javascript
  return await openclaw.tools.call("aloha_mujoco_live", {
    prompt: "リアルタイムで右アームを右に10cm動かしてください",
    mode: "control"
  });
  ```

  For non-live natural control requests, use:

  ```javascript
  return await openclaw.tools.call("aloha_prompt_control", {
    prompt: "右アームを右に10cm動かしてください"
  });
  ```

  For a fixed grasp/place/push artifact request, use:

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

  For a live relative/control request, use:

  ```javascript
  return await openclaw.tools.call("aloha_mujoco_live", {
    prompt: "リアルタイムで右アームを右に10cm動かしてください",
    mode: "control"
  });
  ```

  For a multi-step planning request, use a tool chain like:

  ```javascript
  const session = await openclaw.tools.call("aloha_session_start", {
    prompt: "Alohaの右アームを右に10cm動かしてください"
  });
  const sessionId = session.details?.json?.session_id;
  await openclaw.tools.call("aloha_get_state", { session_id: sessionId });
  await openclaw.tools.call("aloha_move_relative", {
    session_id: sessionId,
    hand: "right",
    direction: "right",
    distance_cm: 10
  });
  return await openclaw.tools.call("aloha_check_pose", { session_id: sessionId, hand: "right" });
  ```

  The compact bridge only exposes `openclaw.tools.search(query)`, `openclaw.tools.describe(id)`, and `openclaw.tools.call(id, args)`.
- Do not write `aloha_prompt_control(...)`, `aloha_session_start(...)`, or any ALOHA tool name as a bare JavaScript function. Always use `openclaw.tools.call("tool_name", args)`.
- If the OpenClaw tool is unavailable, execute the command below through the available shell/terminal mechanism.
- If the only available execution tool is JavaScript code evaluation, run the shell command with Node's `child_process.execFileSync`.
- Do not call `openclaw.tools.run_skill`; that API does not exist in this TUI bridge.

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

- `grasp`: approach the cube or sphere, open/close the gripper, and play a scripted object-follow sequence.
- `place`: approach the cube or sphere, open/close the gripper, and play a scripted transfer-style sequence to the target pad.
- `push`: approach the cube or sphere and push it along the table lane.
- `inspect`: generate the scene and inspect object positions.

Current control scope: the project controller opens/closes the official ALOHA gripper joints and plays a deterministic motion sequence. It is not yet a learned policy or a pure contact-physics grasp; after the close phase, object movement is scripted and should not be described as a verified successful physical grasp.

## Planner Tool Scope

For broad user prompts, the Agent should plan using tools instead of pretending a fixed task exists.
Recommended flow:

1. Start or reuse a session with `aloha_session_start`.
2. Inspect state with `aloha_get_state`.
3. Add simple scene assets with `aloha_add_object` when needed.
4. Convert natural-language movement into world-frame targets. ALOHA frame is x forward, y left, z up; "right 10 cm" is `direction: "right", distance_cm: 10`.
5. Use `aloha_solve_ik`, `aloha_move_relative`, `aloha_move_to_pose`, or `aloha_execute_cartesian_path`.
6. Use `aloha_set_gripper` for open/close commands.
7. Use `aloha_check_pose` and `aloha_check_contacts` to verify results before reporting.
8. For drawing demos, add a fixed `paper` object, execute a Cartesian path above/on the paper, then use `aloha_add_trace` to visualize the intended drawn path.

Do not claim robust physical grasping or drawing with real ink. The session tools provide MuJoCo planning/control scaffolding and visual motion demos.

## Installation Into NemoClaw

From the host, install this skill into a running sandbox:

```bash
scripts/install_robot_skill.sh <sandbox-name>
```

The installer uploads the project runtime to `/sandbox/NemoClaw2Robot`, creates `/sandbox/NemoClaw2Robot/.venv`, and installs the project-side OpenClaw plugin `aloha-mujoco`.
After installation, the OpenClaw agent should satisfy control prompts by calling `aloha_prompt_control`, fixed artifact prompts by calling `aloha_mujoco_run`, and live/watch prompts by calling `aloha_mujoco_live`.
