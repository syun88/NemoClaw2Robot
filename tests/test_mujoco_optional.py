import importlib.util
import json

import pytest

from nemoclaw2robot.prompt import parse_prompt
from nemoclaw2robot.runner import run_prompt


@pytest.mark.skipif(importlib.util.find_spec("mujoco") is None, reason="MuJoCo is optional")
def test_mujoco_controller_generates_trajectory(tmp_path) -> None:
    task = parse_prompt("Alohaのアームロボットでキューブを掴んでください")
    result = run_prompt(task, tmp_path, simulate=True, strict_sim=True)

    assert result.simulated is True
    assert (tmp_path / "trajectory.json").exists()


@pytest.mark.skipif(importlib.util.find_spec("mujoco") is None, reason="MuJoCo is optional")
def test_mujoco_controller_animates_gripper(tmp_path) -> None:
    task = parse_prompt("Alohaのアームロボットでキューブを掴んでください")
    run_prompt(task, tmp_path, simulate=True, strict_sim=True)

    frames = json.loads((tmp_path / "trajectory.json").read_text(encoding="utf-8"))
    phases = {frame["phase"] for frame in frames}
    openings = [frame["gripper_opening"] for frame in frames]

    assert "open_gripper" in phases
    assert "close_gripper" in phases
    assert max(openings) > 0.03
    assert min(openings) < 0.01
