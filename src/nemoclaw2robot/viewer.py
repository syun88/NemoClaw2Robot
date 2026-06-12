from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nemoclaw2robot.models import TaskSpec
from nemoclaw2robot.scene import build_scene_xml
from nemoclaw2robot.simulator import AlohaMujocoController, MujocoUnavailableError, TrajectoryFrame


class ViewerClosed(RuntimeError):
    """Raised internally when the MuJoCo viewer is closed during playback."""


@dataclass(frozen=True)
class ViewerResult:
    task: TaskSpec
    frames: int
    camera: str | None
    viewer_closed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task.to_dict(),
            "frames": self.frames,
            "camera": self.camera,
            "viewer_closed": self.viewer_closed,
        }


def view_prompt(
    task: TaskSpec,
    *,
    fps: float = 30.0,
    camera: str | None = "teleoperator_pov",
    loop: bool = False,
    keep_open: bool = True,
    scene_output: Path | None = None,
) -> ViewerResult:
    """Run a prompt-controlled ALOHA task in the native MuJoCo viewer."""

    if fps <= 0:
        raise ValueError("fps must be greater than zero")

    try:
        import mujoco
        import mujoco.viewer
    except ModuleNotFoundError as exc:
        raise MujocoUnavailableError(
            "MuJoCo is not installed. Install with: pip install -e '.[sim]'"
        ) from exc

    scene_xml = build_scene_xml(task)
    if scene_output is not None:
        scene_output.parent.mkdir(parents=True, exist_ok=True)
        scene_output.write_text(scene_xml, encoding="utf-8")

    frame_delay = 1.0 / fps
    controller = AlohaMujocoController(scene_xml)
    selected_camera = _select_camera(mujoco, controller.model, camera)

    def sync_viewer(frame: TrajectoryFrame, active_controller: AlohaMujocoController) -> None:
        del frame
        if not viewer.is_running():
            raise ViewerClosed
        viewer.sync()
        time.sleep(frame_delay)

    viewer_closed = False
    with mujoco.viewer.launch_passive(controller.model, controller.data) as viewer:
        _configure_viewer_camera(mujoco, viewer, controller.model, selected_camera)
        controller.frame_callback = sync_viewer

        try:
            while viewer.is_running():
                controller.run_task(task)
                if not loop:
                    break
                time.sleep(0.35)
        except ViewerClosed:
            viewer_closed = True

        if keep_open and not viewer_closed:
            while viewer.is_running():
                viewer.sync()
                time.sleep(0.05)

    return ViewerResult(
        task=task,
        frames=len(controller.frames),
        camera=selected_camera,
        viewer_closed=viewer_closed,
    )


def macos_viewer_command(prompt: str, *, fps: float = 30.0) -> str:
    executable = Path(sys.executable)
    mjpython = executable.with_name("mjpython")
    runner = str(mjpython if mjpython.exists() else executable)
    return (
        f'{runner} -m nemoclaw2robot.cli view '
        f'--prompt {json.dumps(prompt, ensure_ascii=False)} --fps {fps:g}'
    )


def _select_camera(mujoco: Any, model: Any, requested: str | None) -> str | None:
    if requested is None:
        return None

    preferred = (requested, "teleoperator_pov", "overhead_cam", "collaborator_pov")
    for camera_name in preferred:
        camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
        if camera_id >= 0:
            return camera_name
    return None


def _configure_viewer_camera(mujoco: Any, viewer: Any, model: Any, camera_name: str | None) -> None:
    if camera_name is None:
        return
    camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
    if camera_id < 0:
        return
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    viewer.cam.fixedcamid = camera_id
