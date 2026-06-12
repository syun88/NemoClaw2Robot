from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from nemoclaw2robot.models import RunArtifact, RunResult, TaskSpec
from nemoclaw2robot.scene import build_scene_xml
from nemoclaw2robot.simulator import AlohaMujocoController, MujocoUnavailableError


def run_prompt(
    task: TaskSpec,
    output_dir: Path,
    *,
    simulate: bool = True,
    strict_sim: bool = False,
) -> RunResult:
    output_dir.mkdir(parents=True, exist_ok=True)

    scene_xml = build_scene_xml(task)
    scene_path = output_dir / "scene.xml"
    plan_path = output_dir / "plan.json"
    trajectory_path = output_dir / "trajectory.json"
    summary_path = output_dir / "summary.md"

    scene_path.write_text(scene_xml, encoding="utf-8")
    plan_path.write_text(
        json.dumps(task.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    artifacts = [
        RunArtifact(path=str(scene_path), kind="mjcf_scene"),
        RunArtifact(path=str(plan_path), kind="task_plan"),
    ]
    warnings: list[str] = []
    simulated = False
    frames: list[dict[str, object]] = []

    if simulate:
        try:
            controller = AlohaMujocoController(scene_xml)
            frames = [frame.to_dict() for frame in controller.run_task(task)]
            trajectory_path.write_text(
                json.dumps(frames, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            artifacts.append(RunArtifact(path=str(trajectory_path), kind="trajectory"))
            simulated = True
        except MujocoUnavailableError as exc:
            if strict_sim:
                raise
            warnings.append(str(exc))

    summary_path.write_text(
        _summary_markdown(task, simulated=simulated, warnings=warnings, frame_count=len(frames)),
        encoding="utf-8",
    )
    artifacts.append(RunArtifact(path=str(summary_path), kind="summary"))

    return RunResult(
        output_dir=str(output_dir),
        task=task,
        simulated=simulated,
        artifacts=tuple(artifacts),
        warnings=tuple(warnings),
    )


def default_output_dir(root: Path = Path("artifacts/runs")) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return root / stamp


def _summary_markdown(
    task: TaskSpec,
    *,
    simulated: bool,
    warnings: list[str],
    frame_count: int,
) -> str:
    lines = [
        f"# NemoClaw2Robot Run: {task.task_id}",
        "",
        f"- Prompt: {task.prompt}",
        f"- Robot: {task.robot}",
        f"- Action: {task.action}",
        f"- Object: {task.object_name}",
        f"- Hand: {task.hand}",
        f"- Target: {task.target_name or 'none'}",
        f"- MuJoCo simulated: {'yes' if simulated else 'no'}",
        f"- Trajectory frames: {frame_count}",
    ]
    if warnings:
        lines.append("")
        lines.append("## Warnings")
        lines.extend(f"- {warning}" for warning in warnings)
    lines.append("")
    return "\n".join(lines)

