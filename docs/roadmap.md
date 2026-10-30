# JAZARI roadmap

Status as of 2026-10-30.

## M1: Working foundation — done

- [x] Repository, manifest-driven source pinning, reproducible `uv` + `npm` installation
- [x] Architecture overview, decision records, source/license inventory, ontology map
- [x] FastAPI backend, `/api/v1/health`, Ollama connectivity with configurable endpoint/model
- [x] Minimal frontend
- [ ] Docker images verified end to end (Compose file provided; Docker daemon was not running during M2, so it is untested)

## M2: First robot expert (Unitree G1) — done

- [x] URDF and MJCF parsers with source line numbers, hardened XML parsing
- [x] Pinned `g1_29dof_rev_1_0` ingestion into an ontology-grounded graph (5.8k triples)
- [x] SHACL + structural + cross-format validation (found 6 real upstream inconsistencies)
- [x] Named read-only SPARQL queries and a fixed tool catalog
- [x] Natural-language Q&A through the graph with evidence permalinks and number verification
- [x] Chat UI with evidence and trace; Robots, Ontologies and Compare pages on live data
- [x] 41-question benchmark with automated scoring ([results](evaluation.md))

## M3: Three-robot knowledge — done

- [x] Sandboxed Xacro expander (no eval, no env, no path escapes), verified against the
      generated Berkeley URDF; MJCF `<include>` and nested default classes for actuators
- [x] Berkeley Humanoid Lite: `lite` (baseline, 72 DoF including 40 hand joints) and
      `lite_biped` (RobStride actuators, CAN ids, torque/current limits, ankle linkage)
- [x] ALOHA 2: bimanual model with two kinematic trees, finger couplings (16 articulated vs
      14 independent DoF), cameras
- [x] Variant-aware robot resolution, multi-robot comparisons, no silent default robot
- [x] Comparison API/UI with derived body regions and "not applicable" vs "not stated"
- [x] Benchmark v0.2 (58 questions) with Berkeley, ALOHA and comparison items: qwen3-coder:30b after fixes: 0.931 tool selection, 0.845 answers (0.879 after review)
- [ ] Curated document facts (`jz:Curated`) for motor tables (G1 `motor_info.md`,
      RobStride spec tables) with explicit variant applicability: moved to M4

## M4: Semantic reasoning

- Ontology-aware traversal (subsystems: leg, arm, waist as `jz:Subsystem` with derivation
  rules), pose via POS, capability/task vocabulary (evaluate IEEE 1872.2 availability).
- Hybrid document retrieval (BM25 + local embeddings via Ollama) over licensed papers.
- Evidence graph visualisation in the UI.

## M5: 3D exploration

- Fetch STL meshes on demand and render a single robot with Three.js/React Three Fiber
  (URDF loader). Clicking a link highlights its graph entity, and back.

## M6: Robotics fine-tuning

- Run the benchmark on more models first, then grow the benchmark (held-out split).
- LoRA/QLoRA via Unsloth on a separate GPU box (6 GB VRAM is too small for 7B+ QLoRA with
  useful context). Training targets: tool selection, abstention, citation discipline.
  Not the graph contents.
- Promote a model only if it beats the baseline on the held-out set.

## M7: Public release

- w3id registration, LICENSE review by the owner, NOTICE completeness.
- Public deployment profile: API key or OAuth, rate limiting, restricted CORS, no Ollama
  exposure, read-only graph, request size limits. See [deployment](deployment/README.md).
