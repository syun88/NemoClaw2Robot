import json

from nemoclaw2robot.cli import build_parser, main


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


def test_cli_session_help_is_registered() -> None:
    parser = build_parser()

    help_text = parser.format_help()
    assert "prompt-control" in help_text
    assert "session-move-relative" in help_text
    assert "session-add-object" in help_text
    assert "session-cartesian-path" in help_text
