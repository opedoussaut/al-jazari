"""The fixed catalog of read-only knowledge tools JAZARI can call.

Every tool executes named SPARQL queries from knowledge-graphs/queries/ (parameters are
passed as SPARQL bindings, never spliced into query text), performs any arithmetic in
Python, and returns structured facts plus evidence. The LLM chooses tools and phrases
answers; it never computes the numbers.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdflib import Literal, URIRef

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


# words too generic to identify a robot ("lite" is kept: it names Berkeley's variants)
_STOPWORDS = {"robot", "robots", "the", "a", "of", "and", "humanoid", "2", "model", "configuration",
              "selected", "description", "menagerie", "full", "body", "v2", "dof", "29dof", "rev", "1", "0"}

# native-name words -> body part, for the derived region grouping
_PARTS = (
    (("finger", "thumb", "gripper", "hand"), "hand"),
    (("hip", "knee", "ankle"), "leg"),
    (("shoulder", "elbow", "wrist", "forearm"), "arm"),
    (("neck", "head"), "neck"),
)


def body_region(name: str) -> str:
    """Body region from a joint's native name: a naming convention, not a source statement."""
    n = name.lower()
    side = next((s for s in ("left", "right") if n.startswith((f"{s}_", f"{s}/"))), "")
    for keys, part in _PARTS:
        if any(k in n for k in keys):
            return f"{side}_{part}" if side else part
    if "waist" in n:
        # on a manipulator arm (ALOHA "left/waist") the waist is the arm's base yaw joint
        return f"{side}_arm" if side else "waist"
    return "other"


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
                     "degrees of freedom (total, without hands, independent after couplings), floating base, "
                     "joints per body region (legs, arms, hands, waist, neck), actuated joints, and how the "
                     "source formats differ.",
                     {"configuration": "configuration id or robot name"}, self.joint_summary),
            ToolSpec("kinematic_structure",
                     "Kinematic tree of a configuration: root link(s) and how they attach to the world "
                     "(floating or welded), serial chains (legs, arms, waist) and parent/child connectivity.",
                     {"configuration": "configuration id or robot name"}, self.kinematic_structure),
            ToolSpec("joint_details",
                     "Limits (position, effort, velocity), axis, parent/child and source lines of one joint.",
                     {"configuration": "configuration id or robot name",
                      "joint": "joint name, e.g. left_knee_joint"}, self.joint_details),
            ToolSpec("actuators", "Actuators of a configuration: the joints they drive, actuator/motor models, "
                     "bus addresses, torque and current limits, gains, and transmissions such as linkages.",
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

    def resolve_configuration(self, text: str | None, robot_id: str | None = None) -> dict | None:
        if not text:
            return None
        t = text.strip().lower()
        configs = [c for c in self.configurations() if robot_id in (None, c["robot_id"])]
        for c in configs:
            if t in (c["id"], c["native_name"].lower(), c["uri"].lower()):
                return c
        def words(s: str) -> set[str]:
            return set(re.findall(r"[a-z0-9]+", s.lower()))

        tokens = words(t) - _STOPWORDS
        # a robot matches on its distinctive name words; a variant wins if its own
        # label/native name adds matches (e.g. "lite biped"), otherwise the baseline
        scored = []
        for c in configs:
            robot_hits = tokens & (words(f"{c['robot']} {c['robot_id']}") - _STOPWORDS)
            if not robot_hits:
                continue
            variant_hits = tokens & (words(f"{c['native_name']} {c['id']}") - words(c["robot"]) - _STOPWORDS)
            scored.append((len(variant_hits), c["baseline"], len(robot_hits), c))
        if not scored:
            return None
        return max(scored, key=lambda x: x[:3])[3]

    def _configuration_with_joint(self, joint: str) -> dict | None:
        """The configuration whose joint names contain this exact name, if exactly one does."""
        rows = self.store.select(
            "SELECT DISTINCT ?config WHERE { ?config jz:hasElement ?j . ?j jz:childLink ?c ; jz:nativeName ?n }",
            {"n": Literal(joint.strip())})
        matches = [c for c in self.configurations() if any(r["config"] == c["uri"] for r in rows)]
        return matches[0] if len(matches) == 1 else None

    def mentioned_configurations(self, text: str) -> list[dict]:
        """One configuration per robot named in the text, in order of first mention."""
        lowered = text.lower()
        found = []
        for robot_id in dict.fromkeys(c["robot_id"] for c in self.configurations()):
            configs = [c for c in self.configurations() if c["robot_id"] == robot_id]
            robot = next((c for c in configs if c["baseline"]), configs[0])
            names = set(re.findall(r"[a-z0-9]+", f"{robot['robot']} {robot_id}".lower())) - _STOPWORDS
            positions = [m.start() for w in names for m in re.finditer(rf"\b{re.escape(w)}\b", lowered)]
            if positions:
                # resolve within this robot only, so variant words pick the variant
                cfg = self.resolve_configuration(f"{robot['robot']} {text}", robot_id=robot_id)
                found.append((min(positions), cfg or robot))
        return [c for _, c in sorted(found, key=lambda x: x[0])]

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
        r.summary["note"] = "Only the robots and configurations listed are in the knowledge graph."
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
        urdf_like = next((f for f in ("urdf", "xacro") if f in by_format), None)
        if floating and urdf_like and f"{urdf_like}:" not in floating[0]["mentions"]:
            notes.append(f"The {urdf_like.upper()} defines no floating base joint; the MJCF declares a free "
                         f"joint on {floating[0]['child']}, which adds 6 unactuated DoF for the base.")
        if not floating:
            notes.append("No floating base joint is stated: the root is fixed to the world in these files.")

        r.derivations = [
            "total joints = number of distinct jz:Joint elements of the configuration (union of URDF and MJCF, merged by native name)",
            "articulated DoF = sum of jz:degreesOfFreedom over joints that are neither fixed nor floating",
            "actuated joints = joints targeted by an MJCF <motor>/<position>/... element (jz:drivesJoint)",
            "per-format counts = joints grouped by the jz:SourceMention of each file",
            ("movable joints by body region = grouping by native-name pattern (left/right + finger/gripper "
             "= hand, hip/knee/ankle = leg, shoulder/elbow/wrist/forearm = arm, waist, neck/head); a naming "
             "convention, not a source statement"),
            ("independent DoF = articulated DoF minus one per one-DoF joint coupling (MJCF <equality><joint>), "
             "because a coupled joint's position is a function of another joint's position"),
        ]
        regions: dict[str, list[str]] = defaultdict(list)
        for j in movable:
            regions[body_region(j["name"])].append(j["name"])
        couplings = self.run_query(r, "couplings", config=c)
        welds = [j["name"] for j in joints if "mjcf:weld" in j["mentions"]]
        if welds:
            notes.append("MJCF bodies without a joint are welded to their parent (or to the world); JAZARI "
                         f"records them as fixed joints of source type 'weld': {', '.join(welds)}.")
        articulated_dof = sum(int(j["dof"]) for j in movable)
        hand = [j["name"] for j in movable if body_region(j["name"]).endswith("hand")]
        r.summary = {
            "configuration": configuration["label"],
            "total_joints_in_graph": len(joints),
            "important_notes": notes,
            "joints_by_class": {x["class"]: int(x["count"]) for x in counts},
            "joints_by_source_format": {fmt: {"total": sum(cnt.values()), **dict(cnt)}
                                        for fmt, cnt in sorted(by_format.items())},
            "category": configuration["category"],
            "articulated_joints": len(movable),
            "articulated_dof": articulated_dof,
            "articulated_dof_without_hands": articulated_dof - len(hand),
            "joint_couplings": [f"{x['dependent']} = f({x['independent']}), polycoef {x['polycoef']}"
                                for x in couplings],
            "independent_dof": articulated_dof - len(couplings),
            "movable_joints_by_body_region": {k: {"count": len(v), "joints": v}
                                              for k, v in sorted(regions.items())},
            "floating_base": ({"joint": floating[0]["name"], "dof": int(floating[0]["dof"]),
                               "stated_in": floating[0]["mentions"]} if floating else None),
            "actuated_joints": len(actuated),
            "movable_joints_without_actuator": unactuated_movable,
            "fixed_joints": [j["name"] for j in joints if j["class"] == "FixedJoint"],
            "hand_or_finger_joints": {"count": len(hand), "joints": hand},
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
        all_links = {j["child"] for j in joints} | {j["parent"] for j in joints if j["parent"]}
        roots = sorted(all_links - child_links)
        world = {j["child"]: j for j in joints if not j["parent"]}  # floating or welded to world

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

        for root in roots:
            walk(root, [])
        unique = {tuple(ch) for ch in chains if ch}
        maximal = sorted([list(ch) for ch in unique
                          if not any(len(o) > len(ch) and o[:len(ch)] == ch for o in unique)],
                         key=lambda ch: ch[-1])
        r.derivations = [
            ("tree built from jz:parentLink/jz:childLink of every joint; roots = links that are never a "
            "child of a joint with a parent (a robot may have several, e.g. two arms bolted to a table)"),
            ("serial chains = movable-joint sequences from a root to each leaf link; chains that are a "
             "prefix of a longer chain are omitted; fixed joints are skipped"),
        ]
        floating = [j for j in joints if j["class"] == "FloatingJoint"]
        r.summary = {
            "configuration": configuration["label"], "category": configuration["category"],
            "root_links": [{"link": rt, "attached_to_world_by": (f"{world[rt]['name']} ({world[rt]['class']})"
                                                                 if rt in world else "nothing stated")}
                           for rt in roots],
            "separate_kinematic_trees": len(roots),
            "floating_base": (f"{floating[0]['name']} (6 DoF, stated in {floating[0]['mentions']})"
                              if floating else None),
            "serial_chains": [{"end_link_of_chain": _chain_end(ch, joints), "movable_joints": ch,
                               "length": len(ch)} for ch in maximal],
            "branching": {link: [j["name"] for j in ks] for link, ks in children.items() if len(ks) > 1},
        }
        r.data = {"root": roots[0] if roots else None, "roots": roots, "trees": [tree(rt) for rt in roots],
                  "tree": tree(roots[0]) if roots else None, "chains": maximal}
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
        by_name: dict[str, dict] = {}
        for x in rows:
            a = by_name.setdefault(x["name"], {"name": x["name"], "drives_joint": x["joint"], "stated_in": {}})
            for k in ("model", "address", "plugin", "transmission", "transmissionParams", "gear", "kp"):
                if x[k] is not None:
                    a[k] = x[k]
            fmt = a["stated_in"].setdefault(x["format"], {"element": x["type"], "line": x["line"]})
            if x["effort"] is not None:
                fmt["effort_limit"] = f"{x['effort']:g} {x['effortUnit']}"
            if x["current"] is not None:
                fmt["current_limit_A"] = x["current"]
        acts = list(by_name.values())
        stated = sorted({k for a in acts for k in a if k not in ("name", "drives_joint", "stated_in")})
        missing = [label for key, label in (("model", "actuator/motor model"), ("gear", "gear ratio"),
                                            ("transmission", "transmission type"))
                   if not any(key in a for a in acts)]
        r.summary = {
            "configuration": configuration["label"], "actuator_count": len(acts),
            "actuator_elements_by_format": {f: dict(Counter(x["type"] for x in rows if x["format"] == f))
                                            for f in sorted({x["format"] for x in rows})},
            "actuator_models": dict(Counter(a["model"] for a in acts if a.get("model"))),
            "hardware_facts_only_in": sorted({x["format"] for x in rows if x["type"].startswith("ros2_control")}),
            "actuators": acts[:40],
            "facts_stated_by_sources": stated,
            "not_stated_in_any_source_file": missing,
            "note": ("Documentation may list more (use search_documents); values there are document "
                     "evidence, not part of the robot description files."),
        }
        if len(acts) > 40:
            r.summary["actuators_truncated"] = f"first 40 of {len(acts)} shown"
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
            "by_type": dict(Counter(x["type"] for x in rows)),
            "sensors": [{"name": x["name"], "type": x["type"],
                         "mounted_on": x["link"] or ("world frame" if x["type"] == "camera" else "not stated"),
                         "format": x["format"], **({"detail": x["detail"]} if x["detail"] else {})}
                        for x in rows],
            "frames_named_like_sensors": frame_links,
            "caution": ("Links named like sensors (e.g. d435_link, imu frames) are coordinate frames; they are "
                        "not sensor declarations. Simulation cameras fixed in the world frame may be viewpoints "
                        "rather than physical cameras; check the robot's documentation."),
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
                if cfg is None and not requested and name == "joint_details" and args.get("joint"):
                    cfg = self._configuration_with_joint(args["joint"])
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
