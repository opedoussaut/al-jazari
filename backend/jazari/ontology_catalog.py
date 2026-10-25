"""Browsable catalog of ontology classes and properties (reference + JAZARI)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rdflib import OWL, RDF, RDFS, Graph, URIRef
from rdflib.namespace import SKOS

from .kg.namespaces import CORA, CORAX, JZ, POS_NS, RPARTS, SUMO

ORIGINS = [
    (str(CORA), "cora", "IEEE 1872-2015 CORA (via IEEE1872-owl, CC-BY-4.0)"),
    (str(CORAX), "corax", "IEEE 1872-2015 CORAX (via IEEE1872-owl, CC-BY-4.0)"),
    (str(RPARTS), "rparts", "IEEE 1872-2015 RPARTS (via IEEE1872-owl, CC-BY-4.0)"),
    (str(POS_NS), "pos", "IEEE 1872-2015 POS (via IEEE1872-owl, CC-BY-4.0)"),
    (str(SUMO), "sumo", "SUMO subset used by CORA (via IEEE1872-owl, CC-BY-4.0)"),
    (str(JZ), "jz", "JAZARI core ontology (Apache-2.0)"),
]


def _origin(uri: str) -> tuple[str, str] | None:
    for ns, prefix, label in ORIGINS:
        if uri.startswith(ns):
            return prefix, label
    return None


def curie(uri: str) -> str:
    o = _origin(uri)
    if o is None:
        return uri
    ns = next(ns for ns, p, _ in ORIGINS if p == o[0])
    return f"{o[0]}:{uri[len(ns):]}"


def expand(curie_or_uri: str) -> URIRef:
    if ":" in curie_or_uri and not curie_or_uri.startswith("http"):
        prefix, local = curie_or_uri.split(":", 1)
        for ns, p, _ in ORIGINS:
            if p == prefix:
                return URIRef(ns + local)
    return URIRef(curie_or_uri)


def humanize(local: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", local).lower()


@dataclass
class Term:
    id: str
    uri: str
    kind: str  # "class" | "property"
    label: str
    origin: str
    definition: str | None
    definition_source: str | None
    parents: list[str]


class OntologyCatalog:
    def __init__(self, graph: Graph):
        self.g = graph
        self.terms: dict[str, Term] = {}
        for kind, types in (("class", (OWL.Class,)), ("property", (OWL.ObjectProperty, OWL.DatatypeProperty))):
            for t in types:
                for s in graph.subjects(RDF.type, t):
                    if not isinstance(s, URIRef):
                        continue
                    o = _origin(str(s))
                    local = curie(str(s)).split(":", 1)[-1]
                    if o is None or local.startswith("_"):
                        continue
                    self.terms[curie(str(s))] = self._term(s, kind, o[1])

    def _term(self, s: URIRef, kind: str, origin: str) -> Term:
        g = self.g
        local = curie(str(s)).split(":", 1)[-1]
        label = g.value(s, RDFS.label)
        definition, def_src = g.value(s, SKOS.definition), None
        if definition is not None:
            def_src = "JAZARI editorial definition (not standard text)"
        else:
            definition = g.value(s, RDFS.comment)
            if definition is not None:
                def_src = f"rdfs:comment in {origin}"
        parent_prop = RDFS.subClassOf if kind == "class" else RDFS.subPropertyOf
        parents = sorted(curie(str(p)) for p in g.objects(s, parent_prop)
                         if isinstance(p, URIRef) and _origin(str(p)))
        return Term(curie(str(s)), str(s), kind, str(label) if label else humanize(local), origin,
                    str(definition) if definition is not None else None, def_src, parents)

    def classes(self) -> list[Term]:
        return sorted((t for t in self.terms.values() if t.kind == "class"), key=lambda t: t.id)

    def children(self, term_id: str) -> list[str]:
        return sorted(t.id for t in self.terms.values() if term_id in t.parents)

    def search(self, query: str, limit: int = 8) -> list[Term]:
        q = query.strip().lower().replace("_", " ")
        q_compact = q.replace(" ", "")
        scored = []
        for t in self.terms.values():
            local = t.id.split(":", 1)[1].lower()
            names = {local, t.label.lower(), humanize(t.id.split(":", 1)[1])}
            if q_compact in {n.replace(" ", "") for n in names}:
                score = 100
            elif any(n.startswith(q) for n in names):
                score = 60
            elif any(q in n for n in names) or q_compact in local:
                score = 40
            elif t.definition and q in t.definition.lower():
                score = 10
            else:
                continue
            # prefer the standard's own concept, then JAZARI, then upper-ontology helpers
            score += {"cora": 8, "rparts": 7, "corax": 6, "pos": 5, "jz": 4, "sumo": 2}[t.id.split(":")[0]]
            score += 1 if t.kind == "class" else 0
            scored.append((score, t))
        return [t for _, t in sorted(scored, key=lambda x: (-x[0], x[1].id))[:limit]]

    def mappings(self, term_id: str) -> list[dict]:
        s = expand(term_id)
        out = []
        for p in (SKOS.exactMatch, SKOS.closeMatch, SKOS.relatedMatch, OWL.equivalentClass):
            for o in self.g.objects(s, p):
                if isinstance(o, URIRef):
                    out.append({"relation": curie(str(p)) if _origin(str(p)) else p.n3(self.g.namespace_manager),
                                "target": curie(str(o))})
        return out
