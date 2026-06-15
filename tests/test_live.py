from nemoclaw2robot.live import _extract_live_prompt_from_message, _is_live_aloha_prompt, _use_prompt_control_live


def test_live_auto_uses_prompt_control_for_relative_move() -> None:
    assert _use_prompt_control_live("リアルタイムで右アームを右に10cm動かしてください")


def test_live_auto_keeps_fixed_grasp_demo_on_demo_path() -> None:
    assert not _use_prompt_control_live("リアルタイムでAlohaのアームロボットがキューブを掴むところを見たい")


def test_live_control_mode_does_not_break_fixed_grasp_demo() -> None:
    assert not _use_prompt_control_live("Alohaのアームロボットでキューブを掴んでください", mode="control")


def test_live_control_mode_uses_prompt_control_for_relative_move() -> None:
    assert _use_prompt_control_live("右アームを右に10cm動かしてください", mode="control")


def test_session_prompt_fallback_detects_live_aloha_prompt() -> None:
    item = {
        "type": "message",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "リアルタイムでAlohaのアームロボットがキューブを掴むところを見たい",
                }
            ],
        },
    }

    assert _extract_live_prompt_from_message(item) == "リアルタイムでAlohaのアームロボットがキューブを掴むところを見たい"


def test_session_prompt_fallback_detects_string_content_prompt() -> None:
    item = {
        "type": "message",
        "message": {
            "role": "user",
            "content": "リアルタイムで右アームを右に10cm動かしてください",
        },
    }

    assert _extract_live_prompt_from_message(item) == "リアルタイムで右アームを右に10cm動かしてください"


def test_session_prompt_fallback_ignores_non_live_prompt() -> None:
    assert not _is_live_aloha_prompt("Alohaのアームロボットでキューブを掴んでください")


def test_session_prompt_fallback_ignores_tool_search_debug_prompt() -> None:
    assert not _is_live_aloha_prompt(
        'tool_search_code を使って return await openclaw.tools.search("aloha_mujoco_live");'
    )
