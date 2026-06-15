from nemoclaw2robot.session import _plan_prompt_control


def test_prompt_control_plans_right_arm_relative_move() -> None:
    plan = _plan_prompt_control("右アームを右に10cm動かしてください")

    assert plan["hand"] == "right"
    operation = plan["operations"][0]
    assert operation["type"] == "move_relative"
    assert operation["hand"] == "right"
    assert operation["direction"] == "right"
    assert operation["delta"] == (0.0, -0.10, 0.0)


def test_prompt_control_plans_move_then_gripper() -> None:
    plan = _plan_prompt_control("右アームを上に5cm動かしてからグリッパーを閉じてください")

    assert [operation["type"] for operation in plan["operations"]] == ["move_relative", "gripper"]
    assert plan["operations"][0]["delta"] == (0.0, 0.0, 0.05)
    assert plan["operations"][1]["action"] == "close"


def test_prompt_control_plans_paper_and_drawing_trace() -> None:
    plan = _plan_prompt_control("MuJoCo上に紙を置いて、右アームで簡単な線を描く動作をしてください")

    assert [operation["type"] for operation in plan["operations"]] == ["add_object", "draw_trace"]
    assert plan["operations"][0]["kind"] == "paper"
    assert plan["operations"][1]["hand"] == "right"
