from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from nemoclaw2robot.models import TaskSpec
from nemoclaw2robot.robots.aloha import (
    ALOHA_SPEC,
    DEFAULT_CUBE_POSITION,
    DEFAULT_PUSH_END_POSITION,
    target_cube_position,
)


class MujocoUnavailableError(RuntimeError):
    """Raised when the optional MuJoCo dependency is not installed."""


FrameCallback = Callable[["TrajectoryFrame", "AlohaMujocoController"], None]
GRIPPER_OPENING = 0.037
GRIPPER_CLOSED = 0.002


@dataclass(frozen=True)
class TrajectoryFrame:
    step: int
    phase: str
    gripper: tuple[float, float, float]
    cube: tuple[float, float, float]
    gripper_opening: float

    def to_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "phase": self.phase,
            "gripper": list(self.gripper),
            "cube": list(self.cube),
            "gripper_opening": self.gripper_opening,
        }


class AlohaMujocoController:
    """Small scripted controller for the generated ALOHA MJCF scene."""

    def __init__(self, scene_xml: str, frame_callback: FrameCallback | None = None):
        try:
            import mujoco
        except ModuleNotFoundError as exc:
            raise MujocoUnavailableError(
                "MuJoCo is not installed. Install with: pip install -e '.[sim]'"
            ) from exc

        self.mujoco: Any = mujoco
        self.model = mujoco.MjModel.from_xml_string(scene_xml)
        self.data = mujoco.MjData(self.model)
        self.frames: list[TrajectoryFrame] = []
        self.frame_callback = frame_callback
        self._step = 0

    def reset(self, *, clear_frames: bool = False) -> None:
        if clear_frames:
            self.frames.clear()
            self._step = 0
        if self.model.nkey:
            self.mujoco.mj_resetDataKeyframe(self.model, self.data, 0)
        else:
            self.mujoco.mj_resetData(self.model, self.data)
        for arm in ALOHA_SPEC.arms.values():
            for joint_name, value in zip(arm.joints, arm.home_qpos, strict=True):
                self._set_joint_qpos(joint_name, value)
            self._set_gripper(arm.name, GRIPPER_OPENING)
        self._set_cube_position(np.array(DEFAULT_CUBE_POSITION, dtype=float))
        self.data.qvel[:] = 0
        self.mujoco.mj_forward(self.model, self.data)

    def run_task(self, task: TaskSpec) -> list[TrajectoryFrame]:
        self.reset(clear_frames=True)
        hand = task.hand if task.hand != "auto" else ALOHA_SPEC.default_hand

        if task.action == "inspect":
            self._record(hand, "inspect")
            return self.frames
        if task.action == "push":
            self._push_cube(hand)
            return self.frames

        place_after_grasp = task.action == "place"
        self._grasp_cube(hand, place_after_grasp=place_after_grasp)
        return self.frames

    def _grasp_cube(self, hand: str, place_after_grasp: bool) -> None:
        cube = np.array(DEFAULT_CUBE_POSITION, dtype=float)
        approach = cube + np.array([0.0, 0.0, 0.18])
        pregrasp = cube + np.array([0.0, 0.0, 0.075])
        lift = cube + np.array([0.0, 0.0, 0.22])
        target = np.array(target_cube_position(hand), dtype=float) + np.array([0.0, 0.0, 0.06])

        self._animate_gripper(hand, GRIPPER_OPENING, "open_gripper", steps=12)
        self._move_to(hand, approach, "approach", steps=35)
        self._move_to(hand, pregrasp, "pregrasp", steps=30)
        self._move_to(hand, cube + np.array([0.0, 0.0, 0.045]), "align_gripper", steps=20)
        self._animate_gripper(hand, GRIPPER_CLOSED, "close_gripper", steps=18)
        self._record(hand, "grasp")
        self._move_to(hand, lift, "lift", steps=35, attached=True)
        if place_after_grasp:
            self._move_to(hand, target, "transfer", steps=45, attached=True)
            self._set_cube_position(target + np.array([0.0, 0.0, -0.045]))
            self._animate_gripper(hand, GRIPPER_OPENING, "release_gripper", steps=18)
            self._record(hand, "place")

    def _push_cube(self, hand: str) -> None:
        cube = np.array(DEFAULT_CUBE_POSITION, dtype=float)
        push_end = np.array(DEFAULT_PUSH_END_POSITION, dtype=float)
        start = cube + np.array([0.0, 0.12, 0.045])
        contact = cube + np.array([0.0, 0.045, 0.045])
        finish = push_end + np.array([0.0, 0.0, 0.045])

        self._set_gripper(hand, GRIPPER_OPENING)
        self._move_to(hand, start, "approach_push", steps=35)
        self._move_to(hand, contact, "contact_push", steps=25)
        self._move_to(hand, finish, "push", steps=45, move_cube_to=push_end)

    def _animate_gripper(self, hand: str, target_opening: float, phase: str, steps: int) -> None:
        start = self._gripper_opening(hand)
        for index in range(steps):
            alpha = (index + 1) / steps
            opening = float(start * (1.0 - alpha) + target_opening * alpha)
            self._set_gripper(hand, opening)
            self.data.qvel[:] = 0
            self.mujoco.mj_forward(self.model, self.data)
            self._record(hand, phase)

    def _move_to(
        self,
        hand: str,
        target: np.ndarray,
        phase: str,
        steps: int,
        attached: bool = False,
        move_cube_to: np.ndarray | None = None,
    ) -> None:
        start_cube = self._cube_position()
        for index in range(steps):
            self._solve_ik(hand, target)
            if attached:
                self._set_cube_position(self._site_position(ALOHA_SPEC.arm(hand).gripper_site) + np.array([0.0, 0.0, -0.045]))
            elif move_cube_to is not None:
                alpha = (index + 1) / steps
                self._set_cube_position(start_cube * (1.0 - alpha) + move_cube_to * alpha)
            self.data.qvel[:] = 0
            self.mujoco.mj_forward(self.model, self.data)
            self._record(hand, phase)

    def _solve_ik(self, hand: str, target: np.ndarray, iterations: int = 8) -> None:
        arm = ALOHA_SPEC.arm(hand)
        site_id = self._site_id(arm.gripper_site)
        joint_ids = [self._joint_id(name) for name in arm.joints]
        dof_ids = [int(self.model.jnt_dofadr[joint_id]) for joint_id in joint_ids]
        qpos_ids = [int(self.model.jnt_qposadr[joint_id]) for joint_id in joint_ids]

        for _ in range(iterations):
            self.mujoco.mj_forward(self.model, self.data)
            current = self.data.site_xpos[site_id].copy()
            error = target - current
            if float(np.linalg.norm(error)) < 0.006:
                break

            jacp = np.zeros((3, self.model.nv))
            jacr = np.zeros((3, self.model.nv))
            self.mujoco.mj_jacSite(self.model, self.data, jacp, jacr, site_id)
            jac = jacp[:, dof_ids]
            damping = 0.002
            delta = jac.T @ np.linalg.solve(jac @ jac.T + damping * np.eye(3), error)
            delta = np.clip(delta, -0.08, 0.08)

            for joint_id, qpos_id, dq in zip(joint_ids, qpos_ids, delta, strict=True):
                self.data.qpos[qpos_id] = self._clamped_joint_value(joint_id, self.data.qpos[qpos_id] + dq)

    def _record(self, hand: str, phase: str) -> None:
        gripper = tuple(float(v) for v in self._site_position(ALOHA_SPEC.arm(hand).gripper_site))
        cube = tuple(float(v) for v in self._cube_position())
        frame = TrajectoryFrame(
            step=self._step,
            phase=phase,
            gripper=gripper,
            cube=cube,
            gripper_opening=self._gripper_opening(hand),
        )
        self.frames.append(frame)
        self._step += 1
        if self.frame_callback is not None:
            self.frame_callback(frame, self)

    def _set_joint_qpos(self, joint_name: str, value: float) -> None:
        joint_id = self._joint_id(joint_name)
        qpos_id = int(self.model.jnt_qposadr[joint_id])
        self.data.qpos[qpos_id] = self._clamped_joint_value(joint_id, value)

    def _set_gripper(self, hand: str, opening: float) -> None:
        for joint_name in self._gripper_joint_names(hand):
            self._set_joint_qpos(joint_name, opening)

        actuator_id = self.mujoco.mj_name2id(
            self.model,
            self.mujoco.mjtObj.mjOBJ_ACTUATOR,
            f"{hand}/gripper",
        )
        if actuator_id >= 0:
            low, high = self.model.actuator_ctrlrange[actuator_id]
            self.data.ctrl[actuator_id] = float(np.clip(opening, low, high))

    def _gripper_opening(self, hand: str) -> float:
        joint_id = self._joint_id(f"{hand}/left_finger")
        qpos_id = int(self.model.jnt_qposadr[joint_id])
        return float(self.data.qpos[qpos_id])

    def _gripper_joint_names(self, hand: str) -> tuple[str, str]:
        return (f"{hand}/left_finger", f"{hand}/right_finger")

    def _clamped_joint_value(self, joint_id: int, value: float) -> float:
        if int(self.model.jnt_limited[joint_id]) == 0:
            return float(value)
        low, high = self.model.jnt_range[joint_id]
        return float(np.clip(value, low, high))

    def _set_cube_position(self, position: np.ndarray) -> None:
        joint_id = self._joint_id("cube_free")
        qpos_id = int(self.model.jnt_qposadr[joint_id])
        self.data.qpos[qpos_id : qpos_id + 3] = position
        self.data.qpos[qpos_id + 3 : qpos_id + 7] = np.array([1.0, 0.0, 0.0, 0.0])

    def _cube_position(self) -> np.ndarray:
        joint_id = self._joint_id("cube_free")
        qpos_id = int(self.model.jnt_qposadr[joint_id])
        return self.data.qpos[qpos_id : qpos_id + 3].copy()

    def _site_position(self, site_name: str) -> np.ndarray:
        return self.data.site_xpos[self._site_id(site_name)].copy()

    def _joint_id(self, joint_name: str) -> int:
        joint_id = self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint_id < 0:
            raise KeyError(f"Joint not found in MuJoCo model: {joint_name}")
        return int(joint_id)

    def _site_id(self, site_name: str) -> int:
        site_id = self.mujoco.mj_name2id(self.model, self.mujoco.mjtObj.mjOBJ_SITE, site_name)
        if site_id < 0:
            raise KeyError(f"Site not found in MuJoCo model: {site_name}")
        return int(site_id)
