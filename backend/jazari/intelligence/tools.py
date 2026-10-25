"""The fixed catalog of read-only knowledge tools JAZARI can call.

Every tool executes named SPARQL queries from knowledge-graphs/queries/ (parameters are
passed as SPARQL bindings, never spliced into query text), performs any arithmetic in
Python, and returns structured facts plus evidence. The LLM chooses tools and phrases
answers; it never computes the numbers.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdflib import URIRef

from ..config import Settings
from ..kg import GraphStore
from ..kg.namespaces import JZR
from ..manifest import Manifest
from ..ontology_catalog import OntologyCatalog, curie, expand
from .documents import DocumentIndex
from .schemas import Evidence, ToolResult


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, str]  # name -> description
    fn: Callable[..., ToolResult]
    needs_configuration: bool = True


def _short(rev: str) -> str:
    return rev[:7]


class Toolbox:
    def __init__(self, settings: Settings, store: GraphStore, manifest: Manifest,
                 catalog: OntologyCatalog, docs: DocumentIndex):
        self.s, self.store, self.m, self.catalog, self.docs = settings, store, manifest, catalog, docs
        self.query_dir = settings.repo_root / "knowledge-graphs" / "queries"
        self.specs: dict[str, ToolSpec] = {}
        for spec in [
            ToolSpec("list_robots", "List robot models and configurations in the knowledge graph.",
                     {}, self.list_robots, needs_configuration=False),
            ToolSpec("configuration_info",
                     "Identity of a robot configuration: variant, why it was selected, source files, "
                     "pinned revisions and licenses.", {"configuration": "configuration id or robot name"},
                     self.configuration_info),
            ToolSpec("joint_summary",
                     "Count and classify all joints of a configuration (revolute, fixed, floating ...), "
                     "degrees of freedom, actuated joints, and how URDF and MJCF differ.",
                     {"configuration": "configuration id or robot name"}, self.joint_summary),
            ToolSpec("kinematic_structure",
                     "Kinematic tree of a configuration: root link, serial chains (legs, arms, waist) "
                     "and parent/child link connectivity.",
                     {"configuration": "configuration id or robot name"}, self.kinematic_structure),
            ToolSpec("joint_details",
                     "Limits (position, effort, velocity), axis, parent/child and source lines of one joint.",
                     {"configuration": "configuration id or robot name",
                      "joint": "joint name, e.g. left_knee_joint"}, self.joint_details),
            ToolSpec("actuators", "Actuators of a configuration and the joints they drive.",
                     {"configuration": "configuration id or robot name"}, self.actuators),
            ToolSpec("sensors", "Sensors of a configuration and the links they are mounted on.",
                     {"configuration": "configuration id or robot name"}, self.sensors),
            ToolSpec("links_and_masses",
                     "Links (rigid bodies) of a configuration and their masses as stated per source file.",
                     {"configuration": "configuration id or robot name"}, self.links_and_masses),
            ToolSpec("source_inconsistencies",
                     "Disagreements between source files (e.g. URDF vs MJCF limits) and values stated in "
                     "only one format, from the validation report.",
                     {"configuration": "configuration id or robot name"}, self.source_inconsistencies),
            ToolSpec("ontology_lookup",
                     "Look up a robotics concept in the reference ontologies (IEEE 1872 CORA, CORAX, "
                     "RPARTS, POS) and the JAZARI ontology: definition, superclasses, properties, "
                     "standard axiom numbers and knowledge-graph instances.",
                     {"term": "concept name, e.g. Robot, robot part, actuator, joint"},
                     self.ontology_lookup, needs_configuration=False),
            ToolSpec("search_documents",
                     "Keyword search in indexed technical documents (robot READMEs, motor tables).",
                     {"query": "search words"}, self.search_documents, needs_configuration=False),
        ]:
            self.specs[spec.name] = spec

    # ------------------------------------------------------------------ helpers
    def query_text(self, name: str) -> str:
        return (self.query_dir / f"{name}.rq").read_text(encoding="utf-8")

    def run_query(self, result: ToolResult, name: str, **bindings: Any) -> list[dict]:
        text = self.query_text(name)
        rows = self.store.select(text, bindings)
        result.query_name = result.query_name or name
        result.queries.append(f"# {name}.rq  bindings={ {k: str(v) for k, v in bindings.items()} }\n{text}")
        result.row_count += len(rows)
        return rows

    def configurations(self) -> list[dict]:
        out = []
        for robot, c in self.m.configurations():
            out.append({"id": c.id, "robot_id": robot.id, "robot": robot.name, "label": c.label,
                        "native_name": c.native_name, "baseline": c.baseline, "category": robot.category,
                        "uri": f"{JZR}{robot.id}/{c.id}"})
        return out

    def resolve_configuration(self, text: str | None) -> dict | None:
        if not text:
            return None
        t = text.strip().lower()
        configs = self.configurations()
        for c in configs:
            if t in (c["id"], c["native_name"].lower(), c["uri"].lower()):
                return c
        tokens = set(t.replace("-", " ").replace("_", " ").split())
        matches = [c for c in configs
                   if tokens & set(f"{c['robot']} {c['robot_id']}".lower().replace("-", " ").split())]
        baseline = [c for c in matches if c["baseline"]]
        return (baseline or matches or [None])[0]

    def file_evidence(self, result: ToolResult, config_uri: str) -> list[dict]:
        files = self.run_query(result, "configuration_files", config=URIRef(config_uri))
        for f in files:
            result.evidence.append(Evidence(
                label=f"{f['label']} ({f['format'] or f['kind']})",
                evidence_type="extracted" if f["kind"] == "description" else "document",
                url=f["url"],
                source=f"{f['repo'].rsplit('/', 1)[-1]}@{_short(f['revision'])} {f['path']}",
                detail=f"license {f['license']}, sha256 {f['sha256'][:12]}",
            ))
        return files

    # ------------------------------------------------------------------ tools
    def list_robots(self) -> ToolResult:
        r = ToolResult(tool="list_robots", arguments={})
        rows = self.run_query(r, "robots")
        r.data = rows
        r.summary = {"robots": [{"model": x["modelLabel"], "category": x["category"],
                                 "configuration": x["config"].rsplit("/", 1)[-1],
                                 "label": x["configLabel"], "baseline": x["baseline"]} for x in rows]}
        r.summary["note"] = ("Only the robots listed are ingested so far. Berkeley Humanoid Lite and "
                             "ALOHA 2 are planned for milestone M3 and are not in the graph yet.")
        return r

    def configuration_info(self, configuration: dict) -> ToolResult:
        r = ToolResult(tool="configuration_info", arguments={"configuration": configuration["id"]},
                       configuration=configuration["id"])
        cfg = next(c for _, c in self.m.configurations() if c.id == configuration["id"])
        files = self.file_evidence(r, configuration["uri"])
        r.data = {"configuration": configuration, "files": files,
                  "selection_rationale": cfg.selection_rationale.strip()}
        r.summary = {
            "configuration": configuration["label"], "native_name": configuration["native_name"],
            "mode_machine": cfg.mode_machine, "selection_rationale": cfg.selection_rationale.strip(),
            "files": [{"file": f["label"], "kind": f["kind"], "format": f["format"],
                       "revision": f["revision"], "license": f["license"]} for f in files],
        }
        return r

    def joint_summary(self, configuration: dict) -> ToolResult:
        c = URIRef(configuration["uri"])
        r = ToolResult(tool="joint_summary", arguments={"configuration": configuration["id"]},
                       configuration=configuration["id"])
        counts = self.run_query(r, "joint_type_counts", config=c)
        joints = self.run_query(r, "joints", config=c)
        self.file_evidence(r, configuration["uri"])

        by_format: dict[str, Counter] = defaultdict(Counter)
        for j in joints:
            for m in j["mentions"].split(" | "):
                fmt, rest = m.split(":", 1)
                by_format[fmt][rest.split("@")[0]] += 1
        movable = [j for j in joints if j["class"] not in ("FixedJoint", "FloatingJoint")]
        floating = [j for j in joints if j["class"] == "FloatingJoint"]
        actuated = [j for j in joints if j["actuator"]]
        unactuated_movable = [j["name"] for j in movable if not j["actuator"]]

        notes = []
        if len(by_format) > 1:
            parts = [f"the {fmt.upper()} file defines {sum(cnt.values())} joints ("
                     + ", ".join(f"{n} {t}" for t, n in cnt.most_common()) + ")"
                     for fmt, cnt in sorted(by_format.items(), reverse=True)]
            notes.append("The source formats differ: " + "; ".join(parts) + ".")
        only = defaultdict(list)
        for j in joints:
            fmts = {m.split(":", 1)[0] for m in j["mentions"].split(" | ")}
            if len(fmts) == 1 and len(by_format) > 1:
                only[next(iter(fmts))].append(j["name"])
        for fmt, names in sorted(only.items()):
            notes.append(f"Joints stated only in {fmt.upper()}: {', '.join(names)}.")
        if floating and "urdf" in by_format and "urdf" not in floating[0]["mentions"]:
            notes.append("The URDF has no floating base joint (it is commented out in the file); the MJCF "
                         "declares the pelvis free joint, which adds 6 unactuated DoF for the base.")

        r.derivations = [
            "total joints = number of distinct jz:Joint elements of the configuration (union of URDF and MJCF, merged by native name)",
            "articulated DoF = sum of jz:degreesOfFreedom over joints that are neither fixed nor floating",
            "actuated joints = joints targeted by an MJCF <motor>/<position>/... element (jz:drivesJoint)",
            "per-format counts = joints grouped by the jz:SourceMention of each file",
            ("movable joints by body region = grouping by native-name pattern (left_/right_ + hip/knee/ankle "
            "= leg, shoulder/elbow/wrist = arm, waist, neck/head); a naming convention, not a source statement"),
        ]
        regions: dict[str, list[str]] = defaultdict(list)
        for j in movable:
            n = j["name"]
            side = "left_" if n.startswith("left_") else "right_" if n.startswith("right_") else ""
            if any(k in n for k in ("hip", "knee", "ankle")):
                region = f"{side}leg"
            elif any(k in n for k in ("shoulder", "elbow", "wrist")):
                region = f"{side}arm"
            elif "waist" in n:
                region = "waist"
            elif any(k in n for k in ("neck", "head")):
                region = "neck"
            else:
                region = "other"
            regions[region].append(n)
        r.summary = {
            "configuration": configuration["label"],
            "total_joints_in_graph": len(joints),
            "important_notes": notes,
            "joints_by_class": {x["class"]: int(x["count"]) for x in counts},
            "joints_by_source_format": {fmt: {"total": sum(cnt.values()), **dict(cnt)}
                                        for fmt, cnt in sorted(by_format.items())},
            "articulated_joints": len(movable),
            "articulated_dof": sum(int(j["dof"]) for j in movable),
            "movable_joints_by_body_region": {k: {"count": len(v), "joints": v}
                                              for k, v in sorted(regions.items())},
            "floating_base": ({"joint": floating[0]["name"], "dof": int(floating[0]["dof"]),
                               "stated_in": floating[0]["mentions"]} if floating else None),
            "actuated_joints": len(actuated),
            "movable_joints_without_actuator": unactuated_movable,
            "fixed_joints": [j["name"] for j in joints if j["class"] == "FixedJoint"],
            "hand_or_finger_joints": [j["name"] for j in joints
                                      if any(k in j["name"] for k in ("finger", "thumb", "index", "hand"))
                                      and j["class"] != "FixedJoint"],
        }
        r.data = {"counts": counts, "joints": joints}
        return r

    def kinematic_structure(self, configuration: dict) -> ToolResult:
        c = URIRef(configuration["uri"])
        r = ToolResult(tool="kinematic_structure", arguments={"configuration": configuration["id"]},
                       configuration=configuration["id"])
        joints = self.run_query(r, "joints", config=c)
        self.file_evidence(r, configuration["uri"])
        children: dict[str, list[dict]] = defaultdict(list)
        child_links = set()
        for j in joints:
            if j["parent"]:
                children[j["parent"]].append(j)
                child_links.add(j["child"])
        roots = sorted({j["parent"] for j in joints if j["parent"]} - child_links)
        root = roots[0] if roots else None

        def tree(link: str) -> dict:
            return {"link": link, "children": [
                {"joint": j["name"], "class": j["class"], "dof": int(j["dof"]), "axis": j["axis"],
                 "actuated": bool(j["actuator"]), **tree(j["child"])}
                for j in sorted(children.get(link, []), key=lambda x: x["name"])]}

        chains: list[list[str]] = []

        def walk(link: str, path: list[str]) -> None:
            kids = children.get(link, [])
            if not kids:
                chains.append(path)
            for j in kids:
                walk(j["child"], path + ([j["name"]] if j["class"] not in ("FixedJoint",) else []))

        if root:
            walk(root, [])
        unique = {tuple(ch) for ch in chains if ch}
        maximal = sorted([list(ch) for ch in unique
                          if not any(len(o) > len(ch) and o[:len(ch)] == ch for o in unique)],
                         key=lambda ch: ch[-1])
        r.derivations = [
            "tree built from jz:parentLink/jz:childLink of every joint; root = link that is never a child",
            ("serial chains = movable-joint sequences from the root to each leaf link; chains that are a "
            "prefix of a longer chain are omitted; fixed joints are skipped"),
        ]
        floating = [j for j in joints if j["class"] == "FloatingJoint"]
        r.summary = {
            "configuration": configuration["label"], "root_link": root,
            "floating_base": floating[0]["name"] + " (6 DoF, stated only in MJCF)" if floating else None,
            "serial_chains": [{"end_link_of_chain": _chain_end(ch, joints), "movable_joints": ch,
                               "length": len(ch)} for ch in maximal],
            "branching": {link: [j["name"] for j in ks] for link, ks in children.items() if len(ks) > 1},
        }
        r.data = {"root": root, "tree": tree(root) if root else None, "chains": maximal}
        return r

    def joint_details(self, configuration: dict, joint: str) -> ToolResult:
        c = URIRef(configuration["uri"])
        r = ToolResult(tool="joint_details", arguments={"configuration": configuration["id"], "joint": joint},
                       configuration=configuration["id"])
        joints = self.run_query(r, "joints", config=c)
        name = joint.strip().lower().replace(" ", "_")
        match = next((j for j in joints if j["name"] == name), None) or next(
            (j for j in joints if name in j["name"]), None)
        if match is None:
            r.ok, r.error = False, f"no joint named {joint!r}; known joints: {', '.join(j['name'] for j in joints)}"
            return r
        quantities = [q for q in self.run_query(r, "joint_quantities", config=c) if q["name"] == match["name"]]
        for q in quantities:
            r.evidence.append(Evidence(
                label=f"{match['name']} {q['property']} = {q['value']:g} {q['unit']} ({q['format']})",
                evidence_type="extracted", url=f"{q['fileUrl']}#L{q['line']}" if q["line"] else q["fileUrl"],
                detail=f"attribute {q['attribute']}"))
        r.summary = {"joint": match["name"], "class": match["class"], "dof": match["dof"],
                     "parent_link": match["parent"], "child_link": match["child"], "axis": match["axis"],
                     "actuator": match["actuator"], "source_mentions": match["mentions"],
                     "quantities": [{k: q[k] for k in ("property", "value", "unit", "format", "attribute")}
                                    for q in quantities],
                     "units_note": "RAD = radians, N-M = newton metre, RAD-PER-SEC = radians per second"}
        r.data = {"joint": match, "quantities": quantities}
        return r

    def actuators(self, configuration: dict) -> ToolResult:
        c = URIRef(configuration["uri"])
        r = ToolResult(tool="actuators", arguments={"configuration": configuration["id"]},
                       configuration=configuration["id"])
        rows = self.run_query(r, "actuators", config=c)
        self.file_evidence(r, configuration["uri"])
        r.summary = {
            "configuration": configuration["label"], "actuator_count": len(rows),
            "actuator_types_as_written": dict(Counter(x["type"] for x in rows)),
            "actuators": [f"{x['name']} -> {x['joint']}" for x in rows],
            "not_stated_in_model": "Motor model, gear ratio, rated torque and electrical data are not stated "
                                   "by the MJCF actuator elements; motor tables exist only in documentation "
                                   "(use search_documents).",
        }
        r.data = rows
        return r

    def sensors(self, configuration: dict) -> ToolResult:
        c = URIRef(configuration["uri"])
        r = ToolResult(tool="sensors", arguments={"configuration": configuration["id"]},
                       configuration=configuration["id"])
        rows = self.run_query(r, "sensors", config=c)
        self.file_evidence(r, configuration["uri"])
        links = self.run_query(r, "links", config=c)
        frame_links = sorted({x["name"] for x in links
                              if any(k in x["name"] for k in ("imu", "d435", "mid360", "camera", "lidar"))})
        r.summary = {
            "configuration": configuration["label"], "sensor_elements": len(rows),
            "sensors": [{"name": x["name"], "type": x["type"], "mounted_on": x["link"], "format": x["format"]}
                        for x in rows],
            "frames_named_like_sensors": frame_links,
            "caution": "Links such as d435_link or mid360_link are coordinate frames in the URDF; the URDF does "
                       "not declare them as sensors and states no sensor specification.",
        }
        r.data = rows
        return r

    def links_and_masses(self, configuration: dict) -> ToolResult:
        c = URIRef(configuration["uri"])
        r = ToolResult(tool="links_and_masses", arguments={"configuration": configuration["id"]},
                       configuration=configuration["id"])
        rows = self.run_query(r, "links", config=c)
        self.file_evidence(r, configuration["uri"])
        totals: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = Counter()
        massless: dict[str, list[str]] = defaultdict(list)
        for x in rows:
            counts[x["format"]] += 1
            if x["mass"] is not None:
                totals[x["format"]] += float(x["mass"])
            else:
                massless[x["format"]].append(x["name"])
        r.derivations = [("total mass per format = sum of inertial masses stated for links in that file; "
                         "it is a model value, not a measured robot mass")]
        r.summary = {"configuration": configuration["label"],
                     "links_per_format": dict(counts),
                     "sum_of_link_masses_kg": {k: round(v, 4) for k, v in totals.items()},
                     "links_without_mass": dict(massless)}
        r.data = rows
        return r

    def source_inconsistencies(self, configuration: dict) -> ToolResult:
        r = ToolResult(tool="source_inconsistencies", arguments={"configuration": configuration["id"]},
                       configuration=configuration["id"])
        path = self.s.generated_dir / f"{configuration['robot_id']}__{configuration['id']}.validation.json"
        if not path.exists():
            r.ok, r.error = False, "no validation report; run `jazari validate`"
            return r
        rep = json.loads(path.read_text(encoding="utf-8"))
        r.row_count = len(rep["inconsistencies"]) + len(rep["warnings"])
        r.summary = {"validation_ok": rep["ok"], "shacl_conforms": rep["shacl_conforms"],
                     "cross_format_inconsistencies": rep["inconsistencies"],
                     "stated_in_only_one_format_count": len(rep["warnings"]),
                     "stated_in_only_one_format_examples": rep["warnings"][:5]}
        r.data = rep
        r.evidence.append(Evidence(label=f"Validation report {path.name}", evidence_type="validation",
                                   source=f"knowledge-graphs/generated/{path.name}",
                                   detail="SHACL + structural + URDF/MJCF consistency checks"))
        self.file_evidence(r, configuration["uri"])
        return r

    def ontology_lookup(self, term: str) -> ToolResult:
        r = ToolResult(tool="ontology_lookup", arguments={"term": term})
        hits = [self.catalog.terms[term]] if term in self.catalog.terms else self.catalog.search(term)
        if not hits:
            r.ok, r.error = False, f"no ontology term matches {term!r}"
            return r
        t = hits[0]
        uri = expand(t.id)
        details: dict[str, Any] = {"id": t.id, "kind": t.kind, "label": t.label, "origin": t.origin,
                                   "definition": t.definition, "definition_source": t.definition_source}
        if t.kind == "class":
            supers = self.run_query(r, "class_superclasses", cls=uri)
            props = self.run_query(r, "class_properties", cls=uri)
            inst = self.run_query(r, "class_instances", cls=uri)
            details.update({
                "direct_superclasses": t.parents,
                "all_superclasses_inferred": sorted(curie(x["super"]) for x in supers),
                "direct_subclasses": self.catalog.children(t.id),
                "properties": [{"property": curie(p["property"]), "class_is": p["role"],
                                "other_end": curie(p["other"]) if p["other"] else None,
                                "ieee_1872_axiom": p["axiom"]} for p in props],
                "mappings": self.catalog.mappings(t.id),
                "knowledge_graph_instances": len(inst),
                "instance_examples": [f"{x['name']} ({x['directClass']})" for x in inst[:6]],
            })
            r.derivations.append("superclasses and instances inferred through rdfs:subClassOf* (RDFS entailment at query time)")
        else:
            prop = self.catalog.g
            details.update({
                "parent_properties": t.parents,
                "domain": [curie(str(x)) for x in prop.objects(uri, URIRef("http://www.w3.org/2000/01/rdf-schema#domain"))],
                "range": [curie(str(x)) for x in prop.objects(uri, URIRef("http://www.w3.org/2000/01/rdf-schema#range"))],
            })
        details["other_matches"] = [f"{h.id} ({h.kind})" for h in hits[1:6]]
        details["copyright_note"] = ("IEEE 1872-2015 natural-language definitions are IEEE copyright and are not "
                                     "reproduced; answers are based on the OWL axioms.")
        r.summary = details
        r.data = details
        r.evidence.append(Evidence(
            label=f"{t.id} in {t.origin}", evidence_type="ontology", url=t.uri if t.uri.startswith("http") else None,
            source="ontology/jazari/jazari.ttl" if t.id.startswith("jz:")
            else f"IEEE1872-owl@{_short(self.m.source('ieee1872_owl').revision)}",
            detail=t.definition_source or "axioms only"))
        return r

    def search_documents(self, query: str) -> ToolResult:
        r = ToolResult(tool="search_documents", arguments={"query": query})
        hits = self.docs.search(query)
        r.row_count = len(hits)
        r.summary = {"hits": [{"file": h.path, "lines": f"{h.start_line}-{h.end_line}", "text": h.text[:1500]}
                              for _, h in hits]}
        for score, h in hits:
            rev = self.m.source(h.source_id).revision
            r.evidence.append(Evidence(label=f"{Path(h.path).name} lines {h.start_line}-{h.end_line}",
                                       evidence_type="document", url=h.url,
                                       source=f"{h.source_id}@{_short(rev)} {h.path}",
                                       detail=f"BM25 score {score:.2f}"))
        r.data = [{"score": s, **h.__dict__} for s, h in hits]
        return r

    # ------------------------------------------------------------------ dispatch
    def run(self, name: str, arguments: dict[str, Any], default_configuration: str | None) -> ToolResult:
        spec = self.specs.get(name)
        if spec is None:
            return ToolResult(tool=name, arguments=arguments, ok=False, error=f"unknown tool {name!r}")
        # LLMs sometimes fill optional arguments with placeholder strings; treat them as omitted
        placeholders = {"", "none", "null", "n/a", "current", "unknown"}
        args = {k: v for k, v in arguments.items() if k in spec.parameters and v is not None
                and not (isinstance(v, str) and v.strip().lower() in placeholders)}
        try:
            if spec.needs_configuration:
                # An explicitly named robot that is not in the graph is an error; only an
                # omitted configuration falls back to the conversation's current one.
                requested = args.get("configuration")
                cfg = self.resolve_configuration(requested if requested else default_configuration)
                configs = self.configurations()
                available = ", ".join(f"{c['id']} ({c['robot']})" for c in configs)
                if cfg is None and not requested:
                    if len(configs) != 1:
                        return ToolResult(tool=name, arguments=arguments, ok=False,
                                          error=f"no robot specified; ask the user which one. Available: {available}")
                    # with a single configuration in the graph there is nothing to disambiguate
                    cfg = configs[0]
                if cfg is None:
                    return ToolResult(tool=name, arguments=arguments, ok=False,
                                      error=f"robot/configuration {args.get('configuration')!r} is not in the "
                                            f"knowledge graph. Available: {available}")
                args["configuration"] = cfg
            missing = [p for p in spec.parameters if p not in args]
            if missing:
                return ToolResult(tool=name, arguments=arguments, ok=False,
                                  error=f"missing argument(s): {', '.join(missing)}")
            result = spec.fn(**args)
            if result.ok and spec.needs_configuration:
                cfg = next(c for _, c in self.m.configurations() if c.id == args["configuration"]["id"])
                result.summary["source_files"] = [
                    f"{f.path.rsplit('/', 1)[-1]} ({f.format}) at {f.source}@{self.m.source(f.source).revision}"
                    for f in cfg.files]
            return result
        except Exception as e:  # noqa: BLE001 - tool failures are reported, not raised
            return ToolResult(tool=name, arguments=arguments, ok=False, error=f"{type(e).__name__}: {e}")


def _chain_end(chain: list[str], joints: list[dict]) -> str:
    by_name = {j["name"]: j for j in joints}
    return by_name[chain[-1]]["child"] if chain else ""
