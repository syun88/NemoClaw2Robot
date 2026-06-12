from __future__ import annotations

from nemoclaw2robot.models import RobotArmSpec, RobotSpec

RIGHT_ARM_JOINTS = (
    "right/waist",
    "right/shoulder",
    "right/elbow",
    "right/forearm_roll",
    "right/wrist_angle",
    "right/wrist_rotate",
)

LEFT_ARM_JOINTS = (
    "left/waist",
    "left/shoulder",
    "left/elbow",
    "left/forearm_roll",
    "left/wrist_angle",
    "left/wrist_rotate",
)

DEFAULT_CUBE_POSITION = (0.0, -0.30, 0.035)
DEFAULT_PUSH_END_POSITION = (0.0, -0.48, 0.035)

ALOHA_SPEC = RobotSpec(
    name="aloha",
    description="Official MuJoCo Menagerie ALOHA 2 dual-arm MJCF model for prompt-driven task scaffolding.",
    default_hand="right",
    arms={
        "right": RobotArmSpec(
            name="right",
            joints=RIGHT_ARM_JOINTS,
            gripper_site="right/gripper",
            home_qpos=(0.0, -0.96, 1.16, 0.0, -0.3, 0.0),
        ),
        "left": RobotArmSpec(
            name="left",
            joints=LEFT_ARM_JOINTS,
            gripper_site="left/gripper",
            home_qpos=(0.0, -0.96, 1.16, 0.0, -0.3, 0.0),
        ),
    },
    workspace_notes=(
        "Official ALOHA 2 scene comes from google-deepmind/mujoco_menagerie.",
        "Default table top is the official Menagerie table, with the work surface near z=0.",
        "Default cube center is at x=0.0, y=-0.30, z=0.035.",
        "Default push endpoint is at x=0.0, y=-0.48, z=0.035.",
    ),
)


def target_pad_position(hand: str) -> tuple[float, float, float]:
    x = -0.18 if hand == "left" else 0.18
    return (x, -0.22, 0.006)


def target_cube_position(hand: str) -> tuple[float, float, float]:
    x, y, _ = target_pad_position(hand)
    return (x, y, 0.047)
