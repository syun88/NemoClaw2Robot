import json
from pathlib import Path


PLUGIN_DIR = Path("openclaw-plugins/aloha-mujoco")
EXPECTED_TOOLS = [
    "aloha_mujoco_plan",
    "aloha_mujoco_run",
    "aloha_mujoco_live",
    "aloha_prompt_control",
    "aloha_session_start",
    "aloha_get_state",
    "aloha_solve_ik",
    "aloha_move_relative",
    "aloha_move_to_pose",
    "aloha_execute_cartesian_path",
    "aloha_set_gripper",
    "aloha_add_object",
    "aloha_add_trace",
    "aloha_check_pose",
    "aloha_check_contacts",
]


def test_openclaw_plugin_manifest_registers_robot_tools() -> None:
    manifest = json.loads((PLUGIN_DIR / "openclaw.plugin.json").read_text(encoding="utf-8"))

    assert manifest["id"] == "aloha-mujoco"
    assert manifest["enabledByDefault"] is True
    assert manifest["contracts"]["tools"] == EXPECTED_TOOLS
    assert manifest["configSchema"]["properties"]["liveViewerUrl"]["default"] == "http://host.docker.internal:8765"


def test_openclaw_plugin_package_declares_extension_entry() -> None:
    package = json.loads((PLUGIN_DIR / "package.json").read_text(encoding="utf-8"))

    assert package["type"] == "module"
    assert package["openclaw"]["extensions"] == ["./index.js"]


def test_openclaw_plugin_entry_matches_manifest_tools() -> None:
    entry = (PLUGIN_DIR / "index.js").read_text(encoding="utf-8")

    assert 'name: "aloha_mujoco_plan"' in entry
    assert 'name: "aloha_mujoco_run"' in entry
    assert 'name: "aloha_mujoco_live"' in entry
    assert 'name: "aloha_prompt_control"' in entry
    for tool_name in EXPECTED_TOOLS:
        assert f'name: "{tool_name}"' in entry
    assert 'default: "queue"' in entry
    assert "enqueueLiveRequest" in entry
    assert 'api.registerTool(createPlanTool(api))' in entry
    assert 'api.registerTool(createRunTool(api))' in entry
    assert 'api.registerTool(createLiveTool(api))' in entry
    assert 'api.registerTool(createPromptControlTool(api))' in entry
    assert 'api.registerTool(createSessionStartTool(api))' in entry
    assert 'api.registerTool(createMoveRelativeTool(api))' in entry
    assert "isLivePrompt" in entry
    assert 'requested_by: "aloha_prompt_control"' in entry


def test_robot_skill_prefers_openclaw_tool() -> None:
    skill = Path(".agents/skills/robot-aloha-mujoco/SKILL.md").read_text(encoding="utf-8")

    assert "first call the OpenClaw tool `aloha_mujoco_live`" in skill
    assert 'mode: "control"' in skill
    assert 'openclaw.tools.call("aloha_prompt_control"' in skill
    assert 'openclaw.tools.call("aloha_mujoco_run"' in skill
    assert 'openclaw.tools.call("aloha_mujoco_live"' in skill
    assert "scripts/live_aloha_agent_viewer.sh mujoco-agent-robot" in skill
    assert "openclaw.tools.readSkill" in skill
    assert "control prompts by calling `aloha_prompt_control`" in skill
