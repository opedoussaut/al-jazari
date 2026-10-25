"""Knowledge-graph quality checks: SHACL shapes plus structural checks that SHACL
cannot express well (tree topology, cross-format consistency)."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pyshacl import validate
from rdflib import RDF, Graph

from .kg.namespaces import JZ, QUDT

LIMIT_TOLERANCE = 1e-4


@dataclass
class ValidationReport:
    shacl_conforms: bool = True
    shacl_results: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    inconsistencies: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.shacl_conforms and not self.errors

    def as_dict(self) -> dict:
        return {
            "ok": self.ok, "shacl_conforms": self.shacl_conforms,
            "shacl_results": self.shacl_results, "errors": self.errors,
            "warnings": self.warnings, "inconsistencies": self.inconsistencies,
        }


def run_shacl(data: Graph, ontology: Graph, shapes_path: Path, report: ValidationReport) -> None:
    shapes = Graph().parse(shapes_path, format="turtle")
    conforms, results_graph, _ = validate(
        data, shacl_graph=shapes, ont_graph=ontology, inference="rdfs", advanced=True
    )
    report.shacl_conforms = bool(conforms)
    SH = "http://www.w3.org/ns/shacl#"
    for res in results_graph.query(
        f"SELECT ?focus ?path ?msg WHERE {{ ?r a <{SH}ValidationResult> ; <{SH}focusNode> ?focus ;"
        f" <{SH}resultMessage> ?msg . OPTIONAL {{ ?r <{SH}resultPath> ?path }} }}"
    ):
        report.shacl_results.append(f"{res.focus} {res.path or ''}: {res.msg}")


def _has_cycle(edges: dict, seen: set) -> bool:
    """Depth-first search over parent->children edges; fills `seen` with reachable nodes."""
    stack: set = set()

    def dfs(n) -> bool:
        if n in stack:
            return True
        if n in seen:
            return False
        seen.add(n)
        stack.add(n)
        cyc = any(dfs(m) for m in edges.get(n, []))
        stack.discard(n)
        return cyc

    return any(dfs(n) for n in list(edges))


def structural_checks(data: Graph, report: ValidationReport) -> None:
    for config in data.subjects(RDF.type, JZ.RobotConfiguration):
        elements = set(data.objects(config, JZ.hasElement))
        links = {e for e in elements if (e, RDF.type, JZ.Link) in data}
        joints = [e for e in elements if data.value(e, JZ.childLink) is not None]
        names = Counter(str(data.value(e, JZ.nativeName)) + str(data.value(e, RDF.type)) for e in elements)
        for n, c in names.items():
            if c > 1:
                report.errors.append(f"duplicate element identifier {n}")

        parents_of: dict = defaultdict(list)
        for j in joints:
            child, parent = data.value(j, JZ.childLink), data.value(j, JZ.parentLink)
            for end in (child, parent):
                if end is not None and end not in links:
                    report.errors.append(f"{data.value(j, JZ.nativeName)}: references missing link {end}")
            if parent is not None:
                parents_of[child].append(j)
            if parent is not None and parent == child:
                report.errors.append(f"{data.value(j, JZ.nativeName)}: parent and child are the same link")
        for child, js in parents_of.items():
            if len(js) > 1:
                report.errors.append(
                    f"link {data.value(child, JZ.nativeName)} has {len(js)} parent joints (not a tree)")

        # cycle check over link graph
        edges = defaultdict(list)
        for j in joints:
            if data.value(j, JZ.parentLink) is not None:
                edges[data.value(j, JZ.parentLink)].append(data.value(j, JZ.childLink))
        seen: set = set()
        if _has_cycle(edges, seen):
            report.errors.append("kinematic graph contains a cycle")

        disconnected = links - seen - set(data.objects(config, JZ.rootLink))
        for link in sorted(disconnected):
            if not any(data.value(j, JZ.childLink) == link for j in joints):
                report.warnings.append(f"link {data.value(link, JZ.nativeName)} is not connected by any joint")

        # actuators must target existing joints
        for a in elements:
            if (a, RDF.type, JZ.Actuator) in data:
                j = data.value(a, JZ.drivesJoint)
                if j is not None and j not in elements:
                    report.errors.append(f"actuator {data.value(a, JZ.nativeName)} drives missing joint {j}")

        cross_format_checks(data, joints, report)


def cross_format_checks(data: Graph, joints: list, report: ValidationReport) -> None:
    """Compare the same quantity stated in different source formats."""
    for j in joints:
        name = data.value(j, JZ.nativeName)
        for prop in (JZ.lowerLimit, JZ.upperLimit, JZ.effortLimit, JZ.velocityLimit):
            per_file = Counter(data.value(q, JZ.describedIn) for q in data.objects(j, prop))
            for f, n in per_file.items():
                if n > 1:
                    report.errors.append(f"{name} {prop.split('#')[-1]}: {n} values from the same file {f}")
        formats = {str(data.value(m, JZ.sourceFormat)) for m in data.objects(j, JZ.hasMention)}
        if len(formats) < 2:
            continue
        for prop in (JZ.lowerLimit, JZ.upperLimit, JZ.effortLimit, JZ.velocityLimit):
            values = {}
            for q in data.objects(j, prop):
                fmt = str(data.value(data.value(q, JZ.describedIn), JZ.sourceFormat))
                values[fmt] = (float(data.value(q, QUDT.numericValue)), data.value(q, QUDT.unit))
            if len(values) == 2:
                (fa, (va, ua)), (fb, (vb, ub)) = sorted(values.items())
                if ua != ub:
                    report.errors.append(f"{name} {prop.split('#')[-1]}: unit mismatch {ua} vs {ub}")
                elif abs(va - vb) > LIMIT_TOLERANCE * max(1.0, abs(va)):
                    report.inconsistencies.append(
                        f"{name} {prop.split('#')[-1]}: {fa}={va:g} vs {fb}={vb:g} {str(ua).rsplit('/', 1)[-1]}")
            elif len(values) == 1 and len(formats) == 2:
                fmt = next(iter(values))
                report.warnings.append(
                    f"{name} {prop.split('#')[-1]}: stated only in {fmt}")


def validate_graph(data: Graph, ontology: Graph, shapes_path: Path) -> ValidationReport:
    report = ValidationReport()
    run_shacl(data, ontology, shapes_path, report)
    structural_checks(data, report)
    return report
