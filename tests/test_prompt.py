from nemoclaw2robot.prompt import parse_prompt


def test_parse_japanese_grasp_prompt() -> None:
    task = parse_prompt("Alohaのアームロボットでキューブを掴んでください")

    assert task.robot == "aloha"
    assert task.action == "grasp"
    assert task.object_name == "cube"
    assert task.hand == "right"
    assert task.target_name is None


def test_parse_japanese_place_prompt() -> None:
    task = parse_prompt("Alohaでキューブを目標位置に置いてください")

    assert task.action == "place"
    assert task.target_name == "target_pad"


def test_parse_push_prompt() -> None:
    task = parse_prompt("Use ALOHA to push the cube")

    assert task.action == "push"
    assert task.target_name == "push_lane_end"


def test_parse_japanese_sphere_prompt() -> None:
    task = parse_prompt("Alohaのアームロボットで球体を掴んでください")

    assert task.action == "grasp"
    assert task.object_name == "sphere"
