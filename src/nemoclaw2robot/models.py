from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

ActionName = Literal["grasp", "place", "push", "inspect"]
ArmName = Literal["left", "right", "auto"]
SceneObjectKind = Literal["cube", "sphere", "cylinder", "paper", "marker"]


@dataclass(frozen=True)
class TaskSpec:
    """A normalized robot task derived from a user prompt."""

    prompt: str
    robot: str = "aloha"
    action: ActionName = "grasp"
    object_name: str = "cube"
    hand: ArmName = "right"
    target_name: str | None = None
    task_id: str = "task"
    scene_name: str = "aloha_prompt_scene"
    build_scene: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RobotArmSpec:
    name: str
    joints: tuple[str, ...]
    gripper_site: str
    home_qpos: tuple[float, ...]


@dataclass(frozen=True)
class RobotSpec:
    name: str
    description: str
    arms: dict[str, RobotArmSpec]
    default_hand: str = "right"
    coordinate_frame: str = "x forward, y left, z up"
    workspace_notes: tuple[str, ...] = field(default_factory=tuple)

    def arm(self, name: str) -> RobotArmSpec:
        return self.arms[name]


@dataclass(frozen=True)
class SceneObjectSpec:
    """A simple project-side object appended to the generated MuJoCo scene."""

    name: str
    kind: SceneObjectKind
    position: tuple[float, float, float]
    size: tuple[float, ...]
    rgba: tuple[float, float, float, float] = (0.8, 0.2, 0.1, 1.0)
    fixed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TraceSegmentSpec:
    """A non-colliding visual segment for drawing/path traces."""

    name: str
    from_pos: tuple[float, float, float]
    to_pos: tuple[float, float, float]
    radius: float = 0.004
    rgba: tuple[float, float, float, float] = (0.05, 0.05, 0.05, 1.0)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RunArtifact:
    path: str
    kind: str


@dataclass(frozen=True)
class RunResult:
    output_dir: str
    task: TaskSpec
    simulated: bool
    artifacts: tuple[RunArtifact, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["task"] = self.task.to_dict()
        return result
