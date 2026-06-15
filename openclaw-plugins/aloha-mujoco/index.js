import { execFile } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import http from "node:http";
import https from "node:https";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const DEFAULT_PROJECT_ROOT = "/sandbox/NemoClaw2Robot";
const DEFAULT_TIMEOUT_MS = 180000;
const DEFAULT_LIVE_VIEWER_URL = "http://host.docker.internal:8765";
const MAX_BUFFER_BYTES = 20 * 1024 * 1024;

function readString(value) {
  return typeof value === "string" ? value.trim() : "";
}

function readBoolean(value, fallback) {
  return typeof value === "boolean" ? value : fallback;
}

function readPositiveInteger(value, fallback) {
  return Number.isInteger(value) && value > 0 ? value : fallback;
}

function readNumber(value, fallback) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readPosition(value, name = "position") {
  if (!Array.isArray(value) || value.length !== 3) {
    throw new Error(`${name} must be [x, y, z] in meters`);
  }
  const position = value.map((item) => Number(item));
  if (position.some((item) => !Number.isFinite(item))) {
    throw new Error(`${name} must contain finite numbers`);
  }
  return position;
}

function readRgba(value) {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (!Array.isArray(value) || value.length !== 4) {
    throw new Error("rgba must be [r, g, b, a]");
  }
  const rgba = value.map((item) => Number(item));
  if (rgba.some((item) => !Number.isFinite(item))) {
    throw new Error("rgba must contain finite numbers");
  }
  return rgba;
}

function readNumberArray(value, name) {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`${name} must be a non-empty number array`);
  }
  const numbers = value.map((item) => Number(item));
  if (numbers.some((item) => !Number.isFinite(item))) {
    throw new Error(`${name} must contain finite numbers`);
  }
  return numbers;
}

function readWaypoints(value, name = "waypoints") {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`${name} must be a non-empty list of [x, y, z] waypoints`);
  }
  return value.map((item, index) => readPosition(item, `${name}[${index}]`));
}

function readHand(value) {
  const hand = readString(value) || "right";
  if (!["left", "right"].includes(hand)) {
    throw new Error("hand must be left or right");
  }
  return hand;
}

function resolveProjectRoot(api) {
  const configured = readString(api?.pluginConfig?.projectRoot);
  return configured || DEFAULT_PROJECT_ROOT;
}

function resolveDefaultTimeout(api) {
  return readPositiveInteger(api?.pluginConfig?.timeoutMs, DEFAULT_TIMEOUT_MS);
}

function resolveLiveViewerUrl(api) {
  return (
    readString(api?.pluginConfig?.liveViewerUrl) ||
    readString(process.env.NEMOCLAW2ROBOT_LIVE_VIEWER_URL) ||
    DEFAULT_LIVE_VIEWER_URL
  ).replace(/\/+$/, "");
}

function resolvePython(projectRoot) {
  const venvPython = path.join(projectRoot, ".venv", "bin", "python");
  return existsSync(venvPython) ? venvPython : "python3";
}

function validateRelativeOutput(output) {
  const value = readString(output);
  if (!value) {
    return undefined;
  }
  if (path.isAbsolute(value) || value.split(/[\\/]+/).includes("..")) {
    throw new Error("output must be a relative path under the project root");
  }
  return value;
}

