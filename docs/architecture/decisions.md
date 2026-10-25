# Architecture decision records

Short ADRs in the order they were made. Status is "accepted" unless noted.

## ADR-001: Single Python package instead of top-level ingestion/intelligence folders

The brief suggested `ingestion/`, `intelligence/` and `backend/` as sibling folders. They
are subpackages of one importable package, `backend/jazari/`, instead: `ingestion`, `kg`,
`intelligence`, `api`. That gives one `pyproject.toml`, one virtualenv, no `sys.path`
manipulation, and a single CLI (`jazari fetch|build|validate|ask|eval|serve`).
Non-code assets keep their own top-level folders (`ontology/`, `knowledge-graphs/`,
`evaluation/`, `docs/`).

## ADR-002: Deterministic tool pipeline, no agent framework

The orchestration is plan → execute fixed tools → compose → verify. There are no
autonomous loops and no multi-agent framework. This keeps every step observable in
the response trace and keeps latency predictable (one planner call and one composer call).
Revisit if multi-hop questions show a measured need for iterative tool use.

## ADR-003: The LLM never computes engineering numbers

Counts, DoF, mass sums and chain lengths are computed in Python inside tools and passed to
the model as facts with `derivations`. A post-hoc verifier flags any number in the answer
that is absent from the tool results. Invented bracketed citations are stripped (found in
testing: `qwen3-coder:30b` invented an IEEE clause number even when told not to).

## ADR-004: rdflib in-process store first, Fuseki later

The M2 graph has about 5.8k triples. rdflib keeps installation to `uv sync` with no Java
service. The store interface is a single `select()` method, so moving to Jena Fuseki is
local to `kg/store.py`. Trigger for the switch: graph size, or the need for concurrent
writers, or for a persistent SPARQL endpoint.

## ADR-005: Parameterised named queries, read-only enforcement

Queries live in `knowledge-graphs/queries/*.rq` and receive parameters via `initBindings`.
The store compiles queries with rdflib's query parser, which rejects SPARQL Update. It also
accepts only `SelectQuery` algebra and refuses `SERVICE`. No API endpoint accepts free
SPARQL.

## ADR-006: Configurations are designs (CORAX), not robots (CORA)

URDF and MJCF files describe a design. Typing configuration elements as `cora:Robot`
parts would assert physical devices that may not exist. `jz:RobotConfiguration ⊑
corax:Design`, and elements ⊑ `corax:DesignObject`. Alignment to RPARTS part roles and to
SOSA uses SKOS mapping relations, not subclassing.

## ADR-007: One element per native name, one quantity per source file

A joint named `left_knee_joint` in both URDF and MJCF is one `jz:Joint` with two
`jz:SourceMention`s. Its effort limit from each file is a separate `qudt:QuantityValue`.
This answers "which file says what" exactly and makes cross-format inconsistencies
detectable. Structural facts (normalised class, parent/child) come from the first file in
the manifest (URDF); disagreements are recorded as build conflicts. None occurred for the
G1.

## ADR-008: Reference ontologies are fetched, not vendored

IEEE1872-owl declares CC-BY-4.0 in `dc:rights` but has no repository LICENSE file. The
OWL files are fetched at a pinned commit during setup and attributed in the UI and
docs. No IEEE standard text is reproduced. The OWL contains axioms and axiom numbers,
which JAZARI uses; natural-language definitions in the JAZARI ontology are written by the
project and labelled as editorial.

## ADR-009: Stable URIs under w3id.org (registration pending)

Ontology: `https://w3id.org/jazari/ontology#`. Data: `https://w3id.org/jazari/kg/`. A
w3id redirect has to be registered (pull request to `perma-id/w3id.org`) before public
release. Until then the URIs are stable identifiers but do not resolve.

## ADR-010: Default model qwen3-coder:30b

Measured on the development laptop (RTX A1000 6 GB, 32 GB RAM) with a two-part routing
question and a 120-word explanation:

| Model | Routing JSON | Explanation speed | Note |
|---|---|---|---|
| qwen3-coder:30b (MoE) | correct | ~22 tok/s | best answers, partly CPU-offloaded |
| qwen2.5-coder:7b | correct | ~25 tok/s | fits in VRAM, terse |
| nemotron-3-nano:4b | correct | ~48 tok/s | spends ~1.4k reasoning tokens per answer |

None of these is robotics-specialised. On the 41-question benchmark, qwen3-coder:30b scores 0.927 tool selection and 0.854 answer accuracy (rules-only baseline: 0.780 and 0.561). Details are in
[`docs/evaluation.md`](../evaluation.md). The model is configurable via `JAZARI_MODEL`.

## ADR-011: BM25 document retrieval before embeddings

Document retrieval starts with deterministic BM25 over paragraph chunks that keep line
ranges, so each hit is a permalink to exact lines. Embeddings are added when the corpus
grows beyond robot READMEs (planned M4).

## ADR-012: License: Apache-2.0

JAZARI's own code, ontology and documentation are Apache-2.0, chosen for its explicit
patent grant. Third-party sources keep their licenses and are listed in `NOTICE` and
[`docs/sources/robot-sources.md`](../sources/robot-sources.md). The project owner may
choose differently before the first public release.
