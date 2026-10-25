"""Format-neutral intermediate representation of a parsed robot description.

Parsers fill only what the source actually states. A value of None means "not
stated in this source", which is different from "the component does not exist".

`source_file` is set when an element comes from a file other than the one passed to the
parser (MJCF <include>, Xacro include or macro definition); `line` is then a line of that
file. `call_line`/`call_file` locate the Xacro macro call that emitted the element, which
is where per-instance values (e.g. actuator limits) are written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Quantity:
    value: float
    unit: str  # QUDT unit local name, e.g. "RAD", "KiloGM", "N-M", "RAD-PER-SEC", "A"
    line: int | None = None
    attribute: str | None = None  # e.g. 'limit/@effort' - where in the element it came from
    source_file: Path | None = None


@dataclass
class Located:
    line: int
    source_file: Path | None = None


@dataclass
class Link(Located):
    name: str = ""
    mass: Quantity | None = None
    has_visual_geometry: bool = False
    has_collision_geometry: bool = False


@dataclass
class Joint(Located):
    name: str = ""
    source_type: str = ""  # as written (urdf "revolute", mjcf "hinge"); "weld" = MJCF body without joint
    parent: str | None = None  # None = attached to the world
    child: str = ""
    axis: tuple[float, float, float] | None = None
    lower: Quantity | None = None
    upper: Quantity | None = None
    effort: Quantity | None = None
    velocity: Quantity | None = None


@dataclass
class Actuator(Located):
    name: str = ""
    source_type: str = ""  # mjcf element name (motor, position, ...) or "ros2_control joint"
    joint: str | None = None
    gear: float | None = None
    kp: float | None = None
    ctrl_range: tuple[float, float] | None = None
    effort: Quantity | None = None  # MJCF forcerange or ros2_control torque_limit
    current: Quantity | None = None  # ros2_control current_limit
    model: str | None = None  # e.g. RobStride "rs-06"
    hardware_address: str | None = None  # e.g. "can_id=31"
    hardware_plugin: str | None = None
    command_interfaces: list[str] = field(default_factory=list)
    transmission: str | None = None  # e.g. "four-bar linkage"
    transmission_parameters: str | None = None  # raw, units as in the source
    call_line: int | None = None
    call_file: Path | None = None


@dataclass
class Sensor(Located):
    name: str = ""
    source_type: str = ""  # mjcf element name (gyro, accelerometer, camera, ...)
    site: str | None = None
    attached_to: str | None = None  # body/link; None with source_type camera = fixed in the world
    detail: str | None = None


@dataclass
class Coupling(Located):
    """MJCF <equality><joint>: joint1 = polynomial(joint2)."""

    joint1: str = ""
    joint2: str = ""
    polycoef: str = "0 1 0 0 0"


@dataclass
class ParsedDescription:
    format: str  # "urdf" | "xacro" | "mjcf"
    model_name: str
    links: list[Link] = field(default_factory=list)
    joints: list[Joint] = field(default_factory=list)
    actuators: list[Actuator] = field(default_factory=list)
    sensors: list[Sensor] = field(default_factory=list)
    couplings: list[Coupling] = field(default_factory=list)
    included_files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