function enqueueLiveRequest(projectRoot, payload) {
  const liveRequestsDir = path.join(projectRoot, "artifacts", "live_requests");
  mkdirSync(liveRequestsDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[-:.]/g, "").replace("T", "T").replace("Z", "Z");
  const suffix = Math.random().toString(16).slice(2, 10);
  const requestPath = path.join(liveRequestsDir, `${stamp}-${suffix}.json`);
  writeFileSync(requestPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return path.relative(projectRoot, requestPath);
}

function isLivePrompt(prompt) {
  const text = readString(prompt).toLowerCase();
  return ["リアルタイム", "ライブ", "見たい", "画面", "ui", "viewer", "live", "watch"].some((word) =>
    text.includes(word),
  );
}

function liveModeForPrompt(prompt) {
  const text = readString(prompt).toLowerCase();
  const controlWords = [
    "cm",
    "センチ",
    "動か",
    "移動",
    "ずら",
    "move",
    "shift",
    "グリッパー",
    "gripper",
    "紙",
    "paper",
    "描",
    "draw",
    "線",
    "line",
    "生成",
    "配置",
    "追加",
    "add",
    "create",
  ];
  return controlWords.some((word) => text.includes(word)) ? "control" : "auto";
}

async function postJson(url, payload, timeoutMs) {
  const endpoint = new URL(url);
  const body = JSON.stringify(payload);
  const client = endpoint.protocol === "https:" ? https : http;

  return await new Promise((resolve, reject) => {
    const request = client.request(
      endpoint,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "content-length": Buffer.byteLength(body),
        },
        timeout: timeoutMs,
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          let json = null;
          try {
            json = text ? JSON.parse(text) : null;
          } catch {
            json = null;
          }
          if ((response.statusCode ?? 500) < 200 || (response.statusCode ?? 500) >= 300) {
            reject(new Error(`HTTP ${response.statusCode}: ${text}`));
            return;
          }
          resolve({ text, json });
        });
      },
    );

    request.on("timeout", () => {
      request.destroy(new Error(`HTTP request timed out after ${timeoutMs}ms`));
    });
    request.on("error", reject);
    request.write(body);
    request.end();
  });
}

function parseStdout(stdout) {
  const text = typeof stdout === "string" ? stdout.trim() : "";
  if (!text) {
    return { text: "", json: null };
  }
  try {
    return { text, json: JSON.parse(text) };
  } catch {
    return { text, json: null };
  }
}

function summarizeRun(json) {
  if (!json || typeof json !== "object") {
    return "ALOHA MuJoCo command completed.";
  }
  const outputDir = typeof json.output_dir === "string" ? json.output_dir : "(unknown)";
  const simulated = json.simulated === true ? "true" : "false";
  const artifacts = Array.isArray(json.artifacts)
    ? json.artifacts.map((artifact) => artifact.path).filter(Boolean)
    : [];
  return [
    `output_dir: ${outputDir}`,
    `simulated: ${simulated}`,
    artifacts.length ? `artifacts:\n${artifacts.map((artifact) => `- ${artifact}`).join("\n")}` : "artifacts: none",
  ].join("\n");
}

function summarizeJson(json) {
  return JSON.stringify(json ?? {}, null, 2);
}

function sessionSummary(json) {
  if (!json || typeof json !== "object") {
    return "ALOHA session command completed.";
  }
  const sessionId = typeof json.session_id === "string" ? json.session_id : "(unknown)";
  const error = Number.isFinite(json.position_error)
    ? `position_error: ${Number(json.position_error).toFixed(4)} m`
    : "";
  const frames = Number.isFinite(json.frames) ? `frames: ${json.frames}` : "";
  return ["session_id: " + sessionId, error, frames].filter(Boolean).join("\n");
}

function promptControlSummary(json) {
  if (!json || typeof json !== "object") {
    return "ALOHA prompt control command completed.";
  }
  const sessionId = typeof json.session_id === "string" ? json.session_id : "(unknown)";
  const plan = json.plan && typeof json.plan === "object" ? json.plan : {};
  const operations = Array.isArray(plan.operations) ? plan.operations : [];
  const operationNames = operations
    .map((operation) => (operation && typeof operation === "object" ? operation.type : "unknown"))
    .filter(Boolean);
  const finalState = json.final_state && typeof json.final_state === "object" ? json.final_state : {};
  const arms = finalState.arms && typeof finalState.arms === "object" ? finalState.arms : {};
  const right = arms.right && typeof arms.right === "object" ? arms.right : undefined;
  const rightPosition = Array.isArray(right?.gripper_position)
    ? `right_gripper: [${right.gripper_position.map((value) => Number(value).toFixed(3)).join(", ")}]`
    : "";
  const scenePath = typeof json.scene_path === "string" ? `scene_path: ${json.scene_path}` : "";
  return [
    `session_id: ${sessionId}`,
    operationNames.length ? `operations: ${operationNames.join(", ")}` : "operations: none",
    rightPosition,
    scenePath,
  ]
    .filter(Boolean)
    .join("\n");
}

