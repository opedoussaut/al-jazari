"""MJCF (MuJoCo XML) parser.

MJCF semantics differ from URDF and are preserved rather than forced into URDF shape:
- the kinematic tree is the nesting of <body> elements; a <joint> inside a body
  moves that body relative to its parent body, so a body may have zero joints
  (welded to its parent) or several;
- default joint type is "hinge"; "free" and "ball" are multi-DoF;
- fixed URDF links are commonly merged into a parent body's geoms;
- actuators (<actuator>/<motor|position|...>) and sensors (<sensor>/<gyro|...>)
  are explicit elements.

<default> classes are resolved for the joint attributes used here. <include> is not
supported yet and is reported as a warning.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .model import Actuator, Joint, Link, ParsedDescription, Quantity, Sensor
from .xml import floats, load_xml

_ACTUATOR_TAGS = {
    "general", "motor", "position", "velocity", "intvelocity", "damper", "cylinder",
    "muscle", "adhesion",
}
_JOINT_ATTRS = ("type", "axis", "range", "limited", "actuatorfrcrange")


def _collect_defaults(root: etree._Element) -> dict[str, dict[str, str]]:
    """Map default class name -> resolved joint attributes (with inheritance)."""
    classes: dict[str, dict[str, str]] = {}

    def walk(el: etree._Element, inherited: dict[str, str]) -> None:
        attrs = dict(inherited)
        j = el.find("joint")
        if j is not None:
            attrs.update({k: v for k, v in j.attrib.items() if k in _JOINT_ATTRS})
        classes[el.get("class", "main")] = attrs
        for child in el.findall("default"):
            walk(child, attrs)

    for top in root.findall("default"):
        walk(top, {})
    return classes


def parse_mjcf(path: Path) -> ParsedDescription:
    root = load_xml(path)
    if root.tag != "mujoco":
        raise ValueError(f"{path.name}: root element is <{root.tag}>, expected <mujoco>")
    desc = ParsedDescription(format="mjcf", model_name=root.get("model", path.stem))
    if root.findall(".//include"):
        desc.warnings.append("<include> elements are not resolved")

    compiler = root.find("compiler")
    degrees = compiler is None or compiler.get("angle", "degree") == "degree"
    if compiler is not None and compiler.get("angle") is None:
        desc.warnings.append("compiler/@angle not set; MJCF default unit is degrees")
    defaults = _collect_defaults(root)
    site_body: dict[str, str] = {}

    def angle(v: float) -> float:
        return v * 3.141592653589793 / 180.0 if degrees else v

    def walk(body: etree._Element, parent: str | None, inherited_class: str) -> None:
        name = body.get("name")
        if name is None:
            desc.warnings.append(f"unnamed <body> at line {body.sourceline} skipped")
            return
        childclass = body.get("childclass", inherited_class)
        link = Link(name=name, line=body.sourceline)
        inertial = body.find("inertial")
        if inertial is not None and inertial.get("mass") is not None:
            link.mass = Quantity(float(inertial.get("mass")), "KiloGM", inertial.sourceline, "inertial/@mass")
        link.has_visual_geometry = body.find("geom") is not None
        desc.links.append(link)
        for site in body.findall("site"):
            if site.get("name"):
                site_body[site.get("name")] = name

        joints = body.findall("joint") + body.findall("freejoint")
        for j in joints:
            attrs = dict(defaults.get(j.get("class", childclass), {}))
            attrs.update(j.attrib)
            jtype = "free" if j.tag == "freejoint" else attrs.get("type", "hinge")
            joint = Joint(
                name=j.get("name") or f"{name}__joint_{j.sourceline}",
                line=j.sourceline,
                source_type=jtype,
                parent=parent,
                child=name,
            )
            if jtype in ("hinge", "slide"):
                joint.axis = tuple(floats(attrs.get("axis", "0 0 1")))
            rng = floats(attrs.get("range"))
            if rng and attrs.get("limited", "auto") != "false":
                conv = angle if jtype == "hinge" else (lambda v: v)
                unit = "RAD" if jtype == "hinge" else "M"
                joint.lower = Quantity(conv(rng[0]), unit, j.sourceline, "joint/@range[0]")
                joint.upper = Quantity(conv(rng[1]), unit, j.sourceline, "joint/@range[1]")
            frc = floats(attrs.get("actuatorfrcrange"))
            if frc:
                unit = "N-M" if jtype == "hinge" else "N"
                joint.effort = Quantity(max(abs(frc[0]), abs(frc[1])), unit, j.sourceline,
                                        "joint/@actuatorfrcrange")
            desc.joints.append(joint)

        for child in body.findall("body"):
            walk(child, name, childclass)

    for wb in root.findall("worldbody"):
        for body in wb.findall("body"):
            walk(body, None, "main")

    for act_root in root.findall("actuator"):
        for a in act_root:
            if a.tag not in _ACTUATOR_TAGS:
                continue
            gear = floats(a.get("gear"))
            cr = floats(a.get("ctrlrange"))
            desc.actuators.append(Actuator(
                name=a.get("name") or f"actuator_{a.sourceline}",
                line=a.sourceline,
                source_type=a.tag,
                joint=a.get("joint"),
                gear=gear[0] if gear else None,
                ctrl_range=(cr[0], cr[1]) if cr else None,
            ))
            if a.get("joint") is None:
                desc.warnings.append(f"actuator {a.get('name')} does not target a joint")

    for sen_root in root.findall("sensor"):
        for s in sen_root:
            site = s.get("site")
            desc.sensors.append(Sensor(
                name=s.get("name") or f"sensor_{s.sourceline}",
                line=s.sourceline,
                source_type=s.tag,
                site=site,
                attached_to=site_body.get(site) if site else None,
            ))
    return desc
