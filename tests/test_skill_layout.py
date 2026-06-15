from pathlib import Path


def test_robot_skill_has_required_frontmatter() -> None:
    skill_md = Path(".agents/skills/robot-aloha-mujoco/SKILL.md")
    content = skill_md.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert 'name: "robot-aloha-mujoco"' in content
    assert 'openclaw.tools.call("aloha_prompt_control"' in content
    assert 'openclaw.tools.call("aloha_mujoco_run"' in content
    assert "aloha_mujoco_live" in content
    assert "aloha_session_start" in content
    assert "aloha_move_relative" in content
    assert "openclaw.tools.run_skill" in content
    assert "references/robot_aloha.md" in content
    assert "scripts/live_aloha_agent_viewer.sh mujoco-agent-robot" in content
