"""URDF parser.

URDF semantics preserved here:
- joints carry an explicit <parent link> and <child link>;
- <limit> holds lower/upper (rad or m), effort (N*m or N) and velocity (rad/s or m/s);
- URDF has no actuator or sensor elements - <transmission> and <gazebo> extensions are
  reported as warnings rather than silently interpreted.

Xacro files must be expanded to URDF before parsing (planned for M3).
"""

from __future__ import annotations

from pathlib import Path

from .model import Joint, Link, ParsedDescription, Quantity
from .xml import floats, load_xml

_LINEAR = {"prismatic"}


def parse_urdf(path: Path) -> ParsedDescription:
    root = load_xml(path)
    if root.tag != "robot":
        raise ValueError(f"{path.name}: root element is <{root.tag}>, expected <robot>")
    desc = ParsedDescription(format="urdf", model_name=root.get("name", path.stem))

    for el in root.findall("link"):
        link = Link(
            name=el.get("name"),
            line=el.sourceline,
            has_visual_geometry=el.find("visual/geometry") is not None,
            has_collision_geometry=el.find("collision/geometry") is not None,
        )
        mass = el.find("inertial/mass")
        if mass is not None and mass.get("value") is not None:
            link.mass = Quantity(float(mass.get("value")), "KiloGM", mass.sourceline, "inertial/mass/@value")
        desc.links.append(link)

    for el in root.findall("joint"):
        jtype = el.get("type")
        parent, child = el.find("parent"), el.find("child")
        joint = Joint(
            name=el.get("name"),
            line=el.sourceline,
            source_type=jtype,
            parent=parent.get("link") if parent is not None else None,
            child=child.get("link") if child is not None else None,
        )
        axis = el.find("axis")
        if axis is not None:
            joint.axis = tuple(floats(axis.get("xyz")))
        limit = el.find("limit")
        if limit is not None:
            pos_unit = "M" if jtype in _LINEAR else "RAD"
            ln = limit.sourceline
            for attr, unit, target in (
                ("lower", pos_unit, "lower"),
                ("upper", pos_unit, "upper"),
                ("effort", "N" if jtype in _LINEAR else "N-M", "effort"),
                ("velocity", "M-PER-SEC" if jtype in _LINEAR else "RAD-PER-SEC", "velocity"),
            ):
                if limit.get(attr) is not None:
                    setattr(joint, target, Quantity(float(limit.get(attr)), unit, ln, f"limit/@{attr}"))
        desc.joints.append(joint)

    for tag in ("transmission", "gazebo"):
        n = len(root.findall(tag))
        if n:
            desc.warnings.append(f"{n} <{tag}> element(s) present but not interpreted")
    return desc
