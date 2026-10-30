# Evaluation

Benchmark: [`evaluation/benchmark.yaml`](../evaluation/benchmark.yaml), v0.2.1, 58
questions over the G1, Berkeley Humanoid Lite, ALOHA 2 and the IEEE 1872 ontologies. Every
expected value was checked by hand against the pinned sources. Run it with:

```bash
uv run jazari eval
```

Add `--no-llm` for the deterministic baseline. Result JSON files (with every answer) are
written to `evaluation/results/` and are not committed.

## Method

Each item is scored on two separate axes:

- **Tool selection:** at least one expected tool was called.
- **Answer:** all required facts are present and no forbidden fact is. For abstention
  items, the answer must say the knowledge is unavailable and must not contain the
  forbidden values.

Items marked `review: expert` also need human review. Their automated facts are necessary
but not sufficient. Unsupported numbers, removed citations and latency are recorded per
item.

## Results — M3 after fixes, benchmark v0.2.1 (58 items), 2026-10-30, RTX A1000 6 GB, Ollama 0.40.9

| Mode | Tool selection | Answer (automated) | Answer (after review) | Median latency | p90 latency |
|---|---|---|---|---|---|
| Rules + template (no LLM) | 0.810 | 0.534 | — | < 0.5 s | < 1 s |
| `qwen3-coder:30b`, after fixes | **0.931** | **0.845** | **0.879** | 17.6 s | 37.9 s |
| `qwen3-coder:30b`, before fixes (2026-10-26) | 0.879 | 0.845 | 0.828 | 16.7 s | 39.6 s |

The slowest item took 66 s. The run before the fixes had one item (bhl-05) that took 7.7
hours because the host was suspended; it is excluded from its latency figures.

By category (LLM after fixes, automated):

| Category | n | Tool selection | Answer |
|---|---|---|---|
| Architecture | 19 | 0.89 | 1.00 |
| Properties | 14 | 1.00 | 0.86 |
| Ontology | 10 | 1.00 | 0.70 |
| Provenance | 6 | 1.00 | 0.83 |
| Abstention | 6 | 0.83 | 0.83 |
| Comparison | 3 | 0.67 | 0.33 |

### What changed between the two runs

| Item | Before → after | Why |
|---|---|---|
| bhl-03 | fail → pass | Variant guard (ADR-015): answers 32 DoF for the full-body `lite` |
| g1-09 | false pass → pass | Correct now: floating base `floating_base_joint`, stated in the MJCF (`mjcf:free@L45`) |
| g1-19 | fail → pass | Planner now calls `links_and_masses` |
| abs-05 | fail → pass | Abstains correctly |
| bhl-07 | fail → fail (automated), **pass after review** | Now calls `actuators` and answers correctly ("left and right ankle pitch joints", four-bar linkage). The scorer looks for `ankle_pitch` and misses the spelled-out name |
| abs-02 | pass → fail (automated), **pass after review** | Correctly says the gear ratio cannot be determined, a phrasing the abstention detector does not know |
| g1-20 | pass → fail | Lists all 29 actuated joints but not their type (`motor`) and says the model is not stated. Run-to-run variation, not caused by the fixes |
| bhl-08 | pass → fail | Names `lite_biped.urdf.xacro` correctly, but also credits the MJCF with the RobStride data, and does not say `ros2_control` |

The scorer was not changed after this run, so the automated numbers of both runs stay
comparable. "After review" corrects only the two scoring misses above (bhl-07, abs-02).

### Still open

| Item | Cause | Plan |
|---|---|---|
| ont-02, ont-05, ont-09 | Ontology search ranks `robotPart` above `robotActuatingPart`; answers omit named classes or the axiom number | M4: ontology retrieval |
| g1-20, bhl-08 | Incomplete or over-attributed answers on actuator data | Composer guidance for actuator listings |
| cmp-01, cmp-03 | Comparisons: the arm joint count (7) not stated explicitly; the gripper/hand comparison used the wrong tools | A dedicated comparison tool |
| Scoring | Fact matching misses spelled-out names; the abstention detector misses some phrasings | Normalise names and widen abstention phrases in a new benchmark version, re-scoring both runs |

Also found and fixed during M3 testing, though outside the benchmark: concurrent API
requests corrupted rdflib's SPARQL parser for the whole process (see PR #2).

## M2 history (benchmark v0.1, 41 items, G1 only)

| Mode | Tool selection | Answer |
|---|---|---|
| Rules + template | 0.780 | 0.561 |
| `qwen3-coder:30b` | 0.927 | 0.854 |

The M2 and M3 numbers are not directly comparable: v0.2 adds harder multi-robot,
comparison and variant questions.

## Known limits

- The number verifier cannot catch a wrong small count (1 or 2), because those numbers
  appear everywhere in the results.
- The benchmark has been used during development, so these scores are optimistic for
  unseen questions. A held-out split is planned before any fine-tuning (M6).
- Other local models have not been benchmarked yet. Runtime memory and GPU use are not
  measured.
