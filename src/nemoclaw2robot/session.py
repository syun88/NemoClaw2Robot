from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from nemoclaw2robot.models import SceneObjectKind, SceneObjectSpec, TaskSpec, TraceSegmentSpec
from nemoclaw2robot.prompt import parse_prompt
from nemoclaw2robot.robots.aloha import ALOHA_SPEC
from nemoclaw2robot.scene import build_scene_xml
from nemoclaw2robot.simulator import AlohaMujocoController, GRIPPER_CLOSED, GRIPPER_OPENING

DEFAULT_SESSION_ROOT = Path("artifacts/sessions")


@dataclass
class AlohaSession:
    session_id: str
    task: TaskSpec
    scene_objects: list[SceneObjectSpec] = field(default_factory=list)
    trace_segments: list[TraceSegmentSpec] = field(default_factory=list)
    qpos_by_joint: dict[str, list[float]] = field(default_factory=dict)
    ctrl_by_actuator: dict[str, float] = field(default_factory=dict)
    last_frames: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "task": self.task.to_dict(),
            "scene_objects": [scene_object.to_dict() for scene_object in self.scene_objects],
            "trace_segments": [segment.to_dict() for segment in self.trace_segments],
            "qpos_by_joint": self.qpos_by_joint,
            "ctrl_by_actuator": self.ctrl_by_actuator,
            "last_frames": self.last_frames,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AlohaSession":
        return cls(
            session_id=str(payload["session_id"]),
            task=TaskSpec(**payload["task"]),
            scene_objects=[_scene_object_from_dict(item) for item in payload.get("scene_objects", [])],
            trace_segments=[_trace_segment_from_dict(item) for item in payload.get("trace_segments", [])],
            qpos_by_joint={
                str(name): [float(value) for value in values]
                for name, values in payload.get("qpos_by_joint", {}).items()
            },
            ctrl_by_actuator={
                str(name): float(value)
                for name, value in payload.get("ctrl_by_actuator", {}).items()
            },
            last_frames=list(payload.get("last_frames", [])),
        )


def create_session(
    prompt: str,
    *,
    session_id: str | None = None,
    root: Path = DEFAULT_SESSION_ROOT,
    robot: str = "aloha",
) -> dict[str, object]:
    task = parse_prompt(prompt, robot_hint=robot)
    session = AlohaSession(session_id=session_id or _new_session_id(prompt), task=task)
    controller = _controller_for_session(session)
    controller.reset(clear_frames=True)
    _capture_controller_state(session, controller)
    _write_session(session, root=root)
    return _session_result(session, root=root, controller=controller)


def get_state(session_id: str, *, root: Path = DEFAULT_SESSION_ROOT) -> dict[str, object]:
    session = _read_session(session_id, root=root)
    controller = _controller_for_session(session)
    return _state_payload(session, controller)


def load_session(session_id: str, *, root: Path = DEFAULT_SESSION_ROOT) -> AlohaSession:
    return _read_session(session_id, root=root)


def solve_ik(
    session_id: str,
    *,
    hand: str = "right",
    position: tuple[float, float, float],
    root: Path = DEFAULT_SESSION_ROOT,
    save: bool = False,
) -> dict[str, object]:
    session = _read_session(session_id, root=root)
    controller = _controller_for_session(session)
    start = controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)
    controller._solve_ik(hand, np.array(position, dtype=float), iterations=24)
    controller.mujoco.mj_forward(controller.model, controller.data)
    actual = controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)
    error = float(np.linalg.norm(actual - np.array(position, dtype=float)))
    if save:
        _capture_controller_state(session, controller)
        _write_session(session, root=root)
    return {
        "session_id": session.session_id,
        "hand": hand,
        "target_position": list(position),
        "start_position": _list3(start),
        "actual_position": _list3(actual),
        "position_error": error,
        "saved": save,
        "arm_qpos": _arm_qpos(controller, hand),
    }


