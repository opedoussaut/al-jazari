"""Turn parsed robot descriptions into an ontology-grounded RDF knowledge graph.

Merge policy for one configuration described by several files (URDF + MJCF):
- links and joints with the same native name are the same model element; each file
  contributes a jz:SourceMention (file, line, type as written);
- every quantity is a separate qudt:QuantityValue per file, so values from different
  formats are never silently combined;
- structural facts (normalised class, parent/child) come from the first file listed in
  the manifest; disagreements are recorded as conflicts for the validation report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rdflib import RDF, RDFS, XSD, Graph, Literal, URIRef

from ..fetch import sha256
from ..ingestion import PARSERS, ParsedDescription
from ..ingestion.model import Joint, Quantity
from ..manifest import Configuration, Manifest, Robot
from .namespaces import JZ, JZR, PREFIXES, QUDT, UNIT

# normalised class and DoF for each (format, source type)
_JOINT_CLASS = {
    ("urdf", "revolute"): (JZ.RevoluteJoint, 1),
    ("urdf", "continuous"): (JZ.ContinuousJoint, 1),
    ("urdf", "prismatic"): (JZ.PrismaticJoint, 1),
    ("urdf", "fixed"): (JZ.FixedJoint, 0),
    ("urdf", "floating"): (JZ.FloatingJoint, 6),
    ("urdf", "planar"): (JZ.PlanarJoint, 3),
    ("mjcf", "slide"): (JZ.PrismaticJoint, 1),
    ("mjcf", "ball"): (JZ.BallJoint, 3),
    ("mjcf", "free"): (JZ.FloatingJoint, 6),
}


def joint_class(fmt: str, joint: Joint) -> tuple[URIRef, int]:
    if fmt == "mjcf" and joint.source_type == "hinge":
        return (JZ.RevoluteJoint, 1) if joint.lower is not None else (JZ.ContinuousJoint, 1)
    try:
        return _JOINT_CLASS[(fmt, joint.source_type)]
    except KeyError:
        raise ValueError(f"unsupported {fmt} joint type {joint.source_type!r} ({joint.name})")


@dataclass
class BuildReport:
    configuration: str
    files: list[str] = field(default_factory=list)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def new_graph() -> Graph:
    g = Graph()
    for k, v in PREFIXES.items():
        g.bind(k, v)
    return g


class ConfigurationBuilder:
    def __init__(self, manifest: Manifest, robot: Robot, config: Configuration, sources_dir: Path):
        self.m, self.robot, self.config, self.sources_dir = manifest, robot, config, sources_dir
        self.g = new_graph()
        self.report = BuildReport(configuration=config.id)
        self.model_uri = JZR[robot.id]
        self.config_uri = JZR[f"{robot.id}/{config.id}"]
        self._structural_owner: dict[URIRef, str] = {}

    # ------------------------------------------------------------ uris
    def element(self, kind: str, name: str) -> URIRef:
        return URIRef(f"{self.config_uri}/{kind}/{name}")

    def file_uri(self, source_id: str, path: str) -> URIRef:
        return JZR[f"source/{source_id}/{path}"]

    # ------------------------------------------------------------ build
    def build(self) -> tuple[Graph, BuildReport]:
        g, r, c = self.g, self.robot, self.config
        g.add((self.model_uri, RDF.type, JZ.RobotModel))
        g.add((self.model_uri, RDFS.label, Literal(r.name)))
        g.add((self.model_uri, JZ.manufacturer, Literal(r.manufacturer)))
        g.add((self.model_uri, JZ.category, Literal(r.category)))
        if r.homepage:
            g.add((self.model_uri, RDFS.seeAlso, URIRef(r.homepage)))
        g.add((self.model_uri, JZ.hasConfiguration, self.config_uri))

        g.add((self.config_uri, RDF.type, JZ.RobotConfiguration))
        g.add((self.config_uri, RDFS.label, Literal(c.label)))
        g.add((self.config_uri, JZ.configurationOf, self.model_uri))
        g.add((self.config_uri, JZ.nativeName, Literal(c.native_name)))
        g.add((self.config_uri, JZ.isBaseline, Literal(c.baseline)))
        g.add((self.config_uri, JZ.selectionRationale, Literal(c.selection_rationale.strip())))
        if c.mode_machine is not None:
            g.add((self.config_uri, JZ.modeMachine, Literal(c.mode_machine)))

        for doc in c.documents:
            doc_uri = self._file_node(doc.source, doc.path, JZ.TechnicalDocument, None)
            g.add((self.config_uri, RDFS.seeAlso, doc_uri))

        for sf in c.files:
            path = self.sources_dir / sf.source / sf.path
            desc = PARSERS[sf.format](path)
            file_uri = self._file_node(sf.source, sf.path, JZ.DescriptionFile, sf.format)
            self.g.add((self.config_uri, JZ.describedIn, file_uri))
            self.report.files.append(f"{sf.source}:{sf.path}")
            self.report.warnings += [f"{sf.path}: {w}" for w in desc.warnings]
            self._add_description(desc, file_uri, sf.format)

        self._add_root_link()
        return g, self.report

    def _file_node(self, source_id: str, path: str, cls: URIRef, fmt: str | None) -> URIRef:
        src = self.m.source(source_id)
        repo_uri = JZR[f"source/{source_id}"]
        self.g.add((repo_uri, RDF.type, JZ.SourceRepository))
        self.g.add((repo_uri, JZ.url, Literal(src.repo, datatype=XSD.anyURI)))
        self.g.add((repo_uri, JZ.license, Literal(src.license)))
        uri = self.file_uri(source_id, path)
        self.g.add((uri, RDF.type, cls))
        self.g.add((uri, RDFS.label, Literal(Path(path).name)))
        self.g.add((uri, JZ.sourcePath, Literal(path)))
        self.g.add((uri, JZ.revision, Literal(src.revision)))
        self.g.add((uri, JZ.sha256, Literal(sha256(self.sources_dir / source_id / path))))
        self.g.add((uri, JZ.fromRepository, repo_uri))
        self.g.add((uri, JZ.url, Literal(src.blob_url(path), datatype=XSD.anyURI)))
        if fmt:
            self.g.add((uri, JZ.sourceFormat, Literal(fmt)))
        return uri

    def _mention(self, el: URIRef, fmt: str, file_uri: URIRef, line: int, stype: str | None) -> None:
        m = URIRef(f"{el}/mention/{fmt}")
        self.g.add((el, JZ.hasMention, m))
        self.g.add((el, JZ.describedIn, file_uri))
        self.g.add((m, RDF.type, JZ.SourceMention))
        self.g.add((m, JZ.describedIn, file_uri))
        self.g.add((m, JZ.sourceLine, Literal(line)))
        self.g.add((m, JZ.sourceFormat, Literal(fmt)))
        if stype:
            self.g.add((m, JZ.sourceType, Literal(stype)))

    def _quantity(self, el: URIRef, prop: URIRef, q: Quantity, fmt: str, file_uri: URIRef) -> None:
        node = URIRef(f"{el}/{fmt}/{prop.split('#')[-1]}")
        self.g.add((el, prop, node))
        self.g.add((node, RDF.type, QUDT.QuantityValue))
        self.g.add((node, QUDT.numericValue, Literal(float(q.value), datatype=XSD.double)))
        self.g.add((node, QUDT.unit, UNIT[q.unit]))
        self.g.add((node, JZ.describedIn, file_uri))
        self.g.add((node, JZ.evidenceType, JZ.Extracted))
        if q.line:
            self.g.add((node, JZ.sourceLine, Literal(q.line)))
        if q.attribute:
            self.g.add((node, JZ.sourceAttribute, Literal(q.attribute)))

    def _element(self, kind: str, name: str, cls: URIRef) -> URIRef:
        el = self.element(kind, name)
        self.g.add((el, RDF.type, cls))
        self.g.add((el, JZ.nativeName, Literal(name)))
        self.g.add((el, RDFS.label, Literal(name)))
        self.g.add((self.config_uri, JZ.hasElement, el))
        return el

    def _add_description(self, d: ParsedDescription, file_uri: URIRef, fmt: str) -> None:
        g = self.g
        self.report.counts[fmt] = {
            "links": len(d.links), "joints": len(d.joints),
            "actuators": len(d.actuators), "sensors": len(d.sensors),
        }
        for link in d.links:
            el = self._element("link", link.name, JZ.Link)
            self._mention(el, fmt, file_uri, link.line, "body" if fmt == "mjcf" else "link")
            if link.mass:
                self._quantity(el, JZ.mass, link.mass, fmt, file_uri)

        for j in d.joints:
            cls, dof = joint_class(fmt, j)
            el = self.element("joint", j.name)
            owner = self._structural_owner.get(el)
            if owner is None:
                self._structural_owner[el] = fmt
                self._element("joint", j.name, cls)
                g.add((el, JZ.degreesOfFreedom, Literal(dof)))
                g.add((el, JZ.childLink, self.element("link", j.child)))
                if j.parent:
                    g.add((el, JZ.parentLink, self.element("link", j.parent)))
                if j.axis:
                    g.add((el, JZ.axis, Literal(" ".join(f"{v:g}" for v in j.axis))))
            else:
                existing_cls = g.value(el, RDF.type)
                if existing_cls != cls:
                    self.report.conflicts.append(
                        f"joint {j.name}: {owner} type {existing_cls.split('#')[-1]} vs "
                        f"{fmt} type {cls.split('#')[-1]} ({j.source_type}); kept {owner}")
                expected_parent = g.value(el, JZ.parentLink)
                if j.parent and expected_parent != self.element("link", j.parent):
                    self.report.conflicts.append(
                        f"joint {j.name}: parent differs ({owner}: "
                        f"{str(expected_parent).rsplit('/', 1)[-1]}, {fmt}: {j.parent}); kept {owner}")
            self._mention(el, fmt, file_uri, j.line, j.source_type)
            for prop, q in ((JZ.lowerLimit, j.lower), (JZ.upperLimit, j.upper),
                            (JZ.effortLimit, j.effort), (JZ.velocityLimit, j.velocity)):
                if q is not None:
                    self._quantity(el, prop, q, fmt, file_uri)

        for a in d.actuators:
            el = self._element("actuator", a.name, JZ.Actuator)
            self._mention(el, fmt, file_uri, a.line, a.source_type)
            if a.joint:
                g.add((el, JZ.drivesJoint, self.element("joint", a.joint)))
            if a.gear is not None:
                g.add((el, JZ.mjcfGear, Literal(a.gear, datatype=XSD.double)))

        for s in d.sensors:
            el = self._element("sensor", s.name, JZ.Sensor)
            self._mention(el, fmt, file_uri, s.line, s.source_type)
            if s.attached_to:
                g.add((el, JZ.mountedOn, self.element("link", s.attached_to)))

    def _add_root_link(self) -> None:
        links = set(self.g.objects(self.config_uri, JZ.hasElement)) & set(self.g.subjects(RDF.type, JZ.Link))
        children = {
            self.g.value(j, JZ.childLink)
            for j in self.g.subjects(JZ.childLink, None)
            if self.g.value(j, JZ.parentLink) is not None
        }
        roots = sorted(links - children)
        for root in roots:
            self.g.add((self.config_uri, JZ.rootLink, root))
        if len(roots) != 1:
            self.report.warnings.append(f"expected exactly one root link, found {len(roots)}")


def build_all(manifest: Manifest, sources_dir: Path, out_dir: Path) -> list[BuildReport]:
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for robot, config in manifest.configurations():
        g, report = ConfigurationBuilder(manifest, robot, config, sources_dir).build()
        g.serialize(out_dir / f"{robot.id}__{config.id}.ttl", format="turtle")
        reports.append(report)
    return reports
