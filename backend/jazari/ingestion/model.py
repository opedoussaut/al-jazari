"""Format-neutral intermediate representation of a parsed robot description.

Parsers fill only what the source actually states. A value of None means "not
stated in this source", which is different from "the component does not exist".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Quantity:
    value: float
    unit: str  # QUDT unit local name, e.g. "RAD", "KiloGM", "N-M", "RAD-PER-SEC"
    line: int | None = None
    attribute: str | None = None  # e.g. 'limit/@effort' - where in the element it came from


@dataclass
class Link:
    name: str
    line: int
    mass: Quantity | None = None
    has_visual_geometry: bool = False
    has_collision_geometry: bool = False


@dataclass
class Joint:
    name: str
    line: int
    source_type: str  # exactly as written in the source (urdf "revolute", mjcf "hinge" ...)
    parent: str | None
    child: str
    axis: tuple[float, float, float] | None = None
    lower: Quantity | None = None
    upper: Quantity | None = None
    effort: Quantity | None = None
    velocity: Quantity | None = None


@dataclass
class Actuator:
    name: str
    line: int
    source_type: str  # mjcf element name: motor, position, velocity, general ...
    joint: str | None
    gear: float | None = None
    ctrl_range: tuple[float, float] | None = None


@dataclass
class Sensor:
    name: str
    line: int
    source_type: str  # mjcf element name: gyro, accelerometer, ...
    site: str | None
    attached_to: str | None  # body/link carrying the site


@dataclass
class ParsedDescription:
    format: str  # "urdf" | "mjcf"
    model_name: str
    links: list[Link] = field(default_factory=list)
    joints: list[Joint] = field(default_factory=list)
    actuators: list[Actuator] = field(default_factory=list)
    sensors: list[Sensor] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
