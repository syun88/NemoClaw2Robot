import json
from pathlib import Path


PLUGIN_DIR = Path("openclaw-plugins/aloha-mujoco")


def test_openclaw_plugin_manifest_registers_robot_tools() -> None:
    manifest = json.loads((PLUGIN_DIR / "openclaw.plugin.json").read_text(encoding="utf-8"))

    assert manifest["id"] == "aloha-mujoco"
    assert manifest["enabledByDefault"] is True
    assert manifest["contracts"]["tools"] == [
        "aloha_mujoco_plan",
        "aloha_mujoco_run",
        "aloha_mujoco_live",
    ]
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
    assert 'default: "queue"' in entry
    assert "enqueueLiveRequest" in entry
    assert 'api.registerTool(createPlanTool(api))' in entry
    assert 'api.registerTool(createRunTool(api))' in entry
    assert 'api.registerTool(createLiveTool(api))' in entry


def test_robot_skill_prefers_openclaw_tool() -> None:
    skill = Path(".agents/skills/robot-aloha-mujoco/SKILL.md").read_text(encoding="utf-8")

    assert "prefer the OpenClaw tool `aloha_mujoco_live`" in skill
    assert "Otherwise prefer the OpenClaw tool `aloha_mujoco_run`" in skill
    assert 'openclaw.tools.call("aloha_mujoco_run"' in skill
    assert 'openclaw.tools.call("aloha_mujoco_live"' in skill
    assert "scripts/live_aloha_agent_viewer.sh mujoco-agent-robot" in skill
    assert "openclaw.tools.readSkill" in skill
    assert "live/watch prompts by calling `aloha_mujoco_live`" in skill
