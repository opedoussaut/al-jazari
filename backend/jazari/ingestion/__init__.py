"""Robot description ingestion: URDF and MJCF parsers into a common model."""

from .mjcf import parse_mjcf
from .model import ParsedDescription
from .urdf import parse_urdf, parse_xacro

PARSERS = {"urdf": parse_urdf, "mjcf": parse_mjcf}

__all__ = ["PARSERS", "ParsedDescription", "parse_mjcf", "parse_urdf", "parse_xacro"]