async function runCli(projectRoot, cliArgs, timeoutMs) {
  const python = resolvePython(projectRoot);
  try {
    const { stdout, stderr } = await execFileAsync(
      python,
      ["-m", "nemoclaw2robot.cli", ...cliArgs],
      {
        cwd: projectRoot,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
        },
        maxBuffer: MAX_BUFFER_BYTES,
        timeout: timeoutMs,
      },
    );
    const parsed = parseStdout(stdout);
    return {
      ok: true,
      command: [python, "-m", "nemoclaw2robot.cli", ...cliArgs],
      cwd: projectRoot,
      stdout: parsed.text,
      stderr: readString(stderr) || undefined,
      json: parsed.json,
    };
  } catch (error) {
    const parsed = parseStdout(error?.stdout);
    return {
      ok: false,
      command: [python, "-m", "nemoclaw2robot.cli", ...cliArgs],
      cwd: projectRoot,
      exitCode: error?.code,
      signal: error?.signal,
      message: error instanceof Error ? error.message : String(error),
      stdout: parsed.text,
      stderr: readString(error?.stderr) || undefined,
      json: parsed.json,
    };
  }
}

function toolResult(run, fallbackSummary) {
  const text = run.ok
    ? fallbackSummary(run.json)
    : [
        "ALOHA MuJoCo command failed.",
        `cwd: ${run.cwd}`,
        `command: ${run.command.join(" ")}`,
        run.message ? `message: ${run.message}` : "",
        run.stderr ? `stderr:\n${run.stderr}` : "",
        run.stdout ? `stdout:\n${run.stdout}` : "",
      ]
        .filter(Boolean)
        .join("\n");

  return {
    content: [
      {
        type: "text",
        text,
      },
    ],
    details: run,
  };
}

function createPlanTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_mujoco_plan",
    label: "ALOHA MuJoCo Plan",
    description:
      "Parse a Japanese or English ALOHA robot prompt into a normalized NemoClaw2Robot task plan without running MuJoCo.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        prompt: {
          type: "string",
          description: "Robot task prompt, for example: Alohaのアームロボットでキューブを掴んでください",
        },
        timeout_ms: {
          type: "integer",
          minimum: 1000,
          description: "Optional timeout override in milliseconds.",
        },
      },
      required: ["prompt"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const prompt = readString(rawParams.prompt);
      if (!prompt) {
        throw new Error("prompt is required");
      }
      const timeoutMs = readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs);
      const run = await runCli(projectRoot, ["plan", "--prompt", prompt], timeoutMs);
      return toolResult(run, (json) => JSON.stringify(json ?? run.stdout, null, 2));
    },
  };
}

function createRunTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_mujoco_run",
    label: "ALOHA MuJoCo Run",
    description:
      "Build the official ALOHA MuJoCo scene from a prompt and run the scripted NemoClaw2Robot controller, writing plan, scene, trajectory, and summary artifacts.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        prompt: {
          type: "string",
          description: "Robot task prompt, for example: Alohaのアームロボットでキューブを掴んでください",
        },
        simulate: {
          type: "boolean",
          default: true,
          description: "When false, only write plan and scene artifacts.",
        },
        strict_sim: {
          type: "boolean",
          default: false,
          description: "When true, fail if MuJoCo cannot run.",
        },
        output: {
          type: "string",
          description: "Optional relative output directory under the project root, such as artifacts/runs/agent-grasp.",
        },
        timeout_ms: {
          type: "integer",
          minimum: 1000,
          description: "Optional timeout override in milliseconds.",
        },
      },
      required: ["prompt"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const prompt = readString(rawParams.prompt);
      if (!prompt) {
        throw new Error("prompt is required");
      }
      const args = ["run", "--prompt", prompt];
      if (!readBoolean(rawParams.simulate, true)) {
        args.push("--no-sim");
      }
      if (readBoolean(rawParams.strict_sim, false)) {
        args.push("--strict-sim");
      }
      const output = validateRelativeOutput(rawParams.output);
      if (output) {
        args.push("--output", output);
      }
      const timeoutMs = readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs);
      const run = await runCli(projectRoot, args, timeoutMs);
      return toolResult(run, summarizeRun);
    },
  };
}

function createLiveTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  const defaultLiveViewerUrl = resolveLiveViewerUrl(api);
  return {
    name: "aloha_mujoco_live",
    label: "ALOHA MuJoCo Live Viewer",
    description:
      "Queue an ALOHA robot prompt for the host-side live MuJoCo viewer watcher so the user can watch the robot move in a native viewer window.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        prompt: {
          type: "string",
          description: "Robot task prompt, for example: Alohaのアームロボットで球体を掴んでください",
        },
        live_viewer_url: {
          type: "string",
          description: "Optional host live viewer URL used only when delivery is http.",
        },
        delivery: {
          type: "string",
          enum: ["queue", "http"],
          default: "queue",
          description:
            "queue writes a sandbox live request for the host watcher. http posts directly to the live viewer bridge.",
        },
        mode: {
          type: "string",
          enum: ["auto", "demo", "control"],
          default: "auto",
          description:
            "auto lets the host watcher choose fixed demo or prompt-control playback. control forces session-based prompt-control playback.",
        },
        timeout_ms: {
          type: "integer",
          minimum: 1000,
          description: "Optional timeout override in milliseconds.",
        },
      },
      required: ["prompt"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const prompt = readString(rawParams.prompt);
      if (!prompt) {
        throw new Error("prompt is required");
      }
      const delivery = readString(rawParams.delivery) || "queue";
      if (delivery !== "http") {
        const mode = readString(rawParams.mode) || "auto";
        const queuedPath = enqueueLiveRequest(projectRoot, {
          prompt,
          robot: "aloha",
          mode,
          created_at: new Date().toISOString(),
          requested_by: "aloha_mujoco_live",
        });
        return {
          content: [
            {
              type: "text",
              text: [
                "live_viewer: queued",
                `request: ${queuedPath}`,
                "Start the host watcher if no MuJoCo window appears: scripts/live_aloha_agent_viewer.sh mujoco-agent-robot",
              ].join("\n"),
            },
          ],
          details: {
            ok: true,
            queued: true,
            requestPath: queuedPath,
          },
        };
      }
      const liveViewerUrl = (readString(rawParams.live_viewer_url) || defaultLiveViewerUrl).replace(/\/+$/, "");
      const timeoutMs = readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs);
      const mode = readString(rawParams.mode) || "auto";
      const { json, text } = await postJson(
        `${liveViewerUrl}/prompt`,
        {
          prompt,
          robot: "aloha",
          mode,
          timeout_seconds: Math.max(1, Math.ceil(timeoutMs / 1000)),
        },
        timeoutMs,
      );
      const result = json && typeof json === "object" ? json.result : null;
      const task = result && typeof result === "object" ? result.task : null;
      const frames = result && typeof result === "object" ? result.frames : null;
      const objectName = task && typeof task === "object" ? task.object_name : undefined;
      return {
        content: [
          {
            type: "text",
            text: [
              "live_viewer: true",
              `viewer_url: ${liveViewerUrl}`,
              objectName ? `object: ${objectName}` : "",
              Number.isFinite(frames) ? `frames: ${frames}` : "",
            ]
              .filter(Boolean)
              .join("\n"),
          },
        ],
        details: {
          ok: true,
          liveViewerUrl,
          response: json ?? text,
        },
      };
    },
  };
}

function createPromptControlTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_prompt_control",
    label: "ALOHA Prompt Control",
    description:
      "Execute a natural-language ALOHA MuJoCo control prompt through session primitives. Use this for relative movement, gripper commands, object creation, paper placement, and drawing-style demos.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        prompt: {
          type: "string",
          description: "Full user prompt, for example: 右アームを右に10cm動かしてください",
        },
        session_id: {
          type: "string",
          description: "Optional stable session id. When omitted, a new session is created.",
        },
        steps: {
          type: "integer",
          minimum: 1,
          default: 30,
          description: "Default interpolation steps for generated motion primitives.",
        },
        timeout_ms: timeoutProperty(),
      },
      required: ["prompt"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const prompt = readString(rawParams.prompt);
      if (!prompt) {
        throw new Error("prompt is required");
      }
      const args = [
        "prompt-control",
        "--prompt",
        prompt,
        "--steps",
        String(readPositiveInteger(rawParams.steps, 30)),
      ];
      const sessionId = readString(rawParams.session_id);
      if (sessionId) {
        args.push("--session-id", sessionId);
      }
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      const result = toolResult(run, promptControlSummary);
      if (run.ok && isLivePrompt(prompt)) {
        const mode = liveModeForPrompt(prompt);
        const queuedPath = enqueueLiveRequest(projectRoot, {
          prompt,
          robot: "aloha",
          mode,
          created_at: new Date().toISOString(),
          requested_by: "aloha_prompt_control",
        });
        result.content[0].text = [
          result.content[0].text,
          "live_viewer: queued",
          `request: ${queuedPath}`,
          `mode: ${mode}`,
          "Start the host watcher if no MuJoCo window appears: scripts/live_aloha_agent_viewer.sh mujoco-agent-robot",
        ].join("\n");
        result.details.liveQueued = true;
        result.details.liveRequestPath = queuedPath;
        result.details.liveMode = mode;
      }
      return result;
    },
  };
}

function createSessionStartTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_session_start",
    label: "ALOHA Session Start",
    description:
      "Create a persistent ALOHA MuJoCo session for multi-step Agent planning. Use this before state/IK/motion tools.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        prompt: {
          type: "string",
          description: "Initial task or scene prompt.",
        },
        session_id: {
          type: "string",
          description: "Optional stable session id.",
        },
        timeout_ms: {
          type: "integer",
          minimum: 1000,
        },
      },
      required: ["prompt"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const prompt = readString(rawParams.prompt);
      if (!prompt) {
        throw new Error("prompt is required");
      }
      const args = ["session-start", "--prompt", prompt];
      const sessionId = readString(rawParams.session_id);
      if (sessionId) {
        args.push("--session-id", sessionId);
      }
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, (json) => {
        const id = json && typeof json === "object" ? json.session_id : undefined;
        return id ? `session_id: ${id}\nUse this id for the next ALOHA planning tools.` : summarizeJson(json);
      });
    },
  };
}

function createSessionStateTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_get_state",
    label: "ALOHA Get State",
    description: "Read persistent session robot qpos, gripper poses, object poses, and current contacts.",
    parameters: sessionIdParameters(),
    execute: async (_toolCallId, rawParams = {}) => {
      const run = await runCli(
        projectRoot,
        ["session-state", "--session-id", requiredSessionId(rawParams)],
        readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs),
      );
      return toolResult(run, summarizeJson);
    },
  };
}

function createSolveIkTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_solve_ik",
    label: "ALOHA Solve IK",
    description:
      "Solve position IK for an ALOHA gripper site. This computes joint qpos for a target position; it does not verify grasp success.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...sessionIdProperties(),
        hand: handProperty(),
        position: positionProperty("Target gripper position [x, y, z] in meters."),
        save: {
          type: "boolean",
          default: false,
          description: "When true, save the solved qpos into the session.",
        },
        timeout_ms: timeoutProperty(),
      },
      required: ["session_id", "position"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const args = [
        "session-ik",
        "--session-id",
        requiredSessionId(rawParams),
        "--hand",
        readHand(rawParams.hand),
        "--position",
        ...readPosition(rawParams.position).map(String),
      ];
      if (readBoolean(rawParams.save, false)) {
        args.push("--save");
      }
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, sessionSummary);
    },
  };
}

function createMoveRelativeTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_move_relative",
    label: "ALOHA Move Relative",
    description:
      "Move a gripper by a world-frame delta. ALOHA frame: x forward, y left, z up; moving right is negative y.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...sessionIdProperties(),
        hand: handProperty(),
        direction: {
          type: "string",
          enum: ["left", "right", "forward", "back", "up", "down"],
          description: "Optional semantic direction. Can be combined with dx/dy/dz.",
        },
        distance_m: {
          type: "number",
          description: "Distance for semantic direction in meters.",
        },
        distance_cm: {
          type: "number",
          description: "Distance for semantic direction in centimeters.",
        },
        dx: { type: "number", default: 0 },
        dy: { type: "number", default: 0 },
        dz: { type: "number", default: 0 },
        dx_cm: { type: "number", default: 0 },
        dy_cm: { type: "number", default: 0 },
        dz_cm: { type: "number", default: 0 },
        steps: { type: "integer", minimum: 1, default: 30 },
        timeout_ms: timeoutProperty(),
      },
      required: ["session_id"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const delta = relativeDelta(rawParams);
      const args = [
        "session-move-relative",
        "--session-id",
        requiredSessionId(rawParams),
        "--hand",
        readHand(rawParams.hand),
        "--dx",
        String(delta[0]),
        "--dy",
        String(delta[1]),
        "--dz",
        String(delta[2]),
        "--steps",
        String(readPositiveInteger(rawParams.steps, 30)),
      ];
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, sessionSummary);
    },
  };
}

function createMoveToTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_move_to_pose",
    label: "ALOHA Move To Pose",
    description: "Move a gripper to a target world-frame position using the project IK scaffold.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...sessionIdProperties(),
        hand: handProperty(),
        position: positionProperty("Target gripper position [x, y, z] in meters."),
        steps: { type: "integer", minimum: 1, default: 30 },
        timeout_ms: timeoutProperty(),
      },
      required: ["session_id", "position"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const args = [
        "session-move-to",
        "--session-id",
        requiredSessionId(rawParams),
        "--hand",
        readHand(rawParams.hand),
        "--position",
        ...readPosition(rawParams.position).map(String),
        "--steps",
        String(readPositiveInteger(rawParams.steps, 30)),
      ];
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, sessionSummary);
    },
  };
}

function createCartesianPathTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_execute_cartesian_path",
    label: "ALOHA Execute Cartesian Path",
    description: "Execute a list of gripper waypoints for drawing or multi-step motion demos.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...sessionIdProperties(),
        hand: handProperty(),
        waypoints: {
          type: "array",
          items: {
            type: "array",
            minItems: 3,
            maxItems: 3,
            items: { type: "number" },
          },
        },
        steps_per_waypoint: { type: "integer", minimum: 1, default: 20 },
        timeout_ms: timeoutProperty(),
      },
      required: ["session_id", "waypoints"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const args = [
        "session-cartesian-path",
        "--session-id",
        requiredSessionId(rawParams),
        "--hand",
        readHand(rawParams.hand),
        "--waypoints-json",
        JSON.stringify(readWaypoints(rawParams.waypoints)),
        "--steps-per-waypoint",
        String(readPositiveInteger(rawParams.steps_per_waypoint, 20)),
      ];
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, sessionSummary);
    },
  };
}

function createGripperTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_set_gripper",
    label: "ALOHA Set Gripper",
    description: "Open or close an ALOHA gripper by setting its finger opening in meters.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...sessionIdProperties(),
        hand: handProperty(),
        action: {
          type: "string",
          enum: ["open", "close"],
          description: "Optional shortcut. open=0.037m, close=0.002m.",
        },
        opening: {
          type: "number",
          description: "Finger opening in meters. Overrides action when provided.",
        },
        steps: { type: "integer", minimum: 1, default: 12 },
        timeout_ms: timeoutProperty(),
      },
      required: ["session_id"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const action = readString(rawParams.action);
      const opening = readNumber(rawParams.opening, action === "close" ? 0.002 : 0.037);
      const args = [
        "session-gripper",
        "--session-id",
        requiredSessionId(rawParams),
        "--hand",
        readHand(rawParams.hand),
        "--opening",
        String(opening),
        "--steps",
        String(readPositiveInteger(rawParams.steps, 12)),
      ];
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, sessionSummary);
    },
  };
}

function createAddObjectTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_add_object",
    label: "ALOHA Add Object",
    description: "Add cube, sphere, cylinder, paper, or marker primitives to the persistent session scene.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...sessionIdProperties(),
        name: { type: "string" },
        kind: { type: "string", enum: ["cube", "sphere", "cylinder", "paper", "marker"] },
        position: positionProperty("Object center position [x, y, z] in meters."),
        size: {
          type: "array",
          items: { type: "number" },
          description: "Optional MuJoCo geom size tuple.",
        },
        rgba: {
          type: "array",
          minItems: 4,
          maxItems: 4,
          items: { type: "number" },
        },
        fixed: { type: "boolean" },
        timeout_ms: timeoutProperty(),
      },
      required: ["session_id", "name", "kind", "position"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const args = [
        "session-add-object",
        "--session-id",
        requiredSessionId(rawParams),
        "--name",
        readString(rawParams.name),
        "--kind",
        readString(rawParams.kind),
        "--position",
        ...readPosition(rawParams.position).map(String),
      ];
      const size = readNumberArray(rawParams.size, "size");
      if (size) {
        args.push("--size", ...size.map(String));
      }
      const rgba = readRgba(rawParams.rgba);
      if (rgba) {
        args.push("--rgba", ...rgba.map(String));
      }
      if (readBoolean(rawParams.fixed, false)) {
        args.push("--fixed");
      }
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, summarizeJson);
    },
  };
}

function createAddTraceTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_add_trace",
    label: "ALOHA Add Trace",
    description:
      "Add visual non-colliding capsule traces to the scene. Useful for drawing demos after executing waypoints.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...sessionIdProperties(),
        points: {
          type: "array",
          items: {
            type: "array",
            minItems: 3,
            maxItems: 3,
            items: { type: "number" },
          },
        },
        name_prefix: { type: "string", default: "trace" },
        radius: { type: "number", default: 0.004 },
        rgba: {
          type: "array",
          minItems: 4,
          maxItems: 4,
          items: { type: "number" },
        },
        timeout_ms: timeoutProperty(),
      },
      required: ["session_id", "points"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const args = [
        "session-add-trace",
        "--session-id",
        requiredSessionId(rawParams),
        "--points-json",
        JSON.stringify(readWaypoints(rawParams.points, "points")),
        "--name-prefix",
        readString(rawParams.name_prefix) || "trace",
        "--radius",
        String(readNumber(rawParams.radius, 0.004)),
      ];
      const rgba = readRgba(rawParams.rgba) ?? [0.05, 0.05, 0.05, 1.0];
      args.push("--rgba", ...rgba.map(String));
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, summarizeJson);
    },
  };
}

function createCheckPoseTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_check_pose",
    label: "ALOHA Check Pose",
    description: "Check current gripper pose, optionally against an expected position and tolerance.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...sessionIdProperties(),
        hand: handProperty(),
        expected_position: positionProperty("Optional expected position [x, y, z] in meters."),
        tolerance: { type: "number", default: 0.02 },
        timeout_ms: timeoutProperty(),
      },
      required: ["session_id"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const args = [
        "session-check-pose",
        "--session-id",
        requiredSessionId(rawParams),
        "--hand",
        readHand(rawParams.hand),
        "--tolerance",
        String(readNumber(rawParams.tolerance, 0.02)),
      ];
      if (rawParams.expected_position !== undefined) {
        args.push("--expected-position", ...readPosition(rawParams.expected_position, "expected_position").map(String));
      }
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, summarizeJson);
    },
  };
}

function createCheckContactsTool(api) {
  const projectRoot = resolveProjectRoot(api);
  const defaultTimeoutMs = resolveDefaultTimeout(api);
  return {
    name: "aloha_check_contacts",
    label: "ALOHA Check Contacts",
    description: "Read current MuJoCo contacts, optionally filtered by an object name.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...sessionIdProperties(),
        object_name: { type: "string" },
        timeout_ms: timeoutProperty(),
      },
      required: ["session_id"],
    },
    execute: async (_toolCallId, rawParams = {}) => {
      const args = ["session-check-contacts", "--session-id", requiredSessionId(rawParams)];
      const objectName = readString(rawParams.object_name);
      if (objectName) {
        args.push("--object-name", objectName);
      }
      const run = await runCli(projectRoot, args, readPositiveInteger(rawParams.timeout_ms, defaultTimeoutMs));
      return toolResult(run, summarizeJson);
    },
  };
}

