from __future__ import annotations

import json
import queue
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import numpy as np

from nemoclaw2robot.models import TaskSpec
from nemoclaw2robot.prompt import parse_prompt
from nemoclaw2robot.scene import build_scene_xml
from nemoclaw2robot.simulator import AlohaMujocoController, TrajectoryFrame
from nemoclaw2robot.viewer import ViewerClosed, _configure_viewer_camera, _select_camera


@dataclass
class LiveRequest:
    prompt: str
    robot: str
    timeout_seconds: float
    mode: str
    event: threading.Event
    result: dict[str, object] | None = None
    error: str | None = None


class LiveViewerBridge:
    """Host-side bridge that lets a sandbox OpenClaw tool drive a MuJoCo viewer."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        fps: float = 30.0,
        camera: str | None = "teleoperator_pov",
        hold_seconds: float = 4.0,
    ) -> None:
        if fps <= 0:
            raise ValueError("fps must be greater than zero")
        if hold_seconds < 0:
            raise ValueError("hold_seconds must be non-negative")

        self.host = host
        self.port = port
        self.fps = fps
        self.camera = camera
        self.hold_seconds = hold_seconds
        self._requests: queue.Queue[LiveRequest | None] = queue.Queue()
        self._server: ThreadingHTTPServer | None = None

    def serve_forever(self) -> None:
        handler = self._make_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        server_thread.start()
        print(
            json.dumps(
                {
                    "live_viewer": "ready",
                    "host": self.host,
                    "port": self.port,
                    "endpoint": f"http://{self.host}:{self.port}/prompt",
                    "sandbox_endpoint": f"http://host.docker.internal:{self.port}/prompt",
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        try:
            self._viewer_loop()
        finally:
            self._server.shutdown()
            self._server.server_close()

    def submit(
        self,
        prompt: str,
        *,
        robot: str = "aloha",
        timeout_seconds: float = 300.0,
        mode: str = "auto",
    ) -> dict[str, object]:
        request = LiveRequest(
            prompt=prompt,
            robot=robot,
            timeout_seconds=timeout_seconds,
            mode=mode,
            event=threading.Event(),
        )
        self._requests.put(request)
        if not request.event.wait(timeout_seconds):
            raise TimeoutError(f"live viewer request timed out after {timeout_seconds:g}s")
        if request.error is not None:
            raise RuntimeError(request.error)
        if request.result is None:
            raise RuntimeError("live viewer request ended without a result")
        return request.result

    def _viewer_loop(self) -> None:
        while True:
            request = self._requests.get()
            if request is None:
                return
            try:
                request.result = self._play_prompt_control(request.prompt, robot=request.robot) if _use_prompt_control_live(
                    request.prompt,
                    request.mode,
                ) else self._play_task(parse_prompt(request.prompt, robot_hint=request.robot))
            except Exception as exc:  # noqa: BLE001 - returned through the bridge.
                request.error = f"{type(exc).__name__}: {exc}"
            finally:
                request.event.set()

    def _play_task(self, task: TaskSpec) -> dict[str, object]:
        try:
            import mujoco
            import mujoco.viewer
        except ModuleNotFoundError as exc:
            raise RuntimeError("MuJoCo is not installed. Install with: pip install -e '.[sim]'") from exc

        scene_xml = build_scene_xml(task)
        controller = AlohaMujocoController(scene_xml)
        selected_camera = _select_camera(mujoco, controller.model, self.camera)
        frame_delay = 1.0 / self.fps
        viewer_closed = False

        def sync_viewer(frame: TrajectoryFrame, active_controller: AlohaMujocoController) -> None:
            del frame, active_controller
            if not viewer.is_running():
                raise ViewerClosed
            viewer.sync()
            time.sleep(frame_delay)

        with mujoco.viewer.launch_passive(controller.model, controller.data) as viewer:
            _configure_viewer_camera(mujoco, viewer, controller.model, selected_camera)
            controller.frame_callback = sync_viewer

            try:
                controller.run_task(task)
            except ViewerClosed:
                viewer_closed = True

            hold_until = time.monotonic() + self.hold_seconds
            while not viewer_closed and viewer.is_running() and time.monotonic() < hold_until:
                viewer.sync()
                time.sleep(0.05)

        return {
            "task": task.to_dict(),
            "frames": len(controller.frames),
            "camera": selected_camera,
            "viewer_closed": viewer_closed,
            "live": True,
            "mode": "demo",
        }

    def _play_prompt_control(self, prompt: str, *, robot: str = "aloha") -> dict[str, object]:
        try:
            import mujoco
            import mujoco.viewer
        except ModuleNotFoundError as exc:
            raise RuntimeError("MuJoCo is not installed. Install with: pip install -e '.[sim]'") from exc

        from nemoclaw2robot.session import DEFAULT_SESSION_ROOT, load_session, prompt_control

        control_result = prompt_control(prompt, robot=robot)
        session = load_session(str(control_result["session_id"]), root=DEFAULT_SESSION_ROOT)
        scene_xml = build_scene_xml(
            session.task,
            extra_objects=tuple(session.scene_objects),
            trace_segments=tuple(session.trace_segments),
        )
        controller = AlohaMujocoController(scene_xml)
        controller.reset(clear_frames=True)
        plan = control_result.get("plan", {})
        planned_hand = plan.get("hand") if isinstance(plan, dict) else None
        hand = str(planned_hand) if planned_hand in {"left", "right"} else "right"
        selected_camera = _select_camera(mujoco, controller.model, self.camera)
        frame_delay = 1.0 / self.fps
        viewer_closed = False

        with mujoco.viewer.launch_passive(controller.model, controller.data) as viewer:
            _configure_viewer_camera(mujoco, viewer, controller.model, selected_camera)

            try:
                for frame in session.last_frames:
                    if not viewer.is_running():
                        raise ViewerClosed
                    controller._solve_ik(hand, np.array(frame["gripper"], dtype=float), iterations=8)
                    controller._set_gripper(hand, float(frame["gripper_opening"]))
                    controller._set_cube_position(np.array(frame["cube"], dtype=float))
                    controller.data.qvel[:] = 0
                    controller.mujoco.mj_forward(controller.model, controller.data)
                    viewer.sync()
                    time.sleep(frame_delay)
            except ViewerClosed:
                viewer_closed = True

            hold_until = time.monotonic() + self.hold_seconds
            while not viewer_closed and viewer.is_running() and time.monotonic() < hold_until:
                viewer.sync()
                time.sleep(0.05)

        operations = control_result.get("plan", {})
        operation_list = operations.get("operations", []) if isinstance(operations, dict) else []
        return {
            "session_id": session.session_id,
            "operations": [
                str(operation.get("type", "unknown"))
                for operation in operation_list
                if isinstance(operation, dict)
            ],
            "frames": len(session.last_frames),
            "camera": selected_camera,
            "viewer_closed": viewer_closed,
            "scene_path": str(DEFAULT_SESSION_ROOT / session.session_id / "scene.xml"),
            "live": True,
            "mode": "prompt_control",
        }

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
                if self.path.rstrip("/") != "/health":
                    self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"ok": True, "service": "nemoclaw2robot-live-viewer"})

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
                if self.path.rstrip("/") not in {"/prompt", "/run"}:
                    self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
                    return

                try:
                    payload = self._read_json()
                    prompt = str(payload.get("prompt", "")).strip()
                    if not prompt:
                        raise ValueError("prompt is required")
                    robot = str(payload.get("robot", "aloha")).strip() or "aloha"
                    timeout_seconds = float(payload.get("timeout_seconds", 300.0))
                    mode = str(payload.get("mode", "auto")).strip() or "auto"
                    result = bridge.submit(prompt, robot=robot, timeout_seconds=timeout_seconds, mode=mode)
                    self._send_json({"ok": True, "result": result})
                except Exception as exc:  # noqa: BLE001 - HTTP error payload.
                    self._send_json(
                        {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )

            def log_message(self, format: str, *args: Any) -> None:
                del format, args

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("content-length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("JSON object expected")
                return payload

            def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(int(status))
                self.send_header("content-type", "application/json; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


def watch_sandbox_live_requests(
    *,
    sandbox: str,
    gateway: str = "nemoclaw",
    poll_interval: float = 1.0,
    fps: float = 30.0,
    camera: str | None = "teleoperator_pov",
    hold_seconds: float = 4.0,
) -> None:
    """Poll a NemoClaw sandbox live-request queue and play requests on the host."""

    if poll_interval <= 0:
        raise ValueError("poll_interval must be greater than zero")

    bridge = LiveViewerBridge(fps=fps, camera=camera, hold_seconds=hold_seconds)
    print(
        json.dumps(
            {
                "live_agent_viewer": "ready",
                "sandbox": sandbox,
                "gateway": gateway,
                "queue": "/sandbox/NemoClaw2Robot/artifacts/live_requests",
                "session_prompt_fallback": True,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    seen_session_prompts = {
        item["key"]
        for item in _sandbox_session_live_prompts(sandbox=sandbox, gateway=gateway)
        if "key" in item
    }

    while True:
        request_path = _next_sandbox_request(sandbox=sandbox, gateway=gateway)
        if not request_path:
            session_prompt = _next_unseen_session_live_prompt(
                sandbox=sandbox,
                gateway=gateway,
                seen=seen_session_prompts,
            )
            if session_prompt is not None:
                _play_live_prompt(
                    bridge,
                    prompt=str(session_prompt["prompt"]),
                    robot=str(session_prompt.get("robot", "aloha") or "aloha"),
                    mode=str(session_prompt.get("mode", "auto") or "auto"),
                    request=str(session_prompt["key"]),
                    source="session_prompt",
                )
                continue
            time.sleep(poll_interval)
            continue

        try:
            payload = _read_sandbox_json(sandbox=sandbox, gateway=gateway, path=request_path)
            _archive_sandbox_request(sandbox=sandbox, gateway=gateway, path=request_path)
            prompt = str(payload.get("prompt", "")).strip()
            if not prompt:
                print(
                    json.dumps({"live_agent_viewer": "skipped", "reason": "missing prompt", "path": request_path}),
                    flush=True,
                )
                continue
            robot = str(payload.get("robot", "aloha") or "aloha")
            mode = str(payload.get("mode", "auto") or "auto")
            _play_live_prompt(
                bridge,
                prompt=prompt,
                robot=robot,
                mode=mode,
                request=request_path,
                source="queue",
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - keep watcher alive.
            print(
                json.dumps(
                    {
                        "live_agent_viewer": "error",
                        "request": request_path,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            time.sleep(poll_interval)


def _play_live_prompt(
    bridge: LiveViewerBridge,
    *,
    prompt: str,
    robot: str,
    mode: str,
    request: str,
    source: str,
) -> None:
    route = "prompt_control" if _use_prompt_control_live(prompt, mode) else "demo"
    print(
        json.dumps(
            {
                "live_agent_viewer": "playing",
                "source": source,
                "request": request,
                "route": route,
                "mode": mode,
                "prompt": prompt,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    result = (
        bridge._play_prompt_control(prompt, robot=robot)
        if route == "prompt_control"
        else bridge._play_task(parse_prompt(prompt, robot_hint=robot))
    )
    print(
        json.dumps(
            {
                "live_agent_viewer": "played",
                "source": source,
                "request": request,
                "result": result,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def _next_sandbox_request(*, sandbox: str, gateway: str) -> str:
    command = (
        "mkdir -p /sandbox/NemoClaw2Robot/artifacts/live_requests "
        "/sandbox/NemoClaw2Robot/artifacts/live_processed; "
        "find /sandbox/NemoClaw2Robot/artifacts/live_requests -maxdepth 1 -type f -name '*.json' "
        "| sort | head -n 1"
    )
    return _openshell_exec(sandbox=sandbox, gateway=gateway, command=command).strip()


def _read_sandbox_json(*, sandbox: str, gateway: str, path: str) -> dict[str, Any]:
    raw = _openshell_exec(sandbox=sandbox, gateway=gateway, command=f"cat -- {shlex.quote(path)}")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("live request JSON object expected")
    return payload


def _archive_sandbox_request(*, sandbox: str, gateway: str, path: str) -> None:
    quoted_path = shlex.quote(path)
    command = (
        "mkdir -p /sandbox/NemoClaw2Robot/artifacts/live_processed; "
        f"mv -- {quoted_path} /sandbox/NemoClaw2Robot/artifacts/live_processed/"
    )
    _openshell_exec(sandbox=sandbox, gateway=gateway, command=command)


def _next_unseen_session_live_prompt(
    *,
    sandbox: str,
    gateway: str,
    seen: set[str],
) -> dict[str, object] | None:
    for item in _sandbox_session_live_prompts(sandbox=sandbox, gateway=gateway):
        key = str(item["key"])
        if key in seen:
            continue
        seen.add(key)
        return item
    return None


def _sandbox_session_live_prompts(*, sandbox: str, gateway: str) -> list[dict[str, object]]:
    command = (
        "find /sandbox/.openclaw/agents/main/sessions -maxdepth 1 -type f "
        "-name '*.jsonl' ! -name '*.trajectory.jsonl' -printf '%T@ %p\\n' 2>/dev/null "
        "| sort -nr | head -20 | cut -d' ' -f2- "
        "| while IFS= read -r p; do "
        "grep -Hn '\"role\"[[:space:]]*:[[:space:]]*\"user\"' \"$p\" 2>/dev/null || true; "
        "done | tail -100"
    )
    raw = _openshell_exec(sandbox=sandbox, gateway=gateway, command=command)
    prompts: list[dict[str, object]] = []
    for line in raw.splitlines():
        try:
            path, line_no, payload = line.split(":", 2)
            item = json.loads(payload)
        except (ValueError, json.JSONDecodeError):
            continue
        prompt = _extract_live_prompt_from_message(item)
        if prompt is None:
            continue
        prompts.append(
            {
                "key": f"{path}:{line_no}",
                "prompt": prompt,
                "robot": "aloha",
                "mode": "auto",
                "timestamp": item.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            }
        )
    return prompts


def _extract_live_prompt_from_message(item: dict[str, Any]) -> str | None:
    if item.get("type") != "message":
        return None
    message = item.get("message")
    if not isinstance(message, dict) or message.get("role") != "user":
        return None
    content = message.get("content")
    if isinstance(content, str):
        prompt = content.strip()
        if not _is_live_aloha_prompt(prompt):
            return None
        return prompt
    if not isinstance(content, list):
        return None
    text_parts = [
        str(part.get("text", ""))
        for part in content
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    prompt = "\n".join(text_parts).strip()
    if not _is_live_aloha_prompt(prompt):
        return None
    return prompt


def _is_live_aloha_prompt(prompt: str) -> bool:
    text = prompt.lower()
    debug_markers = (
        "tool_search_code",
        "openclaw.tools.search",
        "openclaw.tools.describe",
        "openclaw.tools.call",
        "aloha_mujoco_live",
    )
    if any(marker in text for marker in debug_markers):
        return False
    live_words = ("リアルタイム", "ライブ", "見たい", "画面", "ui", "viewer", "live", "watch")
    robot_words = (
        "aloha",
        "アーム",
        "ロボット",
        "右アーム",
        "左アーム",
        "キューブ",
        "球体",
        "cube",
        "sphere",
        "arm",
    )
    return any(word in text for word in live_words) and any(word in text for word in robot_words)


def _openshell_exec(*, sandbox: str, gateway: str, command: str) -> str:
    result = subprocess.run(
        [
            "openshell",
            "sandbox",
            "exec",
            "-g",
            gateway,
            "-n",
            sandbox,
            "--",
            "bash",
            "-lc",
            command,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout


def _use_prompt_control_live(prompt: str, mode: str = "auto") -> bool:
    normalized_mode = mode.strip().lower()
    if normalized_mode in {"demo", "task", "fixed"}:
        return False
    text = prompt.lower()
    looks_control = _looks_like_control_live_prompt(text)
    if normalized_mode in {"control", "prompt_control", "prompt-control"}:
        if _looks_like_fixed_demo_prompt(text) and not looks_control:
            return False
        return True
    return looks_control


def _looks_like_control_live_prompt(text: str) -> bool:
    control_words = (
        "cm",
        "センチ",
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
    )
    movement_words = ("動か", "移動", "move", "shift", "ずら")
    return any(word in text for word in control_words) or any(word in text for word in movement_words)


def _looks_like_fixed_demo_prompt(text: str) -> bool:
    fixed_words = (
        "掴",
        "つか",
        "把持",
        "grasp",
        "grab",
        "pick",
        "置",
        "place",
        "put",
        "押",
        "push",
        "slide",
    )
    return any(word in text for word in fixed_words)
