# JAZARI: your robotics AI expert

JAZARI is an open-source, locally deployable robotics subject-matter expert. Its answers
come from **explicit engineering knowledge** (IEEE 1872 robotics ontologies and a
knowledge graph built from pinned robot description files), not from what a language
model remembers. A local LLM (via [Ollama](https://ollama.com)) plans read-only queries
and explains the results. Every answer lists its evidence, down to the source line.

The project is named after Ismail al-Jazari (1136–1206), engineer and pioneer of
mechanical automata.

> **Status: milestone M3.** Three robots are ingested end to end: Unitree G1 (29-DoF rev 1.0),
> Berkeley Humanoid Lite (`lite` and `lite_biped`) and ALOHA 2 (MuJoCo Menagerie). They come
> from URDF, Xacro and MJCF sources. See the [roadmap](docs/roadmap.md).

## What it does today

- Answers questions like *"How many joints are defined in the selected Unitree G1
  configuration, and what are their types?"* from the graph. Answer: 39 joints (29
  revolute, 9 fixed, 1 floating base). The URDF defines 38 and the MJCF 30, and JAZARI
  explains why they differ.
- Cites evidence as permalinks to the exact upstream file revision and line. It tells
  extracted, derived and inferred facts apart, and flags numbers it can't verify.
- Compares robots of different kinds honestly. For example, ALOHA 2 has 16 articulated but
  14 independent DoF (coupled gripper fingers) and no legs ("not applicable", not 0).
  Berkeley Humanoid Lite has 72 DoF, 40 of them in its hands.
- Reads hardware actuator data from Xacro `ros2_control` blocks, such as RobStride models,
  CAN ids, and torque and current limits, through its own sandboxed Xacro expander.
- Says when it doesn't know (robots not in the graph, specs not in the sources), and asks
  which robot you mean when a question is ambiguous.
- Explores the IEEE 1872 ontology (CORA, CORAX, RPARTS, POS) and the JAZARI extension,
  with axiom numbers and knowledge-graph instances.
- Validates its own graph (SHACL, structural and URDF-vs-MJCF checks). This found six
  real effort-limit disagreements in the upstream G1 files.

## Quick start (Windows, macOS, Linux)

Prerequisites: Git, [uv](https://docs.astral.sh/uv/), Node.js 20+, and optionally Ollama
with a model pulled (default `qwen3-coder:30b`; any model works via `JAZARI_MODEL`).
Without Ollama, JAZARI still answers with a deterministic planner and templated answers.

```bash
git clone https://github.com/opedoussaut/al-jazari.git
```

```bash
cd al-jazari/backend
```

```bash
uv sync --extra dev
```

```bash
uv run jazari fetch
```

```bash
uv run jazari build
```

```bash
uv run jazari validate
```

```bash
uv run jazari serve
```

In a second terminal:

```bash
cd al-jazari/frontend
```

```bash
npm ci
```

```bash
npm run dev
```

Open http://localhost:5173. To ask from the command line:

```bash
uv run jazari ask "How many joints are defined in the selected Unitree G1 configuration, and what are their types?"
```

Configuration is via environment variables or `.env` (see [`.env.example`](.env.example)).
If the backend runs in Docker and Ollama on the Windows host, set
`JAZARI_OLLAMA_URL=http://host.docker.internal:11434`.

## Architecture

```
React UI ──► FastAPI /api/v1 ──► engine: plan (LLM, JSON-schema constrained)
                                        → fixed read-only tools (named SPARQL, Python arithmetic)
                                        → compose (LLM, cites [E#]) → verify numbers/citations
                     tools ──► rdflib store: IEEE 1872 OWL + JAZARI ontology + robot KGs + BM25 docs
ingestion: sources.yaml (pinned SHAs) → fetch → URDF / sandboxed Xacro / MJCF parsers → KG builder → SHACL validation
```

Details: [architecture overview](docs/architecture/overview.md) ·
[decisions](docs/architecture/decisions.md) ·
[ontologies](docs/ontology/reference-ontologies.md) ·
[sources and licenses](docs/sources/robot-sources.md) ·
[evaluation](docs/evaluation.md) · [deployment](docs/deployment/README.md)

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | service, graph and LLM status |
| GET | `/api/v1/robots` | robot catalog |
| GET | `/api/v1/robots/{id}` | configuration identity, sources, joint summary |
| GET | `/api/v1/robots/{id}/components` | joints, limits, kinematic tree, links, actuators, sensors |
| GET | `/api/v1/robots/{id}/validation` | validation report |
| GET | `/api/v1/ontology/classes?q=` | class catalog / search |
| GET | `/api/v1/ontology/classes/{id}` | term details (e.g. `cora:Robot`) |
| POST | `/api/v1/chat` | `{question, session_id?}` → grounded answer, evidence, trace |
| POST | `/api/v1/compare` | `{configurations: [...]}` → structured comparison |

Interactive docs at http://127.0.0.1:8000/docs. No endpoint accepts SPARQL, file paths or
commands.

## Tests and evaluation

```bash
uv run pytest
```

```bash
npm test
```

```bash
uv run jazari eval
```

The benchmark (`evaluation/benchmark.yaml`, 58 hand-verified questions) scores tool
selection, required facts and abstention separately.

## Repository layout

```
backend/jazari/        Python package: ingestion, kg, intelligence, api, cli
ontology/              JAZARI ontology, alignments, SHACL shapes
knowledge-graphs/      source manifest + lock, named SPARQL queries, generated graphs (git-ignored)
evaluation/            benchmark and results
frontend/              React + TypeScript + Vite + Tailwind web app
docs/                  architecture, decisions, sources, ontology, roadmap, deployment
```

## License

Apache-2.0 for JAZARI's own code, ontology and docs. Third-party sources keep their
licenses and are fetched, not redistributed; see [NOTICE](NOTICE). JAZARI is an
independent project, not affiliated with Unitree, Berkeley, Trossen Robotics, Google DeepMind, IEEE, NVIDIA or Dassault Systèmes.
