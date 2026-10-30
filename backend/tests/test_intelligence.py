from types import SimpleNamespace

from jazari.evaluation import fact_present, score_item
from jazari.intelligence.composer import sanitize_citations, verify_numbers
from jazari.intelligence.documents import DocumentIndex
from jazari.intelligence.schemas import ToolResult, Verification


def test_sanitize_removes_invented_citations_keeps_links():
    text = "Robot is an agent [E1]. Joints allow motion [IEEE 1872-2015, 3.1.3]. See [E9] and [docs](http://x)."
    clean, removed = sanitize_citations(text, {"E1"})
    assert clean == "Robot is an agent [E1]. Joints allow motion. See and [docs](http://x)."
    assert removed == ["[IEEE 1872-2015, 3.1.3]", "[E9]"]
    clean, removed = sanitize_citations("39 joints [joint_summary].", {"E1"}, frozenset({"joint_summary"}))
    assert clean == "39 joints." and removed == ["[joint_summary]"]


def test_document_chunks_keep_lines_and_table_header(demo_manifest, demo_dir):
    idx = DocumentIndex.from_manifest(demo_manifest, demo_dir.parent)
    hits = idx.search("slide effort")
    assert hits, "expected a hit"
    top = hits[0][1]
    assert "| motor | joints | effort |" in top.text
    assert top.url.endswith(f"#L{top.start_line}-L{top.end_line}")


def test_verify_numbers_flags_invented_values():
    results = [ToolResult(tool="joint_summary", arguments={}, summary={"total": 39, "revolute": 29})]
    ok = verify_numbers("It has 39 joints, 29 revolute [E1], see `g1_29dof`.", "q", results)
    assert ok.unsupported_numbers == []
    bad = verify_numbers("It has 43 joints and weighs 35.5 kg.", "q", results)
    assert bad.unsupported_numbers == ["35.5", "43"]
    lines = [ToolResult(tool="joint_details", arguments={}, summary={"mentions": "urdf:revolute@L161"})]
    assert verify_numbers("1. Defined at line 161.", "q", lines).unsupported_numbers == []


def test_scorer_accepts_spelled_out_names_and_abstention_wording():
    assert fact_present("ankle_pitch", "the left ankle pitch joint")
    assert fact_present("four-bar", "a **four-bar** linkage")
    assert not fact_present("ankle_pitch", "the left ankle roll joint")
    resp = SimpleNamespace(trace=[], answer="The gear ratio cannot be determined from the results.",
                           verification=Verification(numbers_checked=0, unsupported_numbers=[]),
                           planner="llm", composer="llm", latency_ms=1)
    assert score_item({"id": "x", "category": "abstention", "question": "q", "abstain": True}, resp)["answer_ok"]

