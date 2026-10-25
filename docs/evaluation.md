# Evaluation

Benchmark: [`evaluation/benchmark.yaml`](../evaluation/benchmark.yaml), v0.1, 41 questions.
Every expected value was checked by hand against the pinned sources. Run it with:

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
  forbidden values (e.g. G1 numbers for ALOHA 2).

Items marked `review: expert` (6 of 41) also need human review. Their automated facts are
necessary but not sufficient. Retrieval quality is visible per item in the trace.
Unsupported numbers and removed citations are counted separately. Response latency is
recorded per item.

## Results — 2026-10-25, RTX A1000 6 GB laptop, Ollama 0.40.9

| Mode | Tool selection | Answer | Answers with unsupported numbers | Answers with removed citations | Median latency |
|---|---|---|---|---|---|
| Rules + template (no LLM) | 0.780 | 0.561 | 0 | 6 | 0.03 s |
| `qwen3-coder:30b`, run 1 | 0.927 | 0.854 | 3 | 5 | 13.3 s |
| `qwen3-coder:30b`, run 2 (after fixes below) | **0.927** | **0.854** | 1 | 6 | 13.0 s |

Run 2 by category:

| Category | n | Tool selection | Answer |
|---|---|---|---|
| Ontology | 10 | 1.00 | 0.70 |
| Architecture | 11 | 0.91 | 0.91 |
| Properties | 10 | 1.00 | 0.90 |
| Provenance | 5 | 1.00 | 1.00 |
| Abstention | 5 | 0.60 | 0.80 |

### Changes between run 1 and run 2

Run 1 failures led to three fixes:

1. Per-region joint counts were added to `joint_summary` (derived from native-name patterns,
   with the method recorded). In run 1 the model answered "1 waist joint" (truth: 3)
   because no tool gave that number.
2. The number verifier matches the corpus loosely (`@L161` now supports 161). Run 1 had
   false "unsupported" flags.
3. Placeholder arguments such as `"None"` are treated as omitted.

Gains and losses balanced out: g1-07 and prov-05 were fixed, g1-08 regressed (the model
counted the waist chain as part of the arm).

After run 2, one more fix: with a single configuration in the graph and no robot named
in a fresh session, tools use that configuration. With several, they ask which one.
g1-20 and g1-07 were re-scored individually and pass. A full rerun is pending, so the
table above does **not** include this fix.

### Remaining failures (run 2), by cause

| Item | Cause |
|---|---|
| ont-02 | Ontology search ranks `cora:robotPart` above `rparts:robotActuatingPart` for "actuating parts" |
| ont-05 | The answer explains the concepts but does not name `cora:RoboticSystem` |
| ont-09 | The axiom number 8.1.3 was in the facts, but the model said there was none: composer error |
| g1-08 | Arm chain counted with the waist (10 instead of 7), even though region counts were available |
| g1-09, abs-02 | Correct answers, but via different tools than expected (scoring is strict) |
| g1-20 | Fixed after run 2 (see above) |
| abs-05 | **Misattribution:** said the MJCF states a knee gear ratio of 22.5. That value is a README table entry, and the MJCF states no gear |

Known blind spot: the number verifier cannot catch a wrong small count (1 or 2), because
those numbers appear everywhere in the results.

## Not yet measured

- Other local models (qwen2.5-coder:7b, nemotron-3-nano:4b) on the full benchmark
- A held-out split. The benchmark has been used for development, so these numbers are
  optimistic for unseen questions.
- Runtime memory and GPU utilisation per query
- Expert review of the 6 `review: expert` items
