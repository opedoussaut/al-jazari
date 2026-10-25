"""Xacro expansion and the MJCF features needed for Berkeley Humanoid Lite and ALOHA 2."""

import pytest

from jazari.ingestion import parse_mjcf, parse_xacro
from jazari.ingestion.xacro import XacroError, evaluate
from jazari.ingestion.xml import UnsafePath


@pytest.fixture
def xpkg(demo_dir):
    root = demo_dir.parent / "xpkg"
    return root, {"pkg": root / "pkg"}


def test_xacro_macros_include_args_and_conditions(xpkg):
    root, pkgs = xpkg
    d = parse_xacro(root / "pkg" / "robot.urdf.xacro", root, pkgs)
    joints = {j.name: j for j in d.joints}
    assert set(joints) == {"left_shoulder", "right_shoulder"}
    assert joints["left_shoulder"].lower.value == -1.5 and joints["right_shoulder"].lower.value == 1.5
    assert joints["left_shoulder"].effort.value == 20  # macro default
    assert {lk.name for lk in d.links} == {"base", "left_upper", "right_upper"}  # unless branch skipped
    assert next(lk for lk in d.links if lk.name == "left_upper").mass.value == 1.0  # ${reach * 2}
    # elements emitted by a macro point at the macro file, actuators at the call site
    assert joints["left_shoulder"].source_file.name == "arm.xacro"
    act = next(a for a in d.actuators if a.name == "left_shoulder")
    assert (act.model, act.hardware_address, act.effort.value) == ("rs-02", "can_id=11", 12.5)
    assert act.call_file.name == "robot.urdf.xacro" and act.call_line == 12
    assert [f.name for f in d.included_files] == ["arm.xacro"]


def test_xacro_args_override_defaults(xpkg):
    root, pkgs = xpkg
    d = parse_xacro(root / "pkg" / "robot.urdf.xacro", root, pkgs, {"with_hw": "false"})
    assert d.actuators == [] and "no_hw_marker" in {lk.name for lk in d.links}


@pytest.mark.parametrize("name,error", [("evil_env.xacro", XacroError), ("evil_eval.xacro", XacroError),
                                         ("evil_escape.xacro", UnsafePath)])
def test_xacro_refuses_env_eval_and_escapes(xpkg, name, error):
    root, pkgs = xpkg
    with pytest.raises(error):
        parse_xacro(root / "pkg" / name, root, pkgs)


def test_expression_evaluator_is_restricted():
    assert evaluate("a * 2 + 1", {"a": "3"}) == 7
    assert evaluate("x or y", {"x": "false", "y": "true"}) is True
    for bad in ("__import__('os')", "a.b", "[1, 2]", "f(1)"):
        with pytest.raises(XacroError):
            evaluate(bad, {"a": 1})


def test_mjcf_include_defaults_welds_cameras_couplings(demo_dir):
    d = parse_mjcf(demo_dir.parent / "mj" / "bimanual.xml")
    joints = {j.name: j for j in d.joints}
    # bodies without joints are welded: to the world at top level, to the parent otherwise
    assert joints["left/base__weld"].parent is None and joints["left/base__weld"].source_type == "weld"
    assert joints["left/finger_a"].source_type == "slide" and joints["left/finger_a"].upper.unit == "M"
    assert joints["left/shoulder"].effort.value == 10  # class default via childclass
    acts = {a.name: a for a in d.actuators}
    assert acts["left/gripper"].kp == 200 and acts["left/gripper"].effort.unit == "N"  # slide -> N
    assert acts["left/shoulder"].effort.value == 9
    assert acts["left/shoulder"].source_file.name == "actuators.xml"  # from <include>
    cams = {s.name: s.attached_to for s in d.sensors}
    assert cams == {"overview": None, "left/wrist_cam": "left/finger_b"}
    assert [(c.joint1, c.joint2) for c in d.couplings] == [("left/finger_b", "left/finger_a")]


def test_mjcf_include_cannot_escape_sandbox(demo_dir):
    with pytest.raises(UnsafePath):
        parse_mjcf(demo_dir.parent / "mj" / "escape.xml")
