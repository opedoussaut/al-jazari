"""In-process RDF store (rdflib) holding reference ontologies, the JAZARI ontology and
generated robot knowledge graphs.

Only read queries are accepted: queries are compiled with rdflib's query parser,
which rejects SPARQL Update, and SERVICE clauses are refused so that no query can
reach the network. The store interface is small on purpose so that it can be
replaced by Apache Jena Fuseki when a persistent SPARQL service is needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rdflib import Graph
from rdflib.plugins.sparql import prepareQuery

from .namespaces import PREFIXES, sparql_prefixes

# Reference ontology modules loaded from the pinned IEEE1872-owl checkout.
IEEE1872_MODULES = ["cora", "cora-bare", "corax", "rparts", "sumo-cora", "annotation", "pos"]

_SERVICE = re.compile(r"\bSERVICE\b", re.IGNORECASE)


class QueryRejected(ValueError):
    pass


@dataclass
class LoadedFiles:
    reference: list[Path]
    jazari: list[Path]
    knowledge_graphs: list[Path]


class GraphStore:
    def __init__(self) -> None:
        self.graph = Graph()
        for k, v in PREFIXES.items():
            self.graph.bind(k, v)
        self.files = LoadedFiles([], [], [])

    @classmethod
    def load(cls, ontology_dir: Path, sources_dir: Path, generated_dir: Path) -> GraphStore:
        store = cls()
        ref_dir = sources_dir / "ieee1872_owl"
        for name in IEEE1872_MODULES:
            p = ref_dir / f"{name}.owl"
            if p.exists():
                store.graph.parse(p, format="xml")
                store.files.reference.append(p)
        for p in sorted((ontology_dir / "jazari").glob("*.ttl")) + sorted(
            (ontology_dir / "alignments").glob("*.ttl")
        ):
            store.graph.parse(p, format="turtle")
            store.files.jazari.append(p)
        for p in sorted(generated_dir.glob("*.ttl")):
            store.graph.parse(p, format="turtle")
            store.files.knowledge_graphs.append(p)
        return store

    def select(self, query: str, bindings: dict | None = None) -> list[dict[str, object]]:
        if _SERVICE.search(query):
            raise QueryRejected("SERVICE clauses are not allowed")
        try:
            q = prepareQuery(sparql_prefixes() + query)
        except Exception as e:
            raise QueryRejected(f"not a valid read-only SPARQL query: {e}") from e
        if q.algebra.name != "SelectQuery":
            raise QueryRejected("only SELECT queries are allowed")
        result = self.graph.query(q, initBindings=bindings or {})
        names = [str(v) for v in result.vars]
        rows = []
        for row in result:
            rows.append({n: (v.toPython() if v is not None else None) for n, v in zip(names, row)})
        return rows

    def __len__(self) -> int:
        return len(self.graph)
