"""Turn parsed robot descriptions into an ontology-grounded RDF knowledge graph.

Merge policy for one configuration described by several files (URDF/Xacro + MJCF):
- links, joints and actuators with the same native name are the same model element;
  each format contributes a jz:SourceMention (file, line, type as written). The file is
  the one where the element is actually written (an included file, a Xacro macro);
- every quantity is a separate qudt:QuantityValue per format, so values from different
  formats are never silently combined;
- structural facts (normalised class, parent/child) come from the first file listed in
  the manifest; disagreements are recorded as conflicts for the validation report;
- an MJCF body without a joint becomes a jz:FixedJoint of source type "weld" only when no
  earlier file already gives that link a parent joint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from rdflib import RDF, RDFS, XSD, Graph, Literal, URIRef

from ..fetch import sha256
from ..ingestion import ParsedDescription, parse_mjcf, parse_urdf, parse_xacro
from ..ingestion.model import Joint, Quantity
from ..manifest import Configuration, Manifest, Robot, SourceFile
from .namespaces import JZ, JZR, PREFIXES, QUDT, UNIT

# normalised class and DoF for each (format, source type); xacro is URDF after expansion
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
    ("mjcf", "weld"): (JZ.FixedJoint, 0),
}


def joint_class(fmt: str, joint: Joint) -> tuple[URIRef, int]:
    fmt = "urdf" if fmt == "xacro" else fmt
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


def parse_file(manifest: Manifest, sf: SourceFile, sources_dir: Path) -> ParsedDescription:
    root = sources_dir / sf.source
    path = root / sf.path
    if sf.format == "urdf":
        return parse_urdf(path)
    if sf.format == "mjcf":
        return parse_mjcf(path, sandbox=root)
    if sf.format == "xacro":
        pkgs = {k: root / v for k, v in manifest.source(sf.source).xacro_packages.items()}
        return parse_xacro(path, root, pkgs, sf.xacro_args)
    raise ValueError(f"unsupported format {sf.format!r}")


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
        return URIRef(f"{self.config_uri}/{kind}/{quote(name, safe='')}")

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
            desc = parse_file(self.m, sf, self.sources_dir)
            file_uri = self._file_node(sf.source, sf.path, JZ.DescriptionFile, sf.format)
            if sf.format == "xacro":
                args = " ".join(f"{k}={v}" for k, v in sorted(sf.xacro_args.items()))
                g.add((file_uri, JZ.xacroArguments, Literal(args)))
            self.g.add((self.config_uri, JZ.describedIn, file_uri))
            self.report.files.append(f"{sf.source}:{sf.path}")
            self.report.warnings += [f"{sf.path}: {w}" for w in desc.warnings]
            self._add_description(desc, sf, file_uri)

        self._add_root_links()
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

    def _file_for(self, sf: SourceFile, path: Path | None, default: URIRef) -> URIRef:
        """File node of the file where an element is written (included file, Xacro macro)."""
        if path is None:
            return default
        root = (self.sources_dir / sf.source).resolve()
        rel = Path(path).resolve().relative_to(root).as_posix()
        if rel == sf.path:
            return default
        return self._file_node(sf.source, rel, JZ.DescriptionFile, sf.format)

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

    def _quantity(self, el: URIRef, prop: URIRef, q: Quantity, fmt: str, sf: SourceFile,
                  default_file: URIRef) -> None:
        node = URIRef(f"{el}/{fmt}/{prop.split('#')[-1]}")
        self.g.add((el, prop, node))
        self.g.add((node, RDF.type, QUDT.QuantityValue))
        self.g.add((node, QUDT.numericValue, Literal(float(q.value), datatype=XSD.double)))
        self.g.add((node, QUDT.unit, UNIT[q.unit]))
        self.g.add((node, JZ.describedIn, self._file_for(sf, q.source_file, default_file)))
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

    def _add_description(self, d: ParsedDescription, sf: SourceFile, file_uri: URIRef) -> None:
        g, fmt = self.g, d.format
        self.report.counts[fmt] = {
            "links": len(d.links), "joints": len([j for j in d.joints if j.source_type != "weld"]),
            "implicit_welds": len([j for j in d.joints if j.source_type == "weld"]),
            "actuators": len(d.actuators), "sensors": len(d.sensors), "couplings": len(d.couplings),
        }
        for link in d.links:
            el = self._element("link", link.name, JZ.Link)
            self._mention(el, fmt, self._file_for(sf, link.source_file, file_uri), link.line,
                          "body" if fmt == "mjcf" else "link")
            if link.mass:
                self._quantity(el, JZ.mass, link.mass, fmt, sf, file_uri)

        child_has_parent = {g.value(j, JZ.childLink) for j in g.subjects(JZ.childLink, None)}
        for j in d.joints:
            cls, dof = joint_class(fmt, j)
            child = self.element("link", j.child)
            if j.source_type == "weld" and child in child_has_parent:
                continue  # an earlier file already connects this link with a named joint
            el = self.element("joint", j.name)
            owner = self._structural_owner.get(el)
            if owner is None:
                self._structural_owner[el] = fmt
                self._element("joint", j.name, cls)
                g.add((el, JZ.degreesOfFreedom, Literal(dof)))
                g.add((el, JZ.childLink, child))
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
            self._mention(el, fmt, self._file_for(sf, j.source_file, file_uri), j.line, j.source_type)
            for prop, q in ((JZ.lowerLimit, j.lower), (JZ.upperLimit, j.upper),
                            (JZ.effortLimit, j.effort), (JZ.velocityLimit, j.velocity)):
                if q is not None:
                    self._quantity(el, prop, q, fmt, sf, file_uri)

        for a in d.actuators:
            el = self.element("actuator", a.name)
            if (el, RDF.type, JZ.Actuator) not in g:
                self._element("actuator", a.name, JZ.Actuator)
            line, src = (a.call_line, a.call_file) if a.call_line else (a.line, a.source_file)
            self._mention(el, fmt, self._file_for(sf, src, file_uri), line, a.source_type)
            if a.joint:
                g.add((el, JZ.drivesJoint, self.element("joint", a.joint)))
            for prop, value in ((JZ.mjcfGear, a.gear), (JZ.mjcfKp, a.kp)):
                if value is not None:
                    g.add((el, prop, Literal(float(value), datatype=XSD.double)))
            for prop, value in ((JZ.actuatorModel, a.model), (JZ.hardwareAddress, a.hardware_address),
                                (JZ.hardwarePlugin, a.hardware_plugin), (JZ.transmissionType, a.transmission),
                                (JZ.transmissionParameters, a.transmission_parameters)):
                if value:
                    g.add((el, prop, Literal(value)))
            for ci in a.command_interfaces:
                g.add((el, JZ.commandInterface, Literal(ci)))
            if a.effort:
                self._quantity(el, JZ.effortLimit, a.effort, fmt, sf, file_uri)
            if a.current:
                self._quantity(el, JZ.currentLimit, a.current, fmt, sf, file_uri)

        for s in d.sensors:
            el = self._element("sensor", s.name, JZ.Sensor)
            self._mention(el, fmt, self._file_for(sf, s.source_file, file_uri), s.line, s.source_type)
            if s.attached_to:
                g.add((el, JZ.mountedOn, self.element("link", s.attached_to)))
            if s.detail:
                g.add((el, JZ.sensorDetail, Literal(s.detail)))

        for c in d.couplings:
            el = self._element("coupling", f"{c.joint1}=f({c.joint2})", JZ.JointCoupling)
            self._mention(el, fmt, self._file_for(sf, c.source_file, file_uri), c.line, "equality/joint")
            g.add((el, JZ.dependentJoint, self.element("joint", c.joint1)))
            g.add((el, JZ.independentJoint, self.element("joint", c.joint2)))
            g.add((el, JZ.polynomialCoefficients, Literal(c.polycoef)))

    def _add_root_links(self) -> None:
        g = self.g
        links = set(g.objects(self.config_uri, JZ.hasElement)) & set(g.subjects(RDF.type, JZ.Link))
        children = {g.value(j, JZ.childLink) for j in g.subjects(JZ.childLink, None)
                    if g.value(j, JZ.parentLink) is not None}
        roots = sorted(links - children)
        for root in roots:
            g.add((self.config_uri, JZ.rootLink, root))
        if not roots:
            self.report.warnings.append("no root link found")


def build_all(manifest: Manifest, sources_dir: Path, out_dir: Path) -> list[BuildReport]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.ttl"):
        old.unlink()  # configurations removed from the manifest must not linger
    reports = []
    for robot, config in manifest.configurations():
        g, report = ConfigurationBuilder(manifest, robot, config, sources_dir).build()
        g.serialize(out_dir / f"{robot.id}__{config.id}.ttl", format="turtle")
        reports.append(report)
    return reports