def move_to_pose(
    session_id: str,
    *,
    hand: str = "right",
    position: tuple[float, float, float],
    steps: int = 30,
    root: Path = DEFAULT_SESSION_ROOT,
    phase: str = "move_to_pose",
) -> dict[str, object]:
    session = _read_session(session_id, root=root)
    controller = _controller_for_session(session)
    start = controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)
    controller._move_to(hand, np.array(position, dtype=float), phase, steps=max(1, steps))
    _capture_controller_state(session, controller)
    _write_session(session, root=root)
    actual = controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)
    return {
        "session_id": session.session_id,
        "hand": hand,
        "start_position": _list3(start),
        "target_position": list(position),
        "actual_position": _list3(actual),
        "position_error": float(np.linalg.norm(actual - np.array(position, dtype=float))),
        "frames": len(session.last_frames),
    }


def move_relative(
    session_id: str,
    *,
    hand: str = "right",
    delta: tuple[float, float, float],
    steps: int = 30,
    root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, object]:
    session = _read_session(session_id, root=root)
    controller = _controller_for_session(session)
    start = controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)
    target = start + np.array(delta, dtype=float)
    controller._move_to(hand, target, "move_relative", steps=max(1, steps))
    _capture_controller_state(session, controller)
    _write_session(session, root=root)
    actual = controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)
    return {
        "session_id": session.session_id,
        "hand": hand,
        "delta": list(delta),
        "start_position": _list3(start),
        "target_position": _list3(target),
        "actual_position": _list3(actual),
        "position_error": float(np.linalg.norm(actual - target)),
        "frames": len(session.last_frames),
    }


def execute_cartesian_path(
    session_id: str,
    *,
    hand: str = "right",
    waypoints: tuple[tuple[float, float, float], ...],
    steps_per_waypoint: int = 20,
    root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, object]:
    if not waypoints:
        raise ValueError("at least one waypoint is required")
    session = _read_session(session_id, root=root)
    controller = _controller_for_session(session)
    start = controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)
    for waypoint in waypoints:
        controller._move_to(
            hand,
            np.array(waypoint, dtype=float),
            "cartesian_path",
            steps=max(1, steps_per_waypoint),
        )
    _capture_controller_state(session, controller)
    _write_session(session, root=root)
    actual = controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)
    target = np.array(waypoints[-1], dtype=float)
    return {
        "session_id": session.session_id,
        "hand": hand,
        "waypoints": [list(waypoint) for waypoint in waypoints],
        "start_position": _list3(start),
        "actual_position": _list3(actual),
        "final_position_error": float(np.linalg.norm(actual - target)),
        "frames": len(session.last_frames),
    }


def set_gripper(
    session_id: str,
    *,
    hand: str = "right",
    opening: float,
    steps: int = 12,
    root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, object]:
    session = _read_session(session_id, root=root)
    controller = _controller_for_session(session)
    start = controller._gripper_opening(hand)
    controller._animate_gripper(hand, float(opening), "set_gripper", steps=max(1, steps))
    _capture_controller_state(session, controller)
    _write_session(session, root=root)
    return {
        "session_id": session.session_id,
        "hand": hand,
        "start_opening": start,
        "target_opening": float(opening),
        "actual_opening": controller._gripper_opening(hand),
        "frames": len(session.last_frames),
    }


def add_object(
    session_id: str,
    *,
    name: str,
    kind: SceneObjectKind,
    position: tuple[float, float, float],
    size: tuple[float, ...] | None = None,
    rgba: tuple[float, float, float, float] | None = None,
    fixed: bool | None = None,
    root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, object]:
    session = _read_session(session_id, root=root)
    object_name = _safe_name(name)
    session.scene_objects = [item for item in session.scene_objects if item.name != object_name]
    previous_frames = list(session.last_frames)
    session.scene_objects.append(
        SceneObjectSpec(
            name=object_name,
            kind=kind,
            position=position,
            size=size or _default_size(kind),
            rgba=rgba or _default_rgba(kind),
            fixed=_default_fixed(kind) if fixed is None else fixed,
        )
    )
    controller = _controller_for_session(session)
    _capture_controller_state(session, controller)
    if previous_frames and not controller.frames:
        session.last_frames = previous_frames
    _write_session(session, root=root)
    return {
        "session_id": session.session_id,
        "object": session.scene_objects[-1].to_dict(),
        "scene_path": str(_session_dir(root, session.session_id) / "scene.xml"),
        "state": _state_payload(session, controller),
    }


