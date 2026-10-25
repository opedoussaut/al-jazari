"""Integration tests against the pinned Unitree G1 sources (expected values were checked
by hand against g1_29dof_rev_1_0.urdf / .xml at unitree_ros@15ebe53)."""

import pytest
from fastapi.testclient import TestClient

from jazari.intelligence.engine import get_engine
from jazari.intelligence.planner import rule_plan

pytestmark = pytest.mark.sources


@pytest.fixture(scope="module")
def engine():
    return get_engine()


def run(engine, tool, **args):
    r = engine.toolbox.run(tool, args, None)
    assert r.ok, r.error
    return r


def test_joint_counts(engine):
    s = run(engine, "joint_summary", configuration="unitree g1").summary
    assert s["total_joints_in_graph"] == 39
    assert s["joints_by_class"] == {"RevoluteJoint": 29, "FixedJoint": 9, "FloatingJoint": 1}
    assert s["joints_by_source_format"]["urdf"] == {"total": 38, "revolute": 29, "fixed": 9}
    assert s["joints_by_source_format"]["mjcf"] == {"total": 30, "hinge": 29, "free": 1}
    assert s["articulated_dof"] == 29 and s["actuated_joints"] == 29
    assert s["movable_joints_without_actuator"] == []
    assert s["floating_base"]["dof"] == 6
    regions = {k: v["count"] for k, v in s["movable_joints_by_body_region"].items()}
    assert regions == {"left_arm": 7, "left_leg": 6, "right_arm": 7, "right_leg": 6, "waist": 3}


def test_placeholder_configuration_uses_session_robot(engine):
    r = engine.toolbox.run("actuators", {"configuration": "None"}, "g1-29dof-rev-1-0")
    assert r.ok and r.summary["actuator_count"] == 29
    # fresh session, no robot named, several robots in the graph: ask which one
    r = engine.toolbox.run("actuators", {"configuration": "None"}, None)
    assert not r.ok and "ask the user which one" in r.error


def test_kinematic_chains(engine):
    s = run(engine, "kinematic_structure", configuration="g1-29dof-rev-1-0").summary
    assert [r["link"] for r in s["root_links"]] == ["pelvis"]
    lengths = sorted(c["length"] for c in s["serial_chains"])
    assert lengths == [6, 6, 10, 10]  # 2 legs; waist(3) + arm(7) twice


def test_actuators_sensors_and_inconsistencies(engine):
    assert run(engine, "actuators", configuration="g1").summary["actuator_count"] == 29
    sensors = run(engine, "sensors", configuration="g1").summary
    assert sorted(x["type"] for x in sensors["sensors"]) == ["accelerometer", "accelerometer", "gyro", "gyro"]
    inc = run(engine, "source_inconsistencies", configuration="g1").summary
    assert len(inc["cross_format_inconsistencies"]) == 6
    assert any("left_ankle_pitch_joint effortLimit: mjcf=50 vs urdf=35" in i
               for i in inc["cross_format_inconsistencies"])


def test_joint_details_have_line_evidence(engine):
    r = run(engine, "joint_details", configuration="g1", joint="left_knee_joint")
    q = {(x["property"], x["format"]): x["value"] for x in r.summary["quantities"]}
    assert q[("effortLimit", "urdf")] == 139 and q[("velocityLimit", "urdf")] == 20
    assert any(e.url.endswith("g1_29dof_rev_1_0.urdf#L166") for e in r.evidence)


def test_ontology_lookup_robot(engine):
    s = run(engine, "ontology_lookup", term="Robot").summary
    assert s["id"] == "cora:Robot"
    assert {"sumo:Agent", "sumo:Device"} <= set(s["direct_superclasses"])
    assert any(p["property"] == "rparts:robotSensingPart" and p["ieee_1872_axiom"] == "8.1.3"
               for p in s["properties"])


def test_unknown_robot_is_not_answered_with_g1(engine):
    r = engine.toolbox.run("joint_summary", {"configuration": "Boston Dynamics Atlas"}, "g1-29dof-rev-1-0")
    assert not r.ok and "not in the knowledge graph" in r.error
    calls = rule_plan(engine.toolbox, "How many joints does ALOHA 2 have?")
    assert calls[0].arguments["configuration"] == "aloha-2-menagerie"


def test_chat_api_without_llm():
    from jazari.api.app import app

    c = TestClient(app)
    r = c.post("/api/v1/chat", json={"question": "How many joints does the Unitree G1 have, and of which types?",
                                     "use_llm": False}).json()
    assert r["planner"] == "rules" and "39 joints" in r["answer"]
    assert r["context"]["configuration"] == "g1-29dof-rev-1-0"
    assert r["context"]["source_revision"].endswith("15ebe53f4cd77e7d745ae83b9d7ff90e685e8998")
    assert r["evidence"][0]["url"].startswith("https://github.com/unitreerobotics/unitree_ros/blob/15ebe53")


@pytest.mark.ollama
def test_end_to_end_with_llm(engine):
    r = engine.ask("How many joints are defined in the selected Unitree G1 configuration, and what are their types?",
                   session_id="pytest")
    assert r.planner == "llm" and r.composer == "llm"
    assert any(t.tool == "joint_summary" and t.ok for t in r.trace)
    assert "39" in r.answer and "29" in r.answer
    assert r.verification.unsupported_numbers == [], r.answer
