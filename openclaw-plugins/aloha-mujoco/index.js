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
        const queuedPath = enqueueLiveRequest(projectRoot, {
          prompt,
          robot: "aloha",
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
      const { json, text } = await postJson(
        `${liveViewerUrl}/prompt`,
        {
          prompt,
          robot: "aloha",
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

export default {
  id: "aloha-mujoco",
  name: "ALOHA MuJoCo Robot Tools",
  description: "OpenClaw tools for NemoClaw2Robot ALOHA MuJoCo prompt tasks.",
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
    api.logger.info(`ALOHA MuJoCo tools registered for ${resolveProjectRoot(api)}`);
  },
};
