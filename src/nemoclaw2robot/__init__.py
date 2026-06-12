"""NemoClaw to robot simulation bridge."""

from nemoclaw2robot.prompt import parse_prompt
from nemoclaw2robot.scene import build_scene_xml

__all__ = ["build_scene_xml", "parse_prompt"]
__version__ = "0.1.0"

