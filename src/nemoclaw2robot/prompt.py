from __future__ import annotations

import hashlib
import re

from nemoclaw2robot.models import ActionName, ArmName, TaskSpec

_GRASP_WORDS = (
    "grab",
    "grasp",
    "pick",
    "pick up",
    "catch",
    "つか",
    "掴",
    "把持",
    "持ち上げ",
)
_PLACE_WORDS = (
    "place",
    "put",
    "move",
    "transfer",
    "drop",
    "置",
    "移動",
    "運",
    "入れ",
)
_PUSH_WORDS = (
    "push",
    "slide",
    "押",
    "スライド",
)
_INSPECT_WORDS = (
    "inspect",
    "look",
    "observe",
    "確認",
    "見る",
    "観察",
)
_CUBE_WORDS = (
    "cube",
    "block",
    "box",
    "キューブ",
    "ブロック",
    "箱",
)
_SPHERE_WORDS = (
    "sphere",
    "ball",
    "orb",
    "球体",
    "球",
    "ボール",
)
_LEFT_WORDS = ("left", "左")
_RIGHT_WORDS = ("right", "右")
_TARGET_WORDS = (
    "target",
    "goal",
    "pad",
    "bin",
    "basket",
    "目標",
    "ゴール",
    "場所",
    "箱",
    "トレー",
)


def parse_prompt(prompt: str, robot_hint: str = "aloha") -> TaskSpec:
    """Convert a Japanese or English robot prompt into a conservative task spec."""

    normalized = _normalize(prompt)
    action = _detect_action(normalized)
    hand = _detect_hand(normalized)
    object_name = _detect_object(normalized)
    target_name = _detect_target(normalized, action)
    task_id = _task_id(prompt, action, object_name)

    return TaskSpec(
        prompt=prompt.strip(),
        robot=robot_hint,
        action=action,
        object_name=object_name,
        hand=hand,
        target_name=target_name,
        task_id=task_id,
        scene_name=f"{robot_hint}_{action}_{object_name}_scene",
    )


def _normalize(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.strip().lower())


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _detect_action(text: str) -> ActionName:
    has_grasp = _has_any(text, _GRASP_WORDS)
    has_place = _has_any(text, _PLACE_WORDS)

    if _has_any(text, _PUSH_WORDS):
        return "push"
    if has_grasp and has_place:
        return "place"
    if has_grasp:
        return "grasp"
    if has_place:
        return "place"
    if _has_any(text, _INSPECT_WORDS):
        return "inspect"
    return "grasp"


def _detect_hand(text: str) -> ArmName:
    if _has_any(text, _LEFT_WORDS):
        return "left"
    if _has_any(text, _RIGHT_WORDS):
        return "right"
    return "right"


def _detect_object(text: str) -> str:
    if _has_any(text, _SPHERE_WORDS):
        return "sphere"
    if _has_any(text, _CUBE_WORDS):
        return "cube"
    return "cube"


def _detect_target(text: str, action: ActionName) -> str | None:
    if action == "place" or _has_any(text, _TARGET_WORDS):
        return "target_pad"
    if action == "push":
        return "push_lane_end"
    return None


def _task_id(prompt: str, action: str, object_name: str) -> str:
    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
    return f"{action}_{object_name}_{digest}"