def add_trace(
    session_id: str,
    *,
    points: tuple[tuple[float, float, float], ...],
    name_prefix: str = "trace",
    radius: float = 0.004,
    rgba: tuple[float, float, float, float] = (0.05, 0.05, 0.05, 1.0),
    root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, object]:
    if len(points) < 2:
        raise ValueError("at least two points are required for a trace")
    session = _read_session(session_id, root=root)
    safe_prefix = _safe_name(name_prefix)
    start_index = len(session.trace_segments)
    previous_frames = list(session.last_frames)
    for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
        session.trace_segments.append(
            TraceSegmentSpec(
                name=f"{safe_prefix}_{start_index + index}",
                from_pos=start,
                to_pos=end,
                radius=radius,
                rgba=rgba,
            )
    )
    controller = _controller_for_session(session)
    _capture_controller_state(session, controller)
    if previous_frames and not controller.frames:
        session.last_frames = previous_frames
    _write_session(session, root=root)
    return {
        "session_id": session.session_id,
        "trace_segments_added": len(points) - 1,
        "scene_path": str(_session_dir(root, session.session_id) / "scene.xml"),
    }


def check_pose(
    session_id: str,
    *,
    hand: str = "right",
    expected_position: tuple[float, float, float] | None = None,
    tolerance: float = 0.02,
    root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, object]:
    session = _read_session(session_id, root=root)
    controller = _controller_for_session(session)
    actual = controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)
    payload: dict[str, object] = {
        "session_id": session.session_id,
        "hand": hand,
        "actual_position": _list3(actual),
    }
    if expected_position is not None:
        error = float(np.linalg.norm(actual - np.array(expected_position, dtype=float)))
        payload.update(
            {
                "expected_position": list(expected_position),
                "position_error": error,
                "within_tolerance": error <= tolerance,
                "tolerance": tolerance,
            }
        )
    return payload


def check_contacts(
    session_id: str,
    *,
    object_name: str | None = None,
    root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, object]:
    session = _read_session(session_id, root=root)
    controller = _controller_for_session(session)
    state = _state_payload(session, controller)
    contacts = list(state["contacts"])
    if object_name:
        contacts = [
            contact
            for contact in contacts
            if object_name in {contact.get("geom1"), contact.get("geom2")}
            or f"{object_name}_geom" in {contact.get("geom1"), contact.get("geom2")}
        ]
    return {
        "session_id": session.session_id,
        "object_name": object_name,
        "contacts": contacts,
        "contact_count": len(contacts),
    }


