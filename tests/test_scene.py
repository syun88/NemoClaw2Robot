from xml.etree import ElementTree

from nemoclaw2robot.prompt import parse_prompt
from nemoclaw2robot.scene import build_scene_xml


def test_scene_xml_contains_aloha_task_entities() -> None:
    task = parse_prompt("Alohaのアームロボットでキューブを掴んでください")
    xml = build_scene_xml(task)
    root = ElementTree.fromstring(xml)

    assert root.tag == "mujoco"
    assert root.attrib["model"] == task.scene_name
    assert root.find(".//*[@name='cube']") is not None
    assert root.find(".//*[@name='right/gripper']") is not None
    assert root.find(".//*[@name='left/gripper']") is not None
    assert root.find(".//*[@name='target_pad']") is not None
    assert root.find(".//*[@name='right/waist']") is not None


def test_scene_xml_embeds_task_comment_text() -> None:
    task = parse_prompt("grab the cube with the left ALOHA arm")
    xml = build_scene_xml(task)

    assert "action=grasp" in xml
    assert "hand=left" in xml
    assert "official ALOHA MJCF source" in xml


def test_scene_xml_uses_sphere_geom_when_prompt_requests_sphere() -> None:
    task = parse_prompt("Alohaのアームロボットで球体を掴んでください")
    xml = build_scene_xml(task)
    root = ElementTree.fromstring(xml)
    geom = root.find(".//*[@name='cube_geom']")

    assert task.object_name == "sphere"
    assert geom is not None
    assert geom.attrib["type"] == "sphere"
