from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

EvidenceType = Literal["extracted", "derived", "inferred", "document", "ontology", "validation"]


class Evidence(BaseModel):
    id: str = ""
    label: str
    evidence_type: EvidenceType
    url: str | None = None
    source: str | None = None  # e.g. "unitree_ros@15ebe53 robots/g1_description/g1_29dof_rev_1_0.urdf"
    detail: str | None = None


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool: str
    arguments: dict[str, Any]
    ok: bool = True
    error: str | None = None
    query_name: str | None = None
    queries: list[str] = Field(default_factory=list)  # SPARQL text actually executed
    row_count: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)  # compact facts given to the LLM
    data: Any = None  # full structured result for the UI
    derivations: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    configuration: str | None = None


class TraceStep(BaseModel):
    tool: str
    arguments: dict[str, Any]
    ok: bool
    error: str | None = None
    query_name: str | None = None
    queries: list[str] = Field(default_factory=list)
    row_count: int
    derivations: list[str] = Field(default_factory=list)
    duration_ms: int


class ChatContext(BaseModel):
    configuration: str | None = None
    configuration_label: str | None = None
    source_revision: str | None = None
    ontology_terms: list[str] = Field(default_factory=list)


class Verification(BaseModel):
    numbers_checked: int = 0
    unsupported_numbers: list[str] = Field(default_factory=list)
    removed_citations: list[str] = Field(default_factory=list)  # citations with no matching evidence
    note: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    question: str
    answer: str
    planner: Literal["llm", "rules"]
    composer: Literal["llm", "template"]
    model: str | None = None
    context: ChatContext
    trace: list[TraceStep]
    evidence: list[Evidence]
    results: list[ToolResult]
    verification: Verification
    latency_ms: int
    warnings: list[str] = Field(default_factory=list)
