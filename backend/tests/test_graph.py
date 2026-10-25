from pathlib import Path

import pytest
from rdflib import Graph, URIRef

from jazari.config import get_settings
from jazari.kg import GraphStore, QueryRejected
from jazari.kg.builder import ConfigurationBuilder
from jazari.kg.namespaces import JZ
from jazari.validation import validate_graph

ROOT = get_settings().repo_root
SHAPES = ROOT / "ontology" / "validation" / "shapes.ttl"
CONFIG = URIRef("https://w3id.org/jazari/kg/demo-arm/base")


@pytest.fixture
def demo_graph(demo_manifest, demo_dir):
    robot, config = demo_manifest.configurations()[0]
    return ConfigurationBuilder(demo_manifest, robot, config, demo_dir.parent).build()


def jazari_ontology() -> Graph:
    g = Graph()
    for p in (ROOT / "ontology" / "jazari").glob("*.ttl"):
        g.parse(p)
    return g


def test_merge_urdf_and_mjcf(demo_graph):
    g, report = demo_graph
    joints = {str(g.value(j, JZ.nativeName)) for j in g.subjects(JZ.childLink, None)}
    assert joints == {"root", "shoulder_joint", "slide_joint", "tool_joint"}
    shoulder = URIRef(f"{CONFIG}/joint/shoulder_joint")
    assert len(list(g.objects(shoulder, JZ.hasMention))) == 2
    assert len(list(g.objects(shoulder, JZ.effortLimit))) == 2  # one per format, never merged
    assert (shoulder, None, JZ.RevoluteJoint) in g
    assert g.value(CONFIG, JZ.rootLink) == URIRef(f"{CONFIG}/link/base")
    assert report.counts == {"urdf": {"links": 4, "joints": 3, "actuators": 0, "sensors": 0},
                             "mjcf": {"links": 3, "joints": 3, "actuators": 2, "sensors": 1}}


def test_validation_reports_cross_format_inconsistency(demo_graph):
    g, _ = demo_graph
    rep = validate_graph(g, jazari_ontology(), SHAPES)
    assert rep.shacl_conforms, rep.shacl_results
    assert rep.ok
    assert any("shoulder_joint effortLimit: mjcf=50 vs urdf=35" in i for i in rep.inconsistencies)


def test_validation_detects_missing_link_and_bad_mass(demo_graph):
    g, _ = demo_graph
    joint = URIRef(f"{CONFIG}/joint/tool_joint")
    g.set((joint, JZ.childLink, URIRef(f"{CONFIG}/link/nowhere")))
    mass = next(g.objects(URIRef(f"{CONFIG}/link/l2"), JZ.mass))
    from rdflib import Literal, XSD
    from jazari.kg.namespaces import QUDT
    g.set((mass, QUDT.numericValue, Literal(-1.0, datatype=XSD.double)))
    rep = validate_graph(g, jazari_ontology(), SHAPES)
    assert not rep.ok
    assert any("missing link" in e for e in rep.errors)
    assert any("strictly positive" in r for r in rep.shacl_results)


def test_store_is_read_only(tmp_path):
    store = GraphStore()
    for bad in ("INSERT DATA { <a:b> <a:c> <a:d> }", "DELETE WHERE { ?s ?p ?o }",
                "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
                "SELECT * WHERE { SERVICE <http://example.org/sparql> { ?s ?p ?o } }"):
        with pytest.raises(QueryRejected):
            store.select(bad)
    assert store.select("SELECT ?s WHERE { ?s ?p ?o }") == []


def test_named_queries_parse():
    store = GraphStore()
    for q in (ROOT / "knowledge-graphs" / "queries").glob("*.rq"):
        store.select(q.read_text(encoding="utf-8"))  # raises QueryRejected if invalid


def test_ontology_files_parse():
    for p in list((ROOT / "ontology").rglob("*.ttl")):
        assert len(Graph().parse(p)) > 0, p
