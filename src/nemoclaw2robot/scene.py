from __future__ import annotations

import copy
import os
from pathlib import Path
from xml.etree import ElementTree

from nemoclaw2robot.models import TaskSpec
from nemoclaw2robot.robots.aloha import (
    DEFAULT_CUBE_POSITION,
    DEFAULT_PUSH_END_POSITION,
    target_cube_position,
    target_pad_position,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MENAGERIE_ENV = "NEMOCLAW2ROBOT_MENAGERIE_ROOT"


class OfficialAlohaModelError(FileNotFoundError):
    """Raised when the official ALOHA MuJoCo model submodule is unavailable."""


def build_scene_xml(task: TaskSpec) -> str:
    """Build a task scene by loading the official MuJoCo Menagerie ALOHA MJCF."""

    aloha_dir = official_aloha_model_dir()
    root = _expanded_official_aloha_scene(aloha_dir)
    root.set("model", task.scene_name)

    _append_task_assets(root)
    _append_task_worldbody(root, task)
    _append_task_comments(root, task, aloha_dir)

    ElementTree.indent(root, space="  ")
    return ElementTree.tostring(root, encoding="unicode") + "\n"


def official_aloha_model_dir() -> Path:
    """Return the local directory containing the official ALOHA MJCF files."""

    override = os.environ.get(MENAGERIE_ENV)
    if override:
        candidate = Path(override).expanduser()
        if (candidate / "scene.xml").exists():
            aloha_dir = candidate
        else:
            aloha_dir = candidate / "aloha"
    else:
        aloha_dir = REPO_ROOT / "external" / "mujoco_menagerie" / "aloha"

    scene_path = aloha_dir / "scene.xml"
    robot_path = aloha_dir / "aloha.xml"
    assets_dir = aloha_dir / "assets"
    if not scene_path.exists() or not robot_path.exists() or not assets_dir.exists():
        raise OfficialAlohaModelError(
            "Official ALOHA MJCF model is missing. Run: "
            "git submodule update --init --recursive external/mujoco_menagerie"
        )
    return aloha_dir


def _expanded_official_aloha_scene(aloha_dir: Path) -> ElementTree.Element:
    root = ElementTree.parse(aloha_dir / "scene.xml").getroot()
    _configure_compiler(root, aloha_dir)

    for index, child in enumerate(list(root)):
        if child.tag == "include" and child.get("file") == "aloha.xml":
            root.remove(child)
            for offset, expanded_child in enumerate(_expanded_robot_children(aloha_dir)):
                root.insert(index + offset, expanded_child)
            break

    return root


def _expanded_robot_children(aloha_dir: Path) -> list[ElementTree.Element]:
    robot_root = ElementTree.parse(aloha_dir / "aloha.xml").getroot()
    children: list[ElementTree.Element] = []

    for child in list(robot_root):
        if child.tag == "compiler":
            continue
        if child.tag == "include":
            include_file = child.get("file")
            if include_file is None:
                continue
            include_root = ElementTree.parse(aloha_dir / include_file).getroot()
            children.extend(copy.deepcopy(grandchild) for grandchild in list(include_root))
            continue
        children.append(copy.deepcopy(child))

    return children


def _configure_compiler(root: ElementTree.Element, aloha_dir: Path) -> None:
    compiler = root.find("compiler")
    if compiler is None:
        compiler = ElementTree.Element("compiler")
        root.insert(0, compiler)

    assets_dir = str((aloha_dir / "assets").resolve())
    compiler.set("meshdir", assets_dir)
    compiler.set("texturedir", assets_dir)
    compiler.set("angle", "radian")
    compiler.set("autolimits", "true")


def _append_task_assets(root: ElementTree.Element) -> None:
    asset = root.find("asset")
    if asset is None:
        asset = ElementTree.SubElement(root, "asset")

    _ensure_material(asset, "task_cube_mat", "0.9 0.12 0.08 1")
    _ensure_material(asset, "task_target_mat", "0.05 0.45 0.85 0.45")
    _ensure_material(asset, "task_push_mat", "0.05 0.70 0.20 0.35")


def _ensure_material(asset: ElementTree.Element, name: str, rgba: str) -> None:
    if asset.find(f".//material[@name='{name}']") is not None:
        return
    ElementTree.SubElement(asset, "material", {"name": name, "rgba": rgba})


def _append_task_worldbody(root: ElementTree.Element, task: TaskSpec) -> None:
    worldbody = ElementTree.Element("worldbody")

    target_pos = target_pad_position(task.hand)
    cube_pos = DEFAULT_CUBE_POSITION
    push_end_pos = DEFAULT_PUSH_END_POSITION

    ElementTree.SubElement(
        worldbody,
        "geom",
        {
            "name": "target_pad",
            "type": "cylinder",
            "pos": _vec(target_pos),
            "size": "0.075 0.006",
            "material": "task_target_mat",
            "contype": "0",
            "conaffinity": "0",
        },
    )
    ElementTree.SubElement(
        worldbody,
        "site",
        {
            "name": "target_pad_site",
            "pos": _vec(target_cube_position(task.hand)),
            "size": "0.018",
            "rgba": "0.05 0.45 0.85 1",
        },
    )
    ElementTree.SubElement(
        worldbody,
        "site",
        {
            "name": "push_lane_end_site",
            "pos": _vec(push_end_pos),
            "size": "0.018",
            "rgba": "0.05 0.70 0.20 1",
        },
    )
    ElementTree.SubElement(
        worldbody,
        "geom",
        {
            "name": "push_lane",
            "type": "capsule",
            "fromto": f"{cube_pos[0]:.4g} {cube_pos[1]:.4g} 0.012 {push_end_pos[0]:.4g} {push_end_pos[1]:.4g} 0.012",
            "size": "0.012",
            "material": "task_push_mat",
            "contype": "0",
            "conaffinity": "0",
        },
    )

    cube = ElementTree.SubElement(worldbody, "body", {"name": "cube", "pos": _vec(cube_pos)})
    ElementTree.SubElement(cube, "freejoint", {"name": "cube_free"})
    object_geom = _object_geom_attributes(task.object_name)
    ElementTree.SubElement(
        cube,
        "geom",
        {
            "name": "cube_geom",
            "mass": "0.05",
            "material": "task_cube_mat",
            **object_geom,
        },
    )
    ElementTree.SubElement(
        cube,
        "site",
        {
            "name": "cube_site",
            "pos": "0 0 0",
            "size": "0.012",
            "rgba": "1 1 1 1",
        },
    )

    root.append(worldbody)


def _append_task_comments(root: ElementTree.Element, task: TaskSpec, aloha_dir: Path) -> None:
    root.append(ElementTree.Comment(f" official ALOHA MJCF source: {aloha_dir / 'scene.xml'} "))
    root.append(ElementTree.Comment(f" prompt: {task.prompt} "))
    root.append(
        ElementTree.Comment(
            f" normalized task: action={task.action}, object={task.object_name}, "
            f"hand={task.hand}, target={task.target_name} "
        )
    )


def _object_geom_attributes(object_name: str) -> dict[str, str]:
    if object_name == "sphere":
        return {
            "type": "sphere",
            "size": "0.04",
        }
    return {
        "type": "box",
        "size": "0.035 0.035 0.035",
    }


def _vec(values: tuple[float, float, float]) -> str:
    return " ".join(f"{value:.4g}" for value in values)