def prompt_control(
    prompt: str,
    *,
    session_id: str | None = None,
    root: Path = DEFAULT_SESSION_ROOT,
    robot: str = "aloha",
    steps: int = 30,
) -> dict[str, object]:
    """Execute a conservative natural-language control prompt as session primitives."""

    plan = _plan_prompt_control(prompt, steps=steps)
    session_result = create_session(prompt, session_id=session_id, root=root, robot=robot)
    active_session_id = str(session_result["session_id"])
    results: list[dict[str, object]] = [
        {
            "operation": "session_start",
            "result": session_result,
        }
    ]
    warnings: list[str] = []

    for operation in plan["operations"]:
        operation_type = operation["type"]
        if operation_type == "add_object":
            result = add_object(
                active_session_id,
                name=str(operation["name"]),
                kind=str(operation["kind"]),  # type: ignore[arg-type]
                position=tuple(operation["position"]),  # type: ignore[arg-type]
                size=tuple(operation["size"]) if operation.get("size") else None,  # type: ignore[arg-type]
                rgba=tuple(operation["rgba"]) if operation.get("rgba") else None,  # type: ignore[arg-type]
                fixed=bool(operation.get("fixed", False)),
                root=root,
            )
        elif operation_type == "move_relative":
            result = move_relative(
                active_session_id,
                hand=str(operation["hand"]),
                delta=tuple(operation["delta"]),  # type: ignore[arg-type]
                steps=int(operation["steps"]),
                root=root,
            )
        elif operation_type == "gripper":
            result = set_gripper(
                active_session_id,
                hand=str(operation["hand"]),
                opening=float(operation["opening"]),
                steps=int(operation["steps"]),
                root=root,
            )
        elif operation_type == "draw_trace":
            path_points = tuple(tuple(point) for point in operation["path_points"])  # type: ignore[index]
            result = execute_cartesian_path(
                active_session_id,
                hand=str(operation["hand"]),
                waypoints=path_points,  # type: ignore[arg-type]
                steps_per_waypoint=max(1, int(operation["steps"]) // max(1, len(path_points))),
                root=root,
            )
            trace_result = add_trace(
                active_session_id,
                points=tuple(tuple(point) for point in operation["trace_points"]),  # type: ignore[arg-type,index]
                name_prefix=str(operation.get("name_prefix", "draw")),
                root=root,
            )
            result = {
                "motion": result,
                "trace": trace_result,
            }
        else:
            warnings.append(f"unsupported operation skipped: {operation_type}")
            continue

        results.append(
            {
                "operation": operation_type,
                "request": operation,
                "result": result,
            }
        )

    if not plan["operations"]:
        warnings.append(
            "No controllable primitive was parsed from the prompt; the session was created but no motion was executed."
        )

    final_state = get_state(active_session_id, root=root)
    return {
        "session_id": active_session_id,
        "prompt": prompt,
        "plan": plan,
        "results": results,
        "final_state": final_state,
        "scene_path": str(_session_dir(root, active_session_id) / "scene.xml"),
        "warnings": warnings,
    }


def _plan_prompt_control(prompt: str, *, steps: int = 30) -> dict[str, object]:
    text = _normalize_control_text(prompt)
    hand = _detect_control_hand(text)
    candidates: list[dict[str, object]] = []

    paper_index = _first_index(text, ("紙", "paper"))
    draw_index = _first_index(text, ("描", "書", "draw", "line", "線", "絵"))
    if paper_index >= 0 or draw_index >= 0:
        candidates.append(
            {
                "index": paper_index if paper_index >= 0 else draw_index,
                "type": "add_object",
                "name": "paper",
                "kind": "paper",
                "position": (0.0, -0.30, 0.003),
                "fixed": True,
            }
        )

    created_object = _detect_created_object(text)
    if created_object is not None:
        candidates.append(created_object)

    move = _detect_relative_control_move(text, hand=hand, steps=steps)
    if move is not None:
        candidates.append(move)

    gripper = _detect_gripper_operation(text, hand=hand)
    if gripper is not None:
        candidates.append(gripper)

    if draw_index >= 0:
        candidates.append(
            {
                "index": draw_index,
                "type": "draw_trace",
                "hand": hand,
                "path_points": (
                    (-0.04, -0.32, 0.035),
                    (0.04, -0.32, 0.035),
                    (0.04, -0.27, 0.035),
                ),
                "trace_points": (
                    (-0.04, -0.32, 0.010),
                    (0.04, -0.32, 0.010),
                    (0.04, -0.27, 0.010),
                ),
                "steps": max(30, steps),
                "name_prefix": "draw",
            }
        )

    operations = [
        {key: value for key, value in operation.items() if key != "index"}
        for operation in sorted(candidates, key=lambda item: int(item.get("index", 0)))
    ]
    return {
        "hand": hand,
        "operations": operations,
        "coordinate_frame": ALOHA_SPEC.coordinate_frame,
        "notes": (
            "right is negative y",
            "drawing uses motion plus visual trace, not real ink",
        ),
    }


def _session_result(session: AlohaSession, *, root: Path, controller: AlohaMujocoController) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "task": session.task.to_dict(),
        "scene_path": str(_session_dir(root, session.session_id) / "scene.xml"),
        "state": _state_payload(session, controller),
    }


def _controller_for_session(session: AlohaSession) -> AlohaMujocoController:
    scene_xml = build_scene_xml(
        session.task,
        extra_objects=tuple(session.scene_objects),
        trace_segments=tuple(session.trace_segments),
    )
    controller = AlohaMujocoController(scene_xml)
    controller.reset(clear_frames=True)
    _apply_controller_state(session, controller)
    controller.mujoco.mj_forward(controller.model, controller.data)
    return controller


def _state_payload(session: AlohaSession, controller: AlohaMujocoController) -> dict[str, object]:
    controller.mujoco.mj_forward(controller.model, controller.data)
    return {
        "session_id": session.session_id,
        "task": session.task.to_dict(),
        "arms": {
            hand: {
                "gripper_site": ALOHA_SPEC.arm(hand).gripper_site,
                "gripper_position": _list3(controller._site_position(ALOHA_SPEC.arm(hand).gripper_site)),
                "gripper_opening": controller._gripper_opening(hand),
                "joint_qpos": _arm_qpos(controller, hand),
            }
            for hand in ALOHA_SPEC.arms
        },
        "objects": _object_states(session, controller),
        "contacts": _contacts(controller),
        "scene_objects": [scene_object.to_dict() for scene_object in session.scene_objects],
        "trace_segment_count": len(session.trace_segments),
        "last_frame_count": len(session.last_frames),
    }


