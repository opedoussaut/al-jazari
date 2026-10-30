"""URDF parser (also used for expanded Xacro).

URDF semantics preserved here:
- joints carry an explicit <parent link> and <child link>;
- <limit> holds lower/upper (rad or m), effort (N*m or N) and velocity (rad/s or m/s);
- plain URDF has no actuator element. <ros2_control> blocks, when present, declare the
  hardware interface of each joint (actuator model, bus address, torque and current
  limits, transmission); they are read as actuators of that joint. <transmission> and
  <gazebo> extensions are reported, not interpreted.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .model import Actuator, Joint, Link, ParsedDescription, Quantity, Sensor
from .xacro import expand_xacro
from .xml import CALL_ATTR, floats, load_xml, location

_LINEAR = {"prismatic"}
_LINKAGE_PREFIX = "linkage_"


def parse_urdf(path: Path) -> ParsedDescription:
    return parse_urdf_tree(load_xml(path), path.stem, "urdf")


def parse_xacro(path: Path, sandbox: Path, packages: dict[str, Path],
                args: dict[str, str] | None = None) -> ParsedDescription:
    root, files = expand_xacro(path, sandbox, packages, args)
    desc = parse_urdf_tree(root, path.stem, "xacro")
    desc.included_files = [f for f in files if f != path.resolve()]
    return desc


def _q(value: str, unit: str, el: etree._Element, attribute: str) -> Quantity:
    file, line = location(el)
    return Quantity(float(value), unit, line, attribute, file)


def parse_urdf_tree(root: etree._Element, default_name: str, fmt: str) -> ParsedDescription:
    if root.tag != "robot":
        raise ValueError(f"{default_name}: root element is <{root.tag}>, expected <robot>")
    desc = ParsedDescription(format=fmt, model_name=root.get("name", default_name))

    for el in root.findall("link"):
        file, line = location(el)
        link = Link(name=el.get("name"), line=line, source_file=file,
                    has_visual_geometry=el.find("visual/geometry") is not None,
                    has_collision_geometry=el.find("collision/geometry") is not None)
        mass = el.find("inertial/mass")
        if mass is not None and mass.get("value") is not None:
            link.mass = _q(mass.get("value"), "KiloGM", mass, "inertial/mass/@value")
        desc.links.append(link)

    joint_types: dict[str, str] = {}
    for el in root.findall("joint"):
        jtype = el.get("type")
        joint_types[el.get("name")] = jtype
        parent, child = el.find("parent"), el.find("child")
        file, line = location(el)
        joint = Joint(name=el.get("name"), line=line, source_file=file, source_type=jtype,
                      parent=parent.get("link") if parent is not None else None,
                      child=child.get("link") if child is not None else None)
        axis = el.find("axis")
        if axis is not None:
            joint.axis = tuple(floats(axis.get("xyz")))
        limit = el.find("limit")
        if limit is not None:
            linear = jtype in _LINEAR
            for attr, unit in (("lower", "M" if linear else "RAD"), ("upper", "M" if linear else "RAD"),
                               ("effort", "N" if linear else "N-M"),
                               ("velocity", "M-PER-SEC" if linear else "RAD-PER-SEC")):
                if limit.get(attr) is not None:
                    setattr(joint, attr, _q(limit.get(attr), unit, limit, f"limit/@{attr}"))
        desc.joints.append(joint)

    for rc in root.findall("ros2_control"):
        _ros2_control(rc, joint_types, desc)

    for tag in ("transmission", "gazebo"):
        n = len(root.findall(tag))
        if n:
            desc.warnings.append(f"{n} <{tag}> element(s) present but not interpreted")
    return desc


def _ros2_control(rc: etree._Element, joint_types: dict[str, str], desc: ParsedDescription) -> None:
    plugin_el = rc.find("hardware/plugin")
    plugin = plugin_el.text.strip() if plugin_el is not None and plugin_el.text else None
    hw_params = {p.get("name"): (p.text or "").strip() for p in rc.findall("hardware/param")}
    bus = hw_params.get("can_interface")
    for j in rc.findall("joint"):
        name = j.get("name")
        params = {p.get("name"): (p.text or "").strip() for p in j.findall("param")}
        file, line = location(j)
        # per-joint values are written at the macro call site, not in the macro body
        call_file, call_line = location(j, CALL_ATTR) if j.get(CALL_ATTR) else (None, None)
        linear = joint_types.get(name) in _LINEAR
        act = Actuator(
            name=name, line=line, source_file=file, source_type="ros2_control joint", joint=name,
            model=params.get("model"), hardware_plugin=plugin,
            hardware_address=(f"can_id={params['can_id']}" + (f" on {bus}" if bus else "")
                              if params.get("can_id") else None),
            command_interfaces=[c.get("name") for c in j.findall("command_interface")],
            call_line=call_line, call_file=call_file,
        )
        cline = call_line or line
        cfile = call_file if call_line else file
        if params.get("torque_limit"):
            act.effort = Quantity(float(params["torque_limit"]), "N" if linear else "N-M", cline,
                                  "ros2_control/joint/param[@name='torque_limit']", cfile)
        if params.get("current_limit"):
            act.current = Quantity(float(params["current_limit"]), "A", cline,
                                   "ros2_control/joint/param[@name='current_limit']", cfile)
        linkage = {k[len(_LINKAGE_PREFIX):]: v for k, v in params.items()
                   if k.startswith(_LINKAGE_PREFIX) and k != "linkage_enabled"}
        if linkage:
            act.transmission = "four-bar linkage"
            act.transmission_parameters = " ".join(f"{k}={v}" for k, v in sorted(linkage.items()))
        if name not in joint_types:
            desc.warnings.append(f"ros2_control joint {name} has no matching URDF joint")
        desc.actuators.append(act)
    for s in rc.findall("sensor"):
        file, line = location(s)
        desc.sensors.append(Sensor(name=s.get("name"), line=line, source_file=file,
                                   source_type="ros2_control sensor", detail=plugin))
