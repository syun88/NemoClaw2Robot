from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from nemoclaw2robot.prompt import parse_prompt
from nemoclaw2robot.robots.aloha import ALOHA_SPEC
from nemoclaw2robot.runner import default_output_dir, run_prompt
from nemoclaw2robot.scene import build_scene_xml


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-robots":
        print(json.dumps({"robots": [ALOHA_SPEC.name]}, indent=2))
        return 0
    if args.command == "plan":
        task = parse_prompt(args.prompt, robot_hint=args.robot)
        print(json.dumps(task.to_dict(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "scene":
        task = parse_prompt(args.prompt, robot_hint=args.robot)
        xml = build_scene_xml(task)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(xml, encoding="utf-8")
            print(output)
        else:
            print(xml)
        return 0
    if args.command == "run":
        task = parse_prompt(args.prompt, robot_hint=args.robot)
        output_dir = Path(args.output) if args.output else default_output_dir()
        result = run_prompt(
            task,
            output_dir,
            simulate=not args.no_sim,
            strict_sim=args.strict_sim,
        )
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "view":
        task = parse_prompt(args.prompt, robot_hint=args.robot)
        if sys.platform == "darwin" and os.environ.get("NEMOCLAW2ROBOT_MJPYTHON") != "1":
            from nemoclaw2robot.viewer import macos_viewer_command

            print(
                "macOS native MuJoCo viewer is most reliable through mjpython. "
                "If the window does not open, rerun:\n"
                f"{macos_viewer_command(args.prompt, fps=args.fps)}",
                file=sys.stderr,
            )
        from nemoclaw2robot.viewer import view_prompt

        result = view_prompt(
            task,
            fps=args.fps,
            camera=None if args.camera.lower() == "none" else args.camera,
            loop=args.loop,
            keep_open=not args.no_keep_open,
            scene_output=Path(args.scene_output) if args.scene_output else None,
        )
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "live":
        if sys.platform == "darwin" and os.environ.get("NEMOCLAW2ROBOT_MJPYTHON") != "1":
            executable = Path(sys.executable)
            mjpython = executable.with_name("mjpython")
            runner = str(mjpython if mjpython.exists() else executable)

            print(
                "macOS native MuJoCo viewer is most reliable through mjpython. "
                "If the window does not open, rerun:\n"
                f"{runner} -m nemoclaw2robot.cli live --host {args.host} --port {args.port} --fps {args.fps:g}",
                file=sys.stderr,
            )
        from nemoclaw2robot.live import LiveViewerBridge

        bridge = LiveViewerBridge(
            host=args.host,
            port=args.port,
            fps=args.fps,
            camera=None if args.camera.lower() == "none" else args.camera,
            hold_seconds=args.hold_seconds,
        )
        bridge.serve_forever()
        return 0
    if args.command == "live-agent":
        if sys.platform == "darwin" and os.environ.get("NEMOCLAW2ROBOT_MJPYTHON") != "1":
            executable = Path(sys.executable)
            mjpython = executable.with_name("mjpython")
            runner = str(mjpython if mjpython.exists() else executable)

            print(
                "macOS native MuJoCo viewer is most reliable through mjpython. "
                "If the window does not open, rerun:\n"
                f"{runner} -m nemoclaw2robot.cli live-agent --sandbox {args.sandbox} "
                f"--gateway {args.gateway} --fps {args.fps:g}",
                file=sys.stderr,
            )
        from nemoclaw2robot.live import watch_sandbox_live_requests

        watch_sandbox_live_requests(
            sandbox=args.sandbox,
            gateway=args.gateway,
            poll_interval=args.poll_interval,
            fps=args.fps,
            camera=None if args.camera.lower() == "none" else args.camera,
            hold_seconds=args.hold_seconds,
        )
        return 0
    if args.command == "install-skill":
        return install_skill(args.sandbox, Path(args.skill_dir))

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nemoclaw2robot",
        description="Prompt-driven NemoClaw to MuJoCo robot task bridge.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-robots", help="List supported robot names.")

    plan = subparsers.add_parser("plan", help="Parse a prompt into a normalized task plan.")
    _add_prompt_args(plan)

    scene = subparsers.add_parser("scene", help="Generate a MuJoCo MJCF scene from a prompt.")
    _add_prompt_args(scene)
    scene.add_argument("--output", help="Optional scene.xml output path.")

    run = subparsers.add_parser("run", help="Generate artifacts and optionally run MuJoCo headless.")
    _add_prompt_args(run)
    run.add_argument("--output", help="Output directory. Defaults to artifacts/runs/<timestamp>.")
    run.add_argument("--no-sim", action="store_true", help="Only write plan and MJCF scene.")
    run.add_argument("--strict-sim", action="store_true", help="Fail when MuJoCo is unavailable.")

    view = subparsers.add_parser("view", help="Open the native MuJoCo viewer and play the task in real time.")
    _add_prompt_args(view)
    view.add_argument("--fps", type=float, default=30.0, help="Playback frames per second.")
    view.add_argument("--camera", default="teleoperator_pov", help="MuJoCo camera name, or none for free camera.")
    view.add_argument("--scene-output", help="Optional path to write the generated MJCF scene.")
    view.add_argument("--loop", action="store_true", help="Repeat the task until the viewer is closed.")
    view.add_argument(
        "--no-keep-open",
        action="store_true",
        help="Close the command after one playback instead of keeping the viewer open.",
    )

    live = subparsers.add_parser(
        "live",
        help="Run a host-side MuJoCo viewer bridge that OpenClaw tools can control in real time.",
    )
    live.add_argument("--host", default="127.0.0.1", help="HTTP bind host for the live viewer bridge.")
    live.add_argument("--port", type=int, default=8765, help="HTTP bind port for the live viewer bridge.")
    live.add_argument("--fps", type=float, default=30.0, help="Playback frames per second.")
    live.add_argument("--camera", default="teleoperator_pov", help="MuJoCo camera name, or none for free camera.")
    live.add_argument(
        "--hold-seconds",
        type=float,
        default=4.0,
        help="Seconds to keep the viewer open after each live task finishes.",
    )

    live_agent = subparsers.add_parser(
        "live-agent",
        help="Watch a NemoClaw sandbox live-request queue and play requests in the host MuJoCo viewer.",
    )
    live_agent.add_argument("--sandbox", required=True, help="NemoClaw sandbox name, such as mujoco-agent-robot.")
    live_agent.add_argument("--gateway", default="nemoclaw", help="OpenShell gateway name.")
    live_agent.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between queue polls.")
    live_agent.add_argument("--fps", type=float, default=30.0, help="Playback frames per second.")
    live_agent.add_argument("--camera", default="teleoperator_pov", help="MuJoCo camera name, or none for free camera.")
    live_agent.add_argument(
        "--hold-seconds",
        type=float,
        default=4.0,
        help="Seconds to keep the viewer open after each live task finishes.",
    )

    install = subparsers.add_parser("install-skill", help="Install the robot skill into a NemoClaw sandbox.")
    install.add_argument("sandbox", help="NemoClaw sandbox name.")
    install.add_argument(
        "--skill-dir",
        default=".agents/skills/robot-aloha-mujoco",
        help="Skill directory containing SKILL.md.",
    )
    return parser


def _add_prompt_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt", required=True, help="Robot task prompt in Japanese or English.")
    parser.add_argument("--robot", default="aloha", choices=[ALOHA_SPEC.name], help="Robot name.")


def install_skill(sandbox: str, skill_dir: Path) -> int:
    if not (skill_dir / "SKILL.md").exists():
        raise SystemExit(f"SKILL.md not found in {skill_dir}")
    return subprocess.call(["nemoclaw", sandbox, "skill", "install", str(skill_dir)])


if __name__ == "__main__":
    raise SystemExit(main())
