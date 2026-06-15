from xml.etree import ElementTree

from nemoclaw2robot.models import SceneObjectSpec, TraceSegmentSpec
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


def test_scene_xml_can_append_agent_objects_and_traces() -> None:
    task = parse_prompt("Alohaのアームロボットでキューブを確認してください")
    xml = build_scene_xml(
        task,
        extra_objects=(
            SceneObjectSpec(
                name="paper",
                kind="paper",
                position=(0.0, -0.3, 0.003),
                size=(0.18, 0.12, 0.002),
                fixed=True,
            ),
        ),
        trace_segments=(
            TraceSegmentSpec(
                name="drawing_trace_0",
                from_pos=(0.0, -0.3, 0.01),
                to_pos=(0.04, -0.3, 0.01),
            ),
        ),
    )
    root = ElementTree.fromstring(xml)
    paper = root.find(".//*[@name='paper']")
    trace = root.find(".//*[@name='drawing_trace_0']")

    assert paper is not None
    assert paper.attrib["type"] == "box"
    assert paper.attrib["contype"] == "0"
    assert trace is not None
    assert trace.attrib["type"] == "capsule"
