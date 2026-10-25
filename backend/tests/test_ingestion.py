import math

import pytest
from lxml import etree

from jazari.ingestion import parse_mjcf, parse_urdf


def test_urdf_ignores_commented_joints_and_keeps_lines(demo_dir):
    d = parse_urdf(demo_dir / "arm.urdf")
    names = [j.name for j in d.joints]
    assert names == ["shoulder_joint", "slide_joint", "tool_joint"]  # ghost_joint is in a comment
    assert [l.name for l in d.links] == ["base", "l1", "l2", "tool"]
    shoulder = d.joints[0]
    assert shoulder.line == 10 and shoulder.parent == "base" and shoulder.child == "l1"
    assert (shoulder.effort.value, shoulder.effort.unit) == (35.0, "N-M")
    assert shoulder.velocity.unit == "RAD-PER-SEC"


def test_urdf_prismatic_units_and_missing_values(demo_dir):
    d = parse_urdf(demo_dir / "arm.urdf")
    slide, tool = d.joints[1], d.joints[2]
    assert slide.upper.unit == "M" and slide.effort.unit == "N" and slide.velocity.unit == "M-PER-SEC"
    assert tool.lower is None and tool.effort is None  # not stated != zero
    assert d.links[3].mass is None
    assert any("transmission" in w for w in d.warnings)


def test_mjcf_tree_defaults_degrees_actuators_sensors(demo_dir):
    d = parse_mjcf(demo_dir / "arm.xml")
    j = {x.name: x for x in d.joints}
    assert j["root"].source_type == "free" and j["root"].parent is None
    assert j["shoulder_joint"].source_type == "hinge" and j["shoulder_joint"].parent == "base"
    assert math.isclose(j["shoulder_joint"].upper.value, math.pi / 2, rel_tol=1e-9)  # 90 deg -> rad
    assert j["slide_joint"].source_type == "slide"  # from default class
    assert j["slide_joint"].upper.unit == "M" and j["slide_joint"].upper.value == pytest.approx(0.2)
    assert j["shoulder_joint"].effort.value == 50
    assert [(a.name, a.source_type, a.joint, a.gear) for a in d.actuators] == [
        ("shoulder_motor", "motor", "shoulder_joint", 10.0), ("slide_servo", "position", "slide_joint", None)]
    assert d.sensors[0].source_type == "gyro" and d.sensors[0].attached_to == "base"


def test_xml_entities_are_not_resolved(tmp_path):
    p = tmp_path / "evil.urdf"
    p.write_text('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                 '<robot name="&x;"><link name="a"/></robot>')
    try:
        d = parse_urdf(p)
    except etree.XMLSyntaxError:
        return  # refusing the external entity is the safe outcome
    assert "root" not in d.model_name
