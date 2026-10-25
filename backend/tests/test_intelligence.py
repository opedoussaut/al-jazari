from jazari.intelligence.composer import sanitize_citations, verify_numbers


def test_sanitize_removes_invented_citations_keeps_links():
    text = "Robot is an agent [E1]. Joints allow motion [IEEE 1872-2015, 3.1.3]. See [E9] and [docs](http://x)."
    clean, removed = sanitize_citations(text, {"E1"})
    assert clean == "Robot is an agent [E1]. Joints allow motion. See and [docs](http://x)."
    assert removed == ["[IEEE 1872-2015, 3.1.3]", "[E9]"]
from jazari.intelligence.documents import DocumentIndex
from jazari.intelligence.schemas import ToolResult


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
