import json

from nemoclaw2robot.cli import main


def test_cli_plan_prints_json(capsys) -> None:
    exit_code = main(
        [
            "plan",
            "--prompt",
            "Alohaのアームロボットでキューブを掴んでください",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["action"] == "grasp"
    assert payload["robot"] == "aloha"