def _object_states(session: AlohaSession, controller: AlohaMujocoController) -> dict[str, object]:
    objects: dict[str, object] = {
        "cube": {
            "position": _list3(controller._cube_position()),
            "joint": "cube_free",
        }
    }
    for scene_object in session.scene_objects:
        joint_name = f"{scene_object.name}_free"
        if scene_object.fixed:
            objects[scene_object.name] = {
                "position": list(scene_object.position),
                "fixed": True,
                "kind": scene_object.kind,
            }
            continue
        joint_id = controller.mujoco.mj_name2id(controller.model, controller.mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint_id < 0:
            continue
        qpos_id = int(controller.model.jnt_qposadr[joint_id])
        objects[scene_object.name] = {
            "position": _list3(controller.data.qpos[qpos_id : qpos_id + 3]),
            "joint": joint_name,
            "kind": scene_object.kind,
        }
    return objects


def _contacts(controller: AlohaMujocoController) -> list[dict[str, object]]:
    contacts: list[dict[str, object]] = []
    for index in range(int(controller.data.ncon)):
        contact = controller.data.contact[index]
        geom1 = controller.mujoco.mj_id2name(controller.model, controller.mujoco.mjtObj.mjOBJ_GEOM, contact.geom1)
        geom2 = controller.mujoco.mj_id2name(controller.model, controller.mujoco.mjtObj.mjOBJ_GEOM, contact.geom2)
        contacts.append(
            {
                "geom1": geom1,
                "geom2": geom2,
                "distance": float(contact.dist),
            }
        )
    return contacts


def _capture_controller_state(session: AlohaSession, controller: AlohaMujocoController) -> None:
    session.qpos_by_joint = _qpos_by_joint(controller)
    session.ctrl_by_actuator = _ctrl_by_actuator(controller)
    session.last_frames = [frame.to_dict() for frame in controller.frames]


def _apply_controller_state(session: AlohaSession, controller: AlohaMujocoController) -> None:
    for joint_name, values in session.qpos_by_joint.items():
        joint_id = controller.mujoco.mj_name2id(controller.model, controller.mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint_id < 0:
            continue
        qpos_id = int(controller.model.jnt_qposadr[joint_id])
        width = _joint_qpos_width(controller, joint_id)
        controller.data.qpos[qpos_id : qpos_id + width] = np.array(values[:width], dtype=float)

    for actuator_name, value in session.ctrl_by_actuator.items():
        actuator_id = controller.mujoco.mj_name2id(
            controller.model,
            controller.mujoco.mjtObj.mjOBJ_ACTUATOR,
            actuator_name,
        )
        if actuator_id >= 0:
            controller.data.ctrl[actuator_id] = float(value)


def _qpos_by_joint(controller: AlohaMujocoController) -> dict[str, list[float]]:
    qpos: dict[str, list[float]] = {}
    for joint_id in range(controller.model.njnt):
        joint_name = controller.mujoco.mj_id2name(controller.model, controller.mujoco.mjtObj.mjOBJ_JOINT, joint_id)
        if not joint_name:
            continue
        qpos_id = int(controller.model.jnt_qposadr[joint_id])
        width = _joint_qpos_width(controller, joint_id)
        qpos[joint_name] = [float(value) for value in controller.data.qpos[qpos_id : qpos_id + width]]
    return qpos


def _ctrl_by_actuator(controller: AlohaMujocoController) -> dict[str, float]:
    ctrl: dict[str, float] = {}
    for actuator_id in range(controller.model.nu):
        actuator_name = controller.mujoco.mj_id2name(
            controller.model,
            controller.mujoco.mjtObj.mjOBJ_ACTUATOR,
            actuator_id,
        )
        if actuator_name:
            ctrl[actuator_name] = float(controller.data.ctrl[actuator_id])
    return ctrl


def _joint_qpos_width(controller: AlohaMujocoController, joint_id: int) -> int:
    joint_type = int(controller.model.jnt_type[joint_id])
    if joint_type == int(controller.mujoco.mjtJoint.mjJNT_FREE):
        return 7
    if joint_type == int(controller.mujoco.mjtJoint.mjJNT_BALL):
        return 4
    return 1


def _arm_qpos(controller: AlohaMujocoController, hand: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for joint_name in ALOHA_SPEC.arm(hand).joints:
        joint_id = controller._joint_id(joint_name)
        qpos_id = int(controller.model.jnt_qposadr[joint_id])
        values[joint_name] = float(controller.data.qpos[qpos_id])
    return values


def _write_session(session: AlohaSession, *, root: Path) -> None:
    session_dir = _session_dir(root, session.session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    scene_xml = build_scene_xml(
        session.task,
        extra_objects=tuple(session.scene_objects),
        trace_segments=tuple(session.trace_segments),
    )
    (session_dir / "scene.xml").write_text(scene_xml, encoding="utf-8")
    (session_dir / "session.json").write_text(
        json.dumps(session.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_session(session_id: str, *, root: Path) -> AlohaSession:
    path = _session_dir(root, session_id) / "session.json"
    if not path.exists():
        raise FileNotFoundError(f"session not found: {session_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("session JSON object expected")
    return AlohaSession.from_dict(payload)


def _session_dir(root: Path, session_id: str) -> Path:
    return root / _safe_name(session_id)


def _new_session_id(prompt: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
    return f"aloha_{stamp}_{digest}"


def _scene_object_from_dict(payload: dict[str, Any]) -> SceneObjectSpec:
    return SceneObjectSpec(
        name=str(payload["name"]),
        kind=str(payload["kind"]),  # type: ignore[arg-type]
        position=tuple(float(value) for value in payload["position"]),  # type: ignore[arg-type]
        size=tuple(float(value) for value in payload["size"]),
        rgba=tuple(float(value) for value in payload.get("rgba", (0.8, 0.2, 0.1, 1.0))),  # type: ignore[arg-type]
        fixed=bool(payload.get("fixed", False)),
    )


def _trace_segment_from_dict(payload: dict[str, Any]) -> TraceSegmentSpec:
    return TraceSegmentSpec(
        name=str(payload["name"]),
        from_pos=tuple(float(value) for value in payload["from_pos"]),  # type: ignore[arg-type]
        to_pos=tuple(float(value) for value in payload["to_pos"]),  # type: ignore[arg-type]
        radius=float(payload.get("radius", 0.004)),
        rgba=tuple(float(value) for value in payload.get("rgba", (0.05, 0.05, 0.05, 1.0))),  # type: ignore[arg-type]
    )


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    normalized = normalized.strip("-_").lower()
    if not normalized:
        raise ValueError("name must contain letters or numbers")
    return normalized


def _default_size(kind: str) -> tuple[float, ...]:
    if kind == "sphere":
        return (0.04,)
    if kind == "cylinder":
        return (0.03, 0.04)
    if kind == "paper":
        return (0.18, 0.12, 0.002)
    if kind == "marker":
        return (0.01,)
    return (0.035, 0.035, 0.035)


def _default_rgba(kind: str) -> tuple[float, float, float, float]:
    if kind == "paper":
        return (0.96, 0.96, 0.9, 1.0)
    if kind == "sphere":
        return (0.2, 0.35, 0.95, 1.0)
    if kind == "cylinder":
        return (0.1, 0.7, 0.3, 1.0)
    if kind == "marker":
        return (0.05, 0.05, 0.05, 1.0)
    return (0.9, 0.12, 0.08, 1.0)


def _default_fixed(kind: str) -> bool:
    return kind in {"paper", "marker"}


def _normalize_control_text(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.strip().lower())


def _detect_control_hand(text: str) -> str:
    if re.search(r"(左|left)\s*(?:アーム|arm)", text):
        return "left"
    if re.search(r"(右|right)\s*(?:アーム|arm)", text):
        return "right"
    return ALOHA_SPEC.default_hand


def _first_index(text: str, needles: tuple[str, ...]) -> int:
    indexes = [text.find(needle) for needle in needles if needle in text]
    return min(indexes) if indexes else -1


def _detect_created_object(text: str) -> dict[str, object] | None:
    if not _contains_any(text, ("配置", "置", "追加", "生成", "add", "place", "create", "spawn")):
        return None
    object_specs: tuple[tuple[str, tuple[str, ...], tuple[float, ...], tuple[float, float, float]], ...] = (
        ("sphere", ("球体", "球", "ボール", "sphere", "ball"), (0.035,), (0.05, -0.30, 0.040)),
        ("cylinder", ("円柱", "cylinder"), (0.030, 0.040), (0.05, -0.30, 0.045)),
        ("marker", ("ペン", "marker", "pen"), (0.010,), (0.02, -0.34, 0.020)),
    )
    for kind, words, size, position in object_specs:
        index = _first_index(text, words)
        if index >= 0:
            return {
                "index": index,
                "type": "add_object",
                "name": kind,
                "kind": kind,
                "position": position,
                "size": size,
                "fixed": kind == "marker",
            }
    return None


def _detect_relative_control_move(text: str, *, hand: str, steps: int) -> dict[str, object] | None:
    match = _direction_distance_match(text)
    if match is None:
        return None
    direction, distance_m, index = match
    delta_by_direction = {
        "left": (0.0, distance_m, 0.0),
        "right": (0.0, -distance_m, 0.0),
        "forward": (distance_m, 0.0, 0.0),
        "back": (-distance_m, 0.0, 0.0),
        "up": (0.0, 0.0, distance_m),
        "down": (0.0, 0.0, -distance_m),
    }
    return {
        "index": index,
        "type": "move_relative",
        "hand": hand,
        "direction": direction,
        "distance_m": distance_m,
        "delta": delta_by_direction[direction],
        "steps": max(1, steps),
    }


def _direction_distance_match(text: str) -> tuple[str, float, int] | None:
    direction_pattern = r"(?P<direction>右|左|前|後ろ|後|上|下|right|left|forward|backward|back|up|down)"
    number_pattern = r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>cm|㎝|センチ|m|メートル)?"
    after_direction = re.search(
        rf"{direction_pattern}\s*(?:方向)?\s*(?:へ|に|へと|まで|by|for)?\s*{number_pattern}",
        text,
    )
    if after_direction is not None:
        return (
            _normalize_direction(after_direction.group("direction")),
            _distance_to_meters(after_direction.group("number"), after_direction.group("unit")),
            after_direction.start(),
        )

    before_direction = re.search(
        rf"{number_pattern}\s*{direction_pattern}\s*(?:へ|に|方向)?",
        text,
    )
    if before_direction is not None:
        return (
            _normalize_direction(before_direction.group("direction")),
            _distance_to_meters(before_direction.group("number"), before_direction.group("unit")),
            before_direction.start(),
        )

    direction_only = re.search(
        rf"{direction_pattern}\s*(?:方向)?\s*(?:へ|に|へと)\s*(?:動|移動|move|ずら|shift)",
        text,
    )
    if direction_only is not None:
        return (_normalize_direction(direction_only.group("direction")), 0.05, direction_only.start())
    return None


def _detect_gripper_operation(text: str, *, hand: str) -> dict[str, object] | None:
    close_index = _first_index(text, ("閉", "握", "grip", "close"))
    open_index = _first_index(text, ("開", "open"))
    if close_index < 0 and open_index < 0:
        return None
    if open_index >= 0 and (close_index < 0 or open_index < close_index):
        return {
            "index": open_index,
            "type": "gripper",
            "hand": hand,
            "action": "open",
            "opening": GRIPPER_OPENING,
            "steps": 12,
        }
    return {
        "index": close_index,
        "type": "gripper",
        "hand": hand,
        "action": "close",
        "opening": GRIPPER_CLOSED,
        "steps": 12,
    }


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _normalize_direction(direction: str) -> str:
    if direction in {"右", "right"}:
        return "right"
    if direction in {"左", "left"}:
        return "left"
    if direction in {"前", "forward"}:
        return "forward"
    if direction in {"後", "後ろ", "back", "backward"}:
        return "back"
    if direction in {"上", "up"}:
        return "up"
    if direction in {"下", "down"}:
        return "down"
    raise ValueError(f"unsupported direction: {direction}")


def _distance_to_meters(number: str, unit: str | None) -> float:
    value = float(number)
    if unit in {"m", "メートル"}:
        return value
    if unit in {"cm", "㎝", "センチ", None}:
        return value / 100.0
    raise ValueError(f"unsupported distance unit: {unit}")


def _list3(values: Any) -> list[float]:
    return [float(values[0]), float(values[1]), float(values[2])]
