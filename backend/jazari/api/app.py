"""JAZARI HTTP API (versioned under /api/v1).

Read-only by construction: no endpoint accepts SPARQL, file paths or commands. Chat
requests can only trigger the fixed tool catalog in jazari.intelligence.tools.
"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from rdflib import URIRef

from .. import __version__
from ..config import get_settings
from ..intelligence.engine import get_engine
from ..intelligence.schemas import ChatResponse, ToolResult

settings = get_settings()
app = FastAPI(title="JAZARI API", version=__version__,
              description="Open-source robotics AI expert grounded in ontologies and knowledge graphs.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)
    configuration: str | None = Field(default=None, max_length=100)
    use_llm: bool = True


class CompareRequest(BaseModel):
    configurations: list[str] = Field(min_length=1, max_length=5)


def _config_or_404(config_id: str) -> dict:
    cfg = get_engine().toolbox.resolve_configuration(config_id)
    if cfg is None:
        raise HTTPException(404, f"robot or configuration {config_id!r} is not in the knowledge graph")
    return cfg


@app.get("/api/v1/health")
def health() -> dict:
    e = get_engine()
    return {
        "status": "ok", "version": __version__,
        "graph": {"triples": len(e.store), "reference_ontologies": [p.name for p in e.store.files.reference],
                  "jazari_ontology": [p.name for p in e.store.files.jazari],
                  "knowledge_graphs": [p.name for p in e.store.files.knowledge_graphs]},
        "documents_indexed": len(e.docs.chunks),
        "llm": e.llm.status(),
    }


@app.get("/api/v1/robots")
def robots() -> list[dict]:
    e = get_engine()
    out = []
    for robot in e.manifest.robots:
        out.append({"id": robot.id, "name": robot.name, "manufacturer": robot.manufacturer,
                    "category": robot.category, "homepage": robot.homepage,
                    "configurations": [{"id": c.id, "label": c.label, "native_name": c.native_name,
                                        "baseline": c.baseline} for c in robot.configurations]})
    return out


@app.get("/api/v1/robots/{robot_id}")
def robot(robot_id: str) -> dict:
    e = get_engine()
    cfg = _config_or_404(robot_id)
    info = e.toolbox.run("configuration_info", {"configuration": cfg["id"]}, None)
    summary = e.toolbox.run("joint_summary", {"configuration": cfg["id"]}, None)
    return {"configuration": cfg, "info": info.summary, "files": info.data["files"],
            "evidence": info.evidence, "joint_summary": summary.summary}


@app.get("/api/v1/robots/{robot_id}/components")
def components(robot_id: str) -> dict:
    e = get_engine()
    cfg = _config_or_404(robot_id)
    tb = e.toolbox
    joints = tb.run("joint_summary", {"configuration": cfg["id"]}, None)
    quantities = tb.run_query(ToolResult(tool="components", arguments={}), "joint_quantities",
                              config=URIRef(cfg["uri"]))
    return {
        "configuration": cfg,
        "joints": joints.data["joints"], "joint_quantities": quantities,
        "kinematics": tb.run("kinematic_structure", {"configuration": cfg["id"]}, None).data,
        "links": tb.run("links_and_masses", {"configuration": cfg["id"]}, None).data,
        "actuators": tb.run("actuators", {"configuration": cfg["id"]}, None).data,
        "sensors": tb.run("sensors", {"configuration": cfg["id"]}, None).data,
    }


@app.get("/api/v1/robots/{robot_id}/validation")
def validation(robot_id: str) -> dict:
    cfg = _config_or_404(robot_id)
    path = settings.generated_dir / f"{cfg['robot_id']}__{cfg['id']}.validation.json"
    if not path.exists():
        raise HTTPException(404, "no validation report; run `jazari validate`")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/v1/ontology/classes")
def ontology_classes(q: str | None = Query(default=None, max_length=100)) -> list[dict]:
    cat = get_engine().catalog
    terms = cat.search(q, limit=50) if q else cat.classes()
    return [{"id": t.id, "label": t.label, "kind": t.kind, "origin": t.origin, "parents": t.parents,
             "has_definition": t.definition is not None} for t in terms]


@app.get("/api/v1/ontology/classes/{term_id}")
def ontology_class(term_id: str) -> dict:
    e = get_engine()
    if term_id not in e.catalog.terms:
        raise HTTPException(404, f"unknown ontology term {term_id!r}")
    r = e.toolbox.run("ontology_lookup", {"term": term_id}, None)
    return {**r.summary, "evidence": r.evidence, "queries": r.queries}


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    return await run_in_threadpool(get_engine().ask, req.question, req.session_id, req.configuration,
                                   req.use_llm)


# Dimensions compared; each value is taken from a tool summary or reported as unavailable.
_COMPARE = [
    ("category", None, None),
    ("total joints", "joint_summary", "total_joints_in_graph"),
    ("joints by class", "joint_summary", "joints_by_class"),
    ("articulated DoF", "joint_summary", "articulated_dof"),
    ("actuated joints", "joint_summary", "actuated_joints"),
    ("floating base", "joint_summary", "floating_base"),
    ("actuators", "actuators", "actuator_count"),
    ("sensor elements", "sensors", "sensor_elements"),
    ("serial chains", "kinematic_structure", "serial_chains"),
    ("sum of link masses (kg)", "links_and_masses", "sum_of_link_masses_kg"),
    ("source files", "configuration_info", "files"),
]


@app.post("/api/v1/compare")
def compare(req: CompareRequest) -> dict:
    tb = get_engine().toolbox
    columns = []
    for requested in req.configurations:
        cfg = tb.resolve_configuration(requested)
        if cfg is None:
            columns.append({"requested": requested, "available": False,
                            "reason": "not ingested in the knowledge graph yet"})
            continue
        cache: dict[str, dict] = {}
        values = {}
        for label, tool, key in _COMPARE:
            if tool is None:
                values[label] = cfg["category"]
                continue
            if tool not in cache:
                cache[tool] = tb.run(tool, {"configuration": cfg["id"]}, None).summary
            values[label] = cache[tool].get(key, None)
        columns.append({"requested": requested, "available": True, "configuration": cfg, "values": values})
    return {"dimensions": [d[0] for d in _COMPARE], "columns": columns,
            "note": "Values are read from the knowledge graph; null means not available in the sources."}