function sessionIdProperties() {
  return {
    session_id: {
      type: "string",
      description: "Persistent session id returned by aloha_session_start.",
    },
  };
}

function sessionIdParameters() {
  return {
    type: "object",
    additionalProperties: false,
    properties: {
      ...sessionIdProperties(),
      timeout_ms: timeoutProperty(),
    },
    required: ["session_id"],
  };
}

function requiredSessionId(rawParams) {
  const sessionId = readString(rawParams.session_id);
  if (!sessionId) {
    throw new Error("session_id is required");
  }
  return sessionId;
}

function handProperty() {
  return {
    type: "string",
    enum: ["left", "right"],
    default: "right",
  };
}

function positionProperty(description) {
  return {
    type: "array",
    minItems: 3,
    maxItems: 3,
    items: { type: "number" },
    description,
  };
}

function timeoutProperty() {
  return {
    type: "integer",
    minimum: 1000,
    description: "Optional timeout override in milliseconds.",
  };
}

function relativeDelta(rawParams) {
  const delta = [
    readNumber(rawParams.dx, 0) + readNumber(rawParams.dx_cm, 0) / 100,
    readNumber(rawParams.dy, 0) + readNumber(rawParams.dy_cm, 0) / 100,
    readNumber(rawParams.dz, 0) + readNumber(rawParams.dz_cm, 0) / 100,
  ];
  const direction = readString(rawParams.direction);
  if (direction) {
    const distance = readNumber(rawParams.distance_m, readNumber(rawParams.distance_cm, 0) / 100);
    if (!Number.isFinite(distance) || distance <= 0) {
      throw new Error("distance_m or distance_cm must be positive when direction is set");
    }
    const directionDelta = {
      left: [0, distance, 0],
      right: [0, -distance, 0],
      forward: [distance, 0, 0],
      back: [-distance, 0, 0],
      up: [0, 0, distance],
      down: [0, 0, -distance],
    }[direction];
    if (!directionDelta) {
      throw new Error(`unsupported direction: ${direction}`);
    }
    delta[0] += directionDelta[0];
    delta[1] += directionDelta[1];
    delta[2] += directionDelta[2];
  }
  return delta;
}

export default {
  id: "aloha-mujoco",
  name: "ALOHA MuJoCo Robot Tools",
  description: "OpenClaw tools for NemoClaw2Robot ALOHA MuJoCo prompt tasks and multi-step Agent planning.",
  configSchema: {
    type: "object",
    additionalProperties: false,
    properties: {
      projectRoot: {
        type: "string",
        default: DEFAULT_PROJECT_ROOT,
      },
      timeoutMs: {
        type: "integer",
        minimum: 1000,
        default: DEFAULT_TIMEOUT_MS,
      },
      liveViewerUrl: {
        type: "string",
        default: DEFAULT_LIVE_VIEWER_URL,
      },
    },
  },
  register(api) {
    api.registerTool(createPlanTool(api));
    api.registerTool(createRunTool(api));
    api.registerTool(createLiveTool(api));
    api.registerTool(createPromptControlTool(api));
    api.registerTool(createSessionStartTool(api));
    api.registerTool(createSessionStateTool(api));
    api.registerTool(createSolveIkTool(api));
    api.registerTool(createMoveRelativeTool(api));
    api.registerTool(createMoveToTool(api));
    api.registerTool(createCartesianPathTool(api));
    api.registerTool(createGripperTool(api));
    api.registerTool(createAddObjectTool(api));
    api.registerTool(createAddTraceTool(api));
    api.registerTool(createCheckPoseTool(api));
    api.registerTool(createCheckContactsTool(api));
    api.logger.info(`ALOHA MuJoCo tools registered for ${resolveProjectRoot(api)}`);
  },
};
