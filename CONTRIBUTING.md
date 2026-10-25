# Contributing to JAZARI

Thanks for helping build a robotics expert grounded in explicit knowledge.

## Ground rules

1. **No invented specifications.** Every fact in the graph must come from a pinned source
   (`knowledge-graphs/manifests/sources.yaml`) or be a documented derivation. If a value
   is not stated, leave it out. "Not stated" is not zero.
2. **No hardcoded answers.** Chat behaviour changes go through tools, queries or prompts.
3. **Reuse ontologies.** Before adding a class to `ontology/jazari/jazari.ttl`, check
   IEEE 1872 (CORA/CORAX/RPARTS/POS), SOSA, QUDT and PROV-O, and record the decision in
   `docs/ontology/reference-ontologies.md`.
4. **Licenses.** Do not commit third-party robot files, meshes, standard texts or model
   weights. Add sources to the manifest with license and pinned commit instead.

## Workflow

- Branch from `main` (`feature/<topic>`), open a pull request, keep commits focused.
- Never force-push to `main`.
- Before opening a PR, run everything that applies:

```bash
cd backend && uv run pytest && uv run ruff check jazari
```

```bash
cd frontend && npx tsc -b && npm test
```

```bash
cd backend && uv run jazari build && uv run jazari validate
```

- If you change prompts, tools or the model default, run `uv run jazari eval` and include
  the before/after summary in the PR.

## Adding a robot configuration

1. Add the source (pinned SHA, license, sparse paths) and the configuration (files,
   selection rationale) to `sources.yaml`.
2. Run `jazari fetch && jazari build && jazari validate`, and review conflicts and
   inconsistencies.
3. Add hand-verified benchmark items to `evaluation/benchmark.yaml` and integration tests.
