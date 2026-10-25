"""MJCF (MuJoCo XML) parser.

MJCF semantics differ from URDF and are preserved rather than forced into URDF shape:
- the kinematic tree is the nesting of <body> elements; a <joint> inside a body
  moves that body relative to its parent body. A body with no joint is welded to its
  parent (or to the world at the top level); this is reported as a joint of source type
  "weld" so that the tree stays connected, with the body's own line as provenance;
- default joint type is "hinge"; "free" and "ball" are multi-DoF;
- fixed URDF links are commonly merged into a parent body's geoms;
- actuators (<actuator>/<motor|position|...>), sensors (<sensor>/<gyro|...>), cameras
  and joint equality constraints (<equality>/<joint>) are explicit elements.

<default> classes (nested, with childclass) are resolved for joint and actuator
attributes. <include> is resolved relative to the including file and may not leave the
sandbox folder.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .model import Actuator, Coupling, Joint, Link, ParsedDescription, Quantity, Sensor
from .xml import SRC_ATTR, floats, inside, load_xml, location, stamp

_ACTUATOR_TAGS = {
    "general", "motor", "position", "velocity", "intvelocity", "damper", "cylinder",
    "muscle", "adhesion",
}
_JOINT_ATTRS = ("type", "axis", "range", "limited", "actuatorfrcrange")
_ACT_ATTRS = ("forcerange", "forcelimited", "ctrlrange", "gear", "kp")
MAX_INCLUDE_DEPTH = 10


def _resolve_includes(root: etree._Element, file: Path, sandbox: Path, files: list[Path],
                      depth: int = 0) -> None:
    if depth > MAX_INCLUDE_DEPTH:
        raise ValueError("MJCF <include> nesting too deep")
    for inc in list(root.iter("include")):
        inc_file, _ = location(inc)
        base = (inc_file or file).parent
        target = inside(base / inc.get("file"), sandbox)
        files.append(target)
        sub = load_xml(target)
        _resolve_includes(sub, target, sandbox, files, depth + 1)
        for el in sub.iter():
            if isinstance(el.tag, str) and el.get(SRC_ATTR) is None:
                stamp(el, target)
        parent = inc.getparent()
        idx = parent.index(inc)
        for i, child in enumerate(list(sub)):
            parent.insert(idx + i, child)
        parent.remove(inc)


def _collect_defaults(root: etree._Element) -> dict[str, dict[str, dict[str, str]]]:
    """Map default class name -> {element tag -> resolved attributes} (with inheritance)."""
    classes: dict[str, dict[str, dict[str, str]]] = {}

    def walk(el: etree._Element, inherited: dict[str, dict[str, str]]) -> None:
        attrs = {tag: dict(a) for tag, a in inherited.items()}
        for child in el:
            if not isinstance(child.tag, str) or child.tag == "default":
                continue
            keep = _JOINT_ATTRS if child.tag == "joint" else _ACT_ATTRS if child.tag in _ACTUATOR_TAGS else ()
            if keep:
                attrs.setdefault(child.tag, {}).update({k: v for k, v in child.attrib.items() if k in keep})
        classes[el.get("class", "main")] = attrs
        for child in el.findall("default"):
            walk(child, attrs)

    for top in root.findall("default"):
        walk(top, {})
    return classes


def parse_mjcf(path: Path, sandbox: Path | None = None) -> ParsedDescription:
    sandbox = sandbox or path.parent
    root = load_xml(path)
    if root.tag != "mujoco":
        raise ValueError(f"{path.name}: root element is <{root.tag}>, expected <mujoco>")
    desc = ParsedDescription(format="mjcf", model_name=root.get("model", path.stem))
    _resolve_includes(root, path, sandbox, desc.included_files)

    compiler = root.find("compiler")
    degrees = compiler is None or compiler.get("angle", "degree") == "degree"
    if compiler is not None and compiler.get("angle") is None:
        desc.warnings.append("compiler/@angle not set; MJCF default unit is degrees")
    defaults = _collect_defaults(root)
    site_body: dict[str, str] = {}

    def angle(v: float) -> float:
        return v * 3.141592653589793 / 180.0 if degrees else v

    def q(value: float, unit: str, el: etree._Element, attribute: str) -> Quantity:
        file, line = location(el)
        return Quantity(value, unit, line, attribute, file)

    def camera(cam: etree._Element, body: str | None) -> None:
        file, line = location(cam)
        detail = " ".join(f"{k}={cam.get(k)}" for k in ("mode", "fovy", "resolution") if cam.get(k))
        desc.sensors.append(Sensor(name=cam.get("name") or f"camera_{line}", line=line, source_file=file,
                                   source_type="camera", attached_to=body, detail=detail or None))

    def walk(body: etree._Element, parent: str | None, inherited_class: str) -> None:
        name = body.get("name")
        file, line = location(body)
        if name is None:
            desc.warnings.append(f"unnamed <body> at line {line} skipped")
            return
        childclass = body.get("childclass", inherited_class)
        link = Link(name=name, line=line, source_file=file)
        inertial = body.find("inertial")
        if inertial is not None and inertial.get("mass") is not None:
            link.mass = q(float(inertial.get("mass")), "KiloGM", inertial, "inertial/@mass")
        link.has_visual_geometry = body.find("geom") is not None
        desc.links.append(link)
        for site in body.findall("site"):
            if site.get("name"):
                site_body[site.get("name")] = name
        for cam in body.findall("camera"):
            camera(cam, name)

        joints = body.findall("joint") + body.findall("freejoint")
        if not joints:
            desc.joints.append(Joint(name=f"{name}__weld", line=line, source_file=file,
                                     source_type="weld", parent=parent, child=name))
        for j in joints:
            jfile, jline = location(j)
            attrs = dict(defaults.get(j.get("class", childclass), {}).get("joint", {}))
            attrs.update(j.attrib)
            jtype = "free" if j.tag == "freejoint" else attrs.get("type", "hinge")
            joint = Joint(name=j.get("name") or f"{name}__joint_{jline}", line=jline, source_file=jfile,
                          source_type=jtype, parent=parent, child=name)
            if jtype in ("hinge", "slide"):
                joint.axis = tuple(floats(attrs.get("axis", "0 0 1")))
            rng = floats(attrs.get("range"))
            if rng and attrs.get("limited", "auto") != "false":
                conv = angle if jtype == "hinge" else (lambda v: v)
                unit = "RAD" if jtype == "hinge" else "M"
                joint.lower = q(conv(rng[0]), unit, j, "joint/@range[0]")
                joint.upper = q(conv(rng[1]), unit, j, "joint/@range[1]")
            frc = floats(attrs.get("actuatorfrcrange"))
            if frc:
                joint.effort = q(max(abs(frc[0]), abs(frc[1])), "N-M" if jtype == "hinge" else "N", j,
                                 "joint/@actuatorfrcrange")
            desc.joints.append(joint)

        for child in body.findall("body"):
            walk(child, name, childclass)

    for wb in root.findall("worldbody"):
        for cam in wb.findall("camera"):
            camera(cam, None)
        for body in wb.findall("body"):
            walk(body, None, "main")

    joint_types = {j.name: j.source_type for j in desc.joints}
    for act_root in root.findall("actuator"):
        for a in act_root:
            if not isinstance(a.tag, str) or a.tag not in _ACTUATOR_TAGS:
                continue
            attrs = dict(defaults.get(a.get("class", "main"), {}).get(a.tag, {}))
            attrs.update(a.attrib)
            file, line = location(a)
            gear, cr, fr = floats(attrs.get("gear")), floats(attrs.get("ctrlrange")), floats(attrs.get("forcerange"))
            act = Actuator(name=a.get("name") or f"actuator_{line}", line=line, source_file=file,
                           source_type=a.tag, joint=a.get("joint"), gear=gear[0] if gear else None,
                           kp=float(attrs["kp"]) if attrs.get("kp") else None,
                           ctrl_range=(cr[0], cr[1]) if cr else None)
            if fr:
                unit = "N" if joint_types.get(a.get("joint")) == "slide" else "N-M"
                act.effort = q(max(abs(fr[0]), abs(fr[1])), unit, a, "actuator/@forcerange")
            if a.get("joint") is None:
                desc.warnings.append(f"actuator {act.name} does not target a joint")
            desc.actuators.append(act)

    for eq_root in root.findall("equality"):
        for e in eq_root:
            if not isinstance(e.tag, str):
                continue
            file, line = location(e)
            if e.tag == "joint":
                desc.couplings.append(Coupling(line=line, source_file=file, joint1=e.get("joint1"),
                                               joint2=e.get("joint2"), polycoef=e.get("polycoef", "0 1 0 0 0")))
            else:
                desc.warnings.append(f"<equality><{e.tag}> at line {line} not interpreted")

    for sen_root in root.findall("sensor"):
        for s in sen_root:
            if not isinstance(s.tag, str):
                continue
            file, line = location(s)
            site = s.get("site")
            desc.sensors.append(Sensor(name=s.get("name") or f"sensor_{line}", line=line, source_file=file,
                                       source_type=s.tag, site=site,
                                       attached_to=site_body.get(site) if site else None))
    return desc
