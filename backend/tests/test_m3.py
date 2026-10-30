"""Integration tests for Berkeley Humanoid Lite and ALOHA 2 at their pinned revisions
(lite_description@e582f6b, mujoco_menagerie@f3b6013). Expected values were checked by hand
against the upstream files and READMEs."""

import pytest
from fastapi.testclient import TestClient

from jazari.config import get_settings
from jazari.ingestion import parse_urdf, parse_xacro
from jazari.intelligence.engine import get_engine
from jazari.intelligence.planner import rule_plan

pytestmark = pytest.mark.sources


@pytest.fixture(scope="module")
def tb():
    return get_engine().toolbox


def summary(tb, tool, cfg, **kw):
    r = tb.run(tool, {"configuration": cfg, **kw}, None)
    assert r.ok, r.error
    return r.summary


def test_variant_resolution(tb):
    assert tb.resolve_configuration("Berkeley Humanoid Lite")["id"] == "lite"
    assert tb.resolve_configuration("berkeley lite biped")["id"] == "lite-biped"
    assert tb.resolve_configuration("ALOHA 2")["id"] == "aloha-2-menagerie"
    assert [c["id"] for c in tb.mentioned_configurations("Compare the G1 arm with Berkeley Humanoid Lite")] == \
        ["g1-29dof-rev-1-0", "lite"]


def test_xacro_expansion_matches_generated_urdf():
    root = get_settings().sources_dir / "lite_description"
    robots = root / "lite_description" / "robots"
    x = parse_xacro(robots / "lite/xacro/lite.urdf.xacro", root, {"lite_description": root / "lite_description"}) \
        if (robots / "lite/xacro").exists() else None
    if x is None:
        pytest.skip("lite Xacro not in the sparse checkout")
    u = parse_urdf(robots / "lite/urdf/lite.urdf")
    key = {j.name: (j.parent, j.child, j.source_type, j.upper and j.upper.value, j.effort and j.effort.value)
           for j in u.joints}
    assert {j.name: (j.parent, j.child, j.source_type, j.upper and j.upper.value, j.effort and j.effort.value)
            for j in x.joints if j.name in key} == key


def test_berkeley_lite_full_body(tb):
    s = summary(tb, "joint_summary", "lite")
    assert s["joints_by_class"] == {"RevoluteJoint": 72, "FixedJoint": 1}
    assert s["articulated_dof"] == 72 and s["hand_or_finger_joints"]["count"] == 40
    assert s["articulated_dof_without_hands"] == 32 and s["floating_base"] is None
    regions = {k: v["count"] for k, v in s["movable_joints_by_body_region"].items()}
    assert regions == {"left_arm": 7, "left_hand": 20, "left_leg": 7, "neck": 3,
                       "right_arm": 7, "right_hand": 20, "right_leg": 7, "waist": 1}
    assert summary(tb, "actuators", "lite")["actuator_count"] == 72


def test_berkeley_biped_hardware_actuators(tb):
    s = summary(tb, "actuators", "lite biped")
    assert s["actuator_count"] == 14
    assert s["actuator_models"] == {"rs-00": 4, "rs-02": 2, "rs-05": 2, "rs-06": 6}
    knee = next(a for a in s["actuators"] if a["name"] == "left_knee_pitch")
    assert knee["address"] == "can_id=34" and knee["model"] == "rs-06"
    assert knee["stated_in"]["xacro"]["effort_limit"] == "36 N-M" and knee["stated_in"]["xacro"]["current_limit_A"] == 43
    ankle = next(a for a in s["actuators"] if a["name"] == "left_ankle_pitch")
    assert ankle["transmission"] == "four-bar linkage"
    j = summary(tb, "joint_summary", "lite biped")
    assert j["articulated_dof"] == 14 and j["floating_base"]["dof"] == 6


def test_hardware_facts_are_attributed_to_their_format(tb):
    assert summary(tb, "actuators", "lite-biped")["hardware_facts_only_in"] == ["xacro"]
    assert summary(tb, "actuators", "g1-29dof-rev-1-0")["hardware_facts_only_in"] == []


def test_aloha_bimanual(tb):
    s = summary(tb, "joint_summary", "aloha 2")
    assert s["category"] == "bimanual manipulator"
    assert s["joints_by_class"] == {"RevoluteJoint": 12, "PrismaticJoint": 4, "FixedJoint": 4}
    assert s["articulated_dof"] == 16 and s["independent_dof"] == 14 and len(s["joint_couplings"]) == 2
    regions = {k: v["count"] for k, v in s["movable_joints_by_body_region"].items()}
    assert regions == {"left_arm": 6, "left_hand": 2, "right_arm": 6, "right_hand": 2}
    k = summary(tb, "kinematic_structure", "aloha 2")
    assert k["separate_kinematic_trees"] == 2 and k["floating_base"] is None
    a = summary(tb, "actuators", "aloha 2")
    assert a["actuator_count"] == 14 and "actuator/motor model" in a["not_stated_in_any_source_file"]
    cams = {x["name"]: x["mounted_on"] for x in summary(tb, "sensors", "aloha 2")["sensors"]}
    assert cams["wrist_cam_left"] == "left/gripper_base" and cams["teleoperator_pov"] == "world frame"


def test_comparison_plan_and_api(tb):
    calls = rule_plan(tb, "Compare the kinematic structure of Unitree G1 and Berkeley Humanoid Lite")
    assert [(c.name, c.arguments["configuration"]) for c in calls] == [
        ("kinematic_structure", "g1-29dof-rev-1-0"), ("kinematic_structure", "lite")]
    from jazari.api.app import app

    cols = TestClient(app).post("/api/v1/compare", json={"configurations": ["g1", "berkeley", "aloha"]}).json()["columns"]
    legs = [c["values"]["leg joints"] for c in cols]
    assert legs == [12, 14, "not applicable (bimanual manipulator)"]
    assert [c["values"]["independent DoF (after joint couplings)"] for c in cols] == [29, 72, 14]


def test_joint_name_identifies_robot_when_unique(tb):
    r = tb.run("joint_details", {"joint": "left_knee_joint"}, None)  # only the G1 uses this name
    assert r.ok and r.configuration == "g1-29dof-rev-1-0"
    r = tb.run("joint_details", {"joint": "left_hip_pitch"}, None)  # in both Berkeley configurations
    assert not r.ok and "ask the user which one" in r.error


def test_planner_cannot_pick_an_unnamed_variant():
    from jazari.intelligence.schemas import ToolCall

    engine = get_engine()
    calls = [ToolCall(name="joint_summary", arguments={"configuration": "lite-biped"})]
    notes = engine._enforce_variant_choice(calls, "How many DoF does the Berkeley Humanoid Lite have without hands?")
    assert calls[0].arguments["configuration"] == "lite" and notes
    calls = [ToolCall(name="actuators", arguments={"configuration": "lite-biped"})]
    assert engine._enforce_variant_choice(calls, "Which motors drive the Berkeley lite biped?") == []
    assert calls[0].arguments["configuration"] == "lite-biped"
