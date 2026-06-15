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
    if args.command == "prompt-control":
        from nemoclaw2robot.session import prompt_control

        print(
            json.dumps(
                prompt_control(
                    args.prompt,
                    session_id=args.session_id,
                    root=Path(args.session_root),
                    robot=args.robot,
                    steps=args.steps,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-start":
        from nemoclaw2robot.session import create_session

        print(
            json.dumps(
                create_session(
                    args.prompt,
                    session_id=args.session_id,
                    root=Path(args.session_root),
                    robot=args.robot,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-state":
        from nemoclaw2robot.session import get_state

        print(json.dumps(get_state(args.session_id, root=Path(args.session_root)), indent=2, ensure_ascii=False))
        return 0
    if args.command == "session-ik":
        from nemoclaw2robot.session import solve_ik

        print(
            json.dumps(
                solve_ik(
                    args.session_id,
                    hand=args.hand,
                    position=_triple(args.position),
                    root=Path(args.session_root),
                    save=args.save,
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-move-relative":
        from nemoclaw2robot.session import move_relative

        print(
            json.dumps(
                move_relative(
                    args.session_id,
                    hand=args.hand,
                    delta=(args.dx, args.dy, args.dz),
                    steps=args.steps,
                    root=Path(args.session_root),
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-move-to":
        from nemoclaw2robot.session import move_to_pose

        print(
            json.dumps(
                move_to_pose(
                    args.session_id,
                    hand=args.hand,
                    position=_triple(args.position),
                    steps=args.steps,
                    root=Path(args.session_root),
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-cartesian-path":
        from nemoclaw2robot.session import execute_cartesian_path

        print(
            json.dumps(
                execute_cartesian_path(
                    args.session_id,
                    hand=args.hand,
                    waypoints=_waypoints(args.waypoints_json),
                    steps_per_waypoint=args.steps_per_waypoint,
                    root=Path(args.session_root),
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-gripper":
        from nemoclaw2robot.session import set_gripper

        print(
            json.dumps(
                set_gripper(
                    args.session_id,
                    hand=args.hand,
                    opening=args.opening,
                    steps=args.steps,
                    root=Path(args.session_root),
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-add-object":
        from nemoclaw2robot.session import add_object

        print(
            json.dumps(
                add_object(
                    args.session_id,
                    name=args.name,
                    kind=args.kind,
                    position=_triple(args.position),
                    size=tuple(args.size) if args.size else None,
                    rgba=_quad(args.rgba) if args.rgba else None,
                    fixed=args.fixed,
                    root=Path(args.session_root),
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-add-trace":
        from nemoclaw2robot.session import add_trace

        print(
            json.dumps(
                add_trace(
                    args.session_id,
                    points=_waypoints(args.points_json),
                    name_prefix=args.name_prefix,
                    radius=args.radius,
                    rgba=_quad(args.rgba),
                    root=Path(args.session_root),
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-check-pose":
        from nemoclaw2robot.session import check_pose

        print(
            json.dumps(
                check_pose(
                    args.session_id,
                    hand=args.hand,
                    expected_position=_triple(args.expected_position) if args.expected_position else None,
                    tolerance=args.tolerance,
                    root=Path(args.session_root),
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "session-check-contacts":
        from nemoclaw2robot.session import check_contacts

        print(
            json.dumps(
                check_contacts(
                    args.session_id,
                    object_name=args.object_name,
                    root=Path(args.session_root),
                ),
                indent=2,
                ensure_ascii=False,
            )
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

    prompt_control = subparsers.add_parser(
        "prompt-control",
        help="Execute one natural-language ALOHA prompt through session planning primitives.",
    )
    _add_prompt_args(prompt_control)
    prompt_control.add_argument("--session-id", help="Optional stable session id.")
    _add_session_root_arg(prompt_control)
    prompt_control.add_argument("--steps", type=int, default=30, help="Default interpolation steps for motion.")

    session_start = subparsers.add_parser(
        "session-start",
        help="Create a persistent ALOHA MuJoCo manipulation session for tool-by-tool Agent planning.",
    )
    _add_prompt_args(session_start)
    session_start.add_argument("--session-id", help="Optional stable session id.")
    _add_session_root_arg(session_start)

    session_state = subparsers.add_parser("session-state", help="Read robot, object, and contact state.")
    _add_session_args(session_state)

    session_ik = subparsers.add_parser("session-ik", help="Solve a position IK target for an arm gripper site.")
    _add_session_args(session_ik)
    _add_hand_arg(session_ik)
    _add_position_arg(session_ik)
    session_ik.add_argument("--save", action="store_true", help="Save the solved qpos back into the session.")

    session_move_relative = subparsers.add_parser(
        "session-move-relative",
        help="Move a gripper by a world-frame delta in meters.",
    )
    _add_session_args(session_move_relative)
    _add_hand_arg(session_move_relative)
    session_move_relative.add_argument("--dx", type=float, default=0.0, help="World x delta in meters.")
    session_move_relative.add_argument("--dy", type=float, default=0.0, help="World y delta in meters.")
    session_move_relative.add_argument("--dz", type=float, default=0.0, help="World z delta in meters.")
    session_move_relative.add_argument("--steps", type=int, default=30, help="Interpolation steps.")

    session_move_to = subparsers.add_parser("session-move-to", help="Move a gripper to a world-frame position.")
    _add_session_args(session_move_to)
    _add_hand_arg(session_move_to)
    _add_position_arg(session_move_to)
    session_move_to.add_argument("--steps", type=int, default=30, help="Interpolation steps.")

    session_cartesian_path = subparsers.add_parser(
        "session-cartesian-path",
        help="Execute a list of world-frame gripper waypoints.",
    )
    _add_session_args(session_cartesian_path)
    _add_hand_arg(session_cartesian_path)
    session_cartesian_path.add_argument(
        "--waypoints-json",
        required=True,
        help='JSON list of [x, y, z] waypoints, for example: [[0,-0.3,0.12],[0.05,-0.3,0.12]]',
    )
    session_cartesian_path.add_argument("--steps-per-waypoint", type=int, default=20)

    session_gripper = subparsers.add_parser("session-gripper", help="Open or close a gripper to an opening value.")
    _add_session_args(session_gripper)
    _add_hand_arg(session_gripper)
    session_gripper.add_argument("--opening", type=float, required=True, help="Finger opening in meters.")
    session_gripper.add_argument("--steps", type=int, default=12, help="Interpolation steps.")

    session_add_object = subparsers.add_parser(
        "session-add-object",
        help="Add or replace a simple project-side object in the session scene.",
    )
    _add_session_args(session_add_object)
    session_add_object.add_argument("--name", required=True)
    session_add_object.add_argument(
        "--kind",
        required=True,
        choices=["cube", "sphere", "cylinder", "paper", "marker"],
    )
    _add_position_arg(session_add_object)
    session_add_object.add_argument("--size", nargs="+", type=float, help="MuJoCo geom size tuple.")
    session_add_object.add_argument("--rgba", nargs=4, type=float, help="RGBA values.")
    session_add_object.add_argument(
        "--fixed",
        action="store_true",
        default=None,
        help="Add without a freejoint. When omitted, the kind default is used.",
    )

    session_add_trace = subparsers.add_parser(
        "session-add-trace",
        help="Add non-colliding capsule trace segments for drawing/path visualization.",
    )
    _add_session_args(session_add_trace)
    session_add_trace.add_argument("--points-json", required=True, help="JSON list of [x, y, z] trace points.")
    session_add_trace.add_argument("--name-prefix", default="trace")
    session_add_trace.add_argument("--radius", type=float, default=0.004)
    session_add_trace.add_argument("--rgba", nargs=4, type=float, default=(0.05, 0.05, 0.05, 1.0))

    session_check_pose = subparsers.add_parser("session-check-pose", help="Check a gripper pose against tolerance.")
    _add_session_args(session_check_pose)
    _add_hand_arg(session_check_pose)
    session_check_pose.add_argument("--expected-position", nargs=3, type=float)
    session_check_pose.add_argument("--tolerance", type=float, default=0.02)

    session_check_contacts = subparsers.add_parser("session-check-contacts", help="Read current MuJoCo contacts.")
    _add_session_args(session_check_contacts)
    session_check_contacts.add_argument("--object-name", help="Optional object name filter.")

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


def _add_session_root_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session-root", default="artifacts/sessions", help="Persistent session root directory.")


def _add_session_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session-id", required=True, help="Persistent ALOHA session id.")
    _add_session_root_arg(parser)


def _add_hand_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--hand", default="right", choices=["left", "right"], help="Arm name.")


def _add_position_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--position", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))


def _triple(values: list[float]) -> tuple[float, float, float]:
    if len(values) != 3:
        raise argparse.ArgumentTypeError("expected three float values")
    return (float(values[0]), float(values[1]), float(values[2]))


def _quad(values: list[float] | tuple[float, ...]) -> tuple[float, float, float, float]:
    if len(values) != 4:
        raise argparse.ArgumentTypeError("expected four float values")
    return (float(values[0]), float(values[1]), float(values[2]), float(values[3]))


def _waypoints(raw_json: str) -> tuple[tuple[float, float, float], ...]:
    payload = json.loads(raw_json)
    if not isinstance(payload, list):
        raise argparse.ArgumentTypeError("waypoints JSON must be a list")
    waypoints: list[tuple[float, float, float]] = []
    for item in payload:
        if not isinstance(item, list) or len(item) != 3:
            raise argparse.ArgumentTypeError("each waypoint must be [x, y, z]")
        waypoints.append((float(item[0]), float(item[1]), float(item[2])))
    return tuple(waypoints)


def install_skill(sandbox: str, skill_dir: Path) -> int:
    if not (skill_dir / "SKILL.md").exists():
        raise SystemExit(f"SKILL.md not found in {skill_dir}")
    return subprocess.call(["nemoclaw", sandbox, "skill", "install", str(skill_dir)])


if __name__ == "__main__":
    raise SystemExit(main())
