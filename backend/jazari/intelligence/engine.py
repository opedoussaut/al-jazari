"""JAZARI orchestration: plan -> run read-only tools -> compose -> verify.

Deliberately a single, observable pipeline rather than an agent framework: every step
is recorded in the response trace.
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache

from ..config import Settings, get_settings
from ..kg import GraphStore
from ..manifest import load_manifest
from ..ontology_catalog import OntologyCatalog
from .composer import compose_llm, compose_template, sanitize_citations, verify_numbers
from .documents import DocumentIndex
from .ollama import LLMUnavailable, OllamaClient
from .planner import llm_plan, rule_plan
from .schemas import ChatContext, ChatResponse, TraceStep
from .tools import Toolbox

MAX_SESSIONS = 200


@dataclass
class Session:
    configuration: str | None = None
    history: list[tuple[str, str]] = field(default_factory=list)


class Engine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.manifest = load_manifest(settings.manifest_path)
        self.store = GraphStore.load(settings.ontology_dir, settings.sources_dir, settings.generated_dir)
        self.catalog = OntologyCatalog(self.store.graph)
        self.docs = DocumentIndex.from_manifest(self.manifest, settings.sources_dir)
        self.toolbox = Toolbox(settings, self.store, self.manifest, self.catalog, self.docs)
        self.llm = OllamaClient(settings.ollama_url, settings.model, settings.llm_timeout_s)
        self.sessions: OrderedDict[str, Session] = OrderedDict()

    def session(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            self.sessions[session_id] = Session()
            while len(self.sessions) > MAX_SESSIONS:
                self.sessions.popitem(last=False)
        self.sessions.move_to_end(session_id)
        return self.sessions[session_id]

    def ask(self, question: str, session_id: str | None = None, configuration: str | None = None,
            use_llm: bool = True) -> ChatResponse:
        t0 = time.perf_counter()
        session_id = session_id or uuid.uuid4().hex
        sess = self.session(session_id)
        if configuration:
            cfg = self.toolbox.resolve_configuration(configuration)
            sess.configuration = cfg["id"] if cfg else sess.configuration
        warnings: list[str] = []

        planner = "rules"
        calls = None
        if use_llm:
            try:
                calls = llm_plan(self.llm, self.toolbox, question, sess.configuration, sess.history)
                planner = "llm"
            except LLMUnavailable as e:
                if not self.settings.allow_llm_fallback:
                    raise
                warnings.append(f"LLM planner unavailable, used rule planner: {e}")
        if calls is None:
            calls = rule_plan(self.toolbox, question)

        results, trace = [], []
        for call in calls:
            ts = time.perf_counter()
            res = self.toolbox.run(call.name, call.arguments, sess.configuration)
            trace.append(TraceStep(tool=res.tool, arguments={k: v if not isinstance(v, dict) else v.get("id")
                                                             for k, v in res.arguments.items()},
                                   ok=res.ok, error=res.error, query_name=res.query_name, queries=res.queries,
                                   row_count=res.row_count, derivations=res.derivations,
                                   duration_ms=int((time.perf_counter() - ts) * 1000)))
            results.append(res)
            if res.ok and res.configuration:
                sess.configuration = res.configuration

        # number evidence globally, de-duplicating identical sources across tools
        evidence, seen = [], {}
        for r in results:
            for e in r.evidence:
                key = (e.label, e.url, e.evidence_type)
                if key not in seen:
                    e.id = f"E{len(evidence) + 1}"
                    seen[key] = e.id
                    evidence.append(e)
                else:
                    e.id = seen[key]

        composer = "template"
        answer = None
        if use_llm and planner == "llm":
            try:
                answer = compose_llm(self.llm, question, results, sess.history)
                composer = "llm"
            except LLMUnavailable as e:
                warnings.append(f"LLM composer unavailable, used template: {e}")
        if answer is None:
            answer = compose_template(question, results)

        answer, removed = sanitize_citations(answer, {e.id for e in evidence})
        verification = verify_numbers(answer, question, results)
        if removed:
            verification.removed_citations = removed
        sess.history.append((question, answer))
        sess.history = sess.history[-8:]

        ctx = ChatContext(configuration=sess.configuration)
        if sess.configuration:
            cfg = self.toolbox.resolve_configuration(sess.configuration)
            ctx.configuration_label = cfg["label"]
            src = next(f for _, c in self.manifest.configurations() if c.id == cfg["id"] for f in c.files)
            ctx.source_revision = f"{src.source}@{self.manifest.source(src.source).revision}"
        ctx.ontology_terms = [r.summary.get("id") for r in results if r.tool == "ontology_lookup" and r.ok]

        return ChatResponse(
            session_id=session_id, question=question, answer=answer, planner=planner, composer=composer,
            model=self.settings.model if composer == "llm" or planner == "llm" else None,
            context=ctx, trace=trace, evidence=evidence, results=results, verification=verification,
            latency_ms=int((time.perf_counter() - t0) * 1000), warnings=warnings,
        )


@lru_cache
def get_engine() -> Engine:
    return Engine(get_settings())
