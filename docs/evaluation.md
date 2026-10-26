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

## Results — M3, benchmark v0.2 (58 items), 2026-10-26, RTX A1000 6 GB, Ollama 0.40.9

| Mode | Tool selection | Answer (automated) | Answer (after review) | Median latency | p90 latency |
|---|---|---|---|---|---|
| Rules + template (no LLM) | 0.810 | 0.534 | — | < 0.5 s | < 1 s |
| `qwen3-coder:30b` | **0.879** | **0.845** | **0.828** | 16.7 s | 39.6 s |

"After review" reflects one false pass that review found: g1-09. The model answered that
the G1 has *no* floating base, which is wrong (the MJCF declares one). It passed
automatically only because "MJCF" appeared in its answer. The item now also requires
`floating_base_joint` and forbids the false claim (v0.2.1).

One item (bhl-05) took 7.7 hours because the host was suspended overnight during the run.
It is excluded from the latency figures; the slowest other item took 246 s.

By category (LLM, automated):

| Category | n | Tool selection | Answer |
|---|---|---|---|
| Architecture | 19 | 0.84 | 0.95 |
| Properties | 14 | 0.86 | 0.86 |
| Ontology | 10 | 1.00 | 0.70 |
| Provenance | 6 | 1.00 | 1.00 |
| Abstention | 6 | 0.83 | 0.83 |
| Comparison | 3 | 0.67 | 0.33 |

### Failures and what was done

| Item | Cause | Action |
|---|---|---|
| bhl-03 | The planner chose the `lite_biped` variant for "Berkeley Humanoid Lite without its hands" | **Fixed:** the engine overrides a variant the question does not name (ADR-015). Re-asked: correct (32) |
| g1-09 | Asserted a negative ("no floating base") that no tool result supported | **Fixed:** composer rule against unsupported absence claims; tool descriptions mention the floating base. Re-asked: correct |
| bhl-07 | The planner invented joint names instead of calling `actuators` | **Fixed:** the actuators tool description now covers transmissions and linkages. Re-asked: correct |
| ont-02, ont-05, ont-09 | Ontology search ranks `robotPart` above `robotActuatingPart`; answers omit named classes or the axiom number | Open (M4: ontology retrieval) |
| g1-06, g1-08, g1-19, abs-05 | Correct or partly correct answers through other tools than expected; g1-19 missed link names | Open |
| cmp-01, cmp-03 | Comparisons: the arm joint count (7) not stated explicitly; the gripper/hand comparison used the wrong tools | Open: a dedicated comparison tool is planned |

A full re-run after these fixes is pending, so the table above shows the measured run
**before** the fixes.

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
