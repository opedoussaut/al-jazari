"""Command line entry point: `jazari fetch | build | validate | ask | serve`."""

from __future__ import annotations

import argparse
import json
import sys

from .config import get_settings
from .manifest import load_manifest


def cmd_fetch(_: argparse.Namespace) -> int:
    from .fetch import fetch_all

    s = get_settings()
    lock = fetch_all(load_manifest(s.manifest_path), s.sources_dir, s.lock_path)
    for sid, info in lock["sources"].items():
        print(f"{sid}: {info['revision']} ({len(info['files'])} files)")
    print(f"lock written to {s.lock_path}")
    return 0


def cmd_build(_: argparse.Namespace) -> int:
    from .fetch import verify_file
    from .kg.builder import build_all

    s = get_settings()
    manifest = load_manifest(s.manifest_path)
    lock = json.loads(s.lock_path.read_text(encoding="utf-8"))
    for _, config in manifest.configurations():
        for f in config.files + config.documents:
            verify_file(lock, f.source, f.path, s.sources_dir / f.source / f.path)
    for r in build_all(manifest, s.sources_dir, s.generated_dir):
        print(f"[{r.configuration}] files: {', '.join(r.files)}")
        for fmt, counts in r.counts.items():
            print(f"  {fmt}: {counts}")
        for w in r.warnings:
            print(f"  warning: {w}")
        for c in r.conflicts:
            print(f"  conflict: {c}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from rdflib import Graph

    from .kg import GraphStore
    from .validation import validate_graph

    s = get_settings()
    store = GraphStore.load(s.ontology_dir, s.sources_dir, s.generated_dir)
    ontology = Graph()
    for p in store.files.reference:
        ontology.parse(p, format="xml")
    for p in store.files.jazari:
        ontology.parse(p, format="turtle")
    failed = False
    for p in store.files.knowledge_graphs:
        data = Graph().parse(p, format="turtle")
        report = validate_graph(data, ontology, s.ontology_dir / "validation" / "shapes.ttl")
        out = s.generated_dir / f"{p.stem}.validation.json"
        out.write_text(json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")
        print(f"{p.name}: {'OK' if report.ok else 'FAILED'} (SHACL conforms: {report.shacl_conforms}, "
              f"{len(report.errors)} errors, {len(report.inconsistencies)} cross-format inconsistencies, "
              f"{len(report.warnings)} warnings) -> {out.name}")
        for line in (report.shacl_results + report.errors)[: args.max]:
            print(f"  ERROR {line}")
        for line in report.inconsistencies[: args.max]:
            print(f"  INCONSISTENT {line}")
        failed |= not report.ok
    return 1 if failed else 0


def cmd_ask(args: argparse.Namespace) -> int:
    from .intelligence.engine import get_engine

    engine = get_engine()
    resp = engine.ask(args.question, session_id="cli")
    if args.json:
        print(resp.model_dump_json(indent=2))
        return 0
    print(resp.answer)
    print("\n--- context:", resp.context.model_dump())
    for t in resp.trace:
        print(f"--- tool {t.tool}({t.arguments}) -> {t.row_count} rows; query: {t.query_name}")
    for e in resp.evidence:
        print(f"--- evidence [{e.evidence_type}] {e.label}: {e.url}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from .evaluation import run_benchmark
    from .intelligence.engine import get_engine

    s = get_settings()
    run_benchmark(get_engine(), s.repo_root / "evaluation" / "benchmark.yaml",
                  s.repo_root / "evaluation" / "results", use_llm=not args.no_llm)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("jazari.api.app:app", host=args.host, port=args.port, reload=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jazari", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="fetch pinned upstream sources").set_defaults(fn=cmd_fetch)
    sub.add_parser("build", help="build knowledge graphs from fetched sources").set_defaults(fn=cmd_build)
    v = sub.add_parser("validate", help="validate generated knowledge graphs")
    v.add_argument("--max", type=int, default=20)
    v.set_defaults(fn=cmd_validate)
    a = sub.add_parser("ask", help="ask JAZARI a question")
    a.add_argument("question")
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_ask)
    ev = sub.add_parser("eval", help="run the evaluation benchmark")
    ev.add_argument("--no-llm", action="store_true", help="rule planner + template answers only")
    ev.set_defaults(fn=cmd_eval)
    sv = sub.add_parser("serve", help="run the API server")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(fn=cmd_serve)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
