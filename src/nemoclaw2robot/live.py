from __future__ import annotations

import json
import queue
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

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

    def submit(self, prompt: str, *, robot: str = "aloha", timeout_seconds: float = 300.0) -> dict[str, object]:
        request = LiveRequest(
            prompt=prompt,
            robot=robot,
            timeout_seconds=timeout_seconds,
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
                task = parse_prompt(request.prompt, robot_hint=request.robot)
                request.result = self._play_task(task)
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
                    result = bridge.submit(prompt, robot=robot, timeout_seconds=timeout_seconds)
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
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    while True:
        request_path = _next_sandbox_request(sandbox=sandbox, gateway=gateway)
        if not request_path:
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
            task = parse_prompt(prompt, robot_hint=str(payload.get("robot", "aloha") or "aloha"))
            result = bridge._play_task(task)
            print(
                json.dumps({"live_agent_viewer": "played", "request": request_path, "result": result}, ensure_ascii=False),
                flush=True,
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
