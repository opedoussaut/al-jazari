"""Benchmark runner: scores tool selection, required facts and abstention separately."""

from __future__ import annotations

import json
import platform
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

ABSTAIN_PHRASES = (
    "not in the knowledge graph", "not ingested", "does not contain", "doesn't contain", "cannot provide",
    "not present", "not available", "no information", "not stated", "not specified", "not included",
    "is not provided", "are not provided", "do not have", "does not have", "unavailable", "not found",
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace("*", "").replace("`", ""))


def fact_present(fact: object, answer: str) -> bool:
    a = _norm(answer)
    f = str(fact)
    if re.fullmatch(r"-?\d+(\.\d+)?", f):
        nums = {float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", answer.replace(",", ""))}
        return float(f) in nums or any(f"{n:g}".startswith(f) for n in nums if "." in f)
    return _norm(f) in a or _norm(f).replace(" ", "_") in a


def score_item(item: dict, resp) -> dict:
    tools_called = [t.tool for t in resp.trace]
    expected_tools = item.get("tools", [])
    # an empty list means no particular tool is required
    tool_ok = any(t in tools_called for t in expected_tools) if expected_tools else True
    missing = [f for f in item.get("facts", []) if not fact_present(f, resp.answer)]
    forbidden = [f for f in item.get("forbidden", []) if fact_present(f, resp.answer)]
    abstained = any(p in resp.answer.lower() for p in ABSTAIN_PHRASES)
    if item.get("abstain"):
        answer_ok = abstained and not forbidden
    else:
        answer_ok = not missing and not forbidden
    return {
        "id": item["id"], "category": item["category"], "question": item["question"],
        "tools_called": tools_called, "tool_selection_ok": bool(tool_ok),
        "missing_facts": missing, "forbidden_found": forbidden, "abstained": abstained,
        "answer_ok": answer_ok, "needs_expert_review": item.get("review") == "expert",
        "unsupported_numbers": resp.verification.unsupported_numbers,
        "removed_citations": resp.verification.removed_citations,
        "planner": resp.planner, "composer": resp.composer, "latency_ms": resp.latency_ms,
        "answer": resp.answer,
    }


def run_benchmark(engine, benchmark_path: Path, out_dir: Path, use_llm: bool) -> dict:
    items = yaml.safe_load(benchmark_path.read_text(encoding="utf-8"))["items"]
    results = []
    for item in items:
        resp = engine.ask(item["question"], session_id=f"bench-{item['id']}", use_llm=use_llm)
        results.append(score_item(item, resp))
        print(f"{item['id']:8s} tools={'OK ' if results[-1]['tool_selection_ok'] else 'BAD'} "
              f"answer={'OK ' if results[-1]['answer_ok'] else 'BAD'} {resp.latency_ms / 1000:5.1f}s "
              f"{results[-1]['missing_facts'] or ''}", flush=True)

    def rate(key: str, subset: list[dict]) -> float:
        return round(sum(r[key] for r in subset) / len(subset), 3) if subset else 0.0

    by_cat = {}
    for cat in sorted({r["category"] for r in results}):
        sub = [r for r in results if r["category"] == cat]
        by_cat[cat] = {"n": len(sub), "tool_selection": rate("tool_selection_ok", sub), "answer": rate("answer_ok", sub)}
    latencies = sorted(r["latency_ms"] for r in results)
    report = {
        "benchmark": str(benchmark_path.name), "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "llm" if use_llm else "rules+template", "model": engine.settings.model if use_llm else None,
        "host": platform.platform(), "n": len(results),
        "tool_selection_accuracy": rate("tool_selection_ok", results),
        "answer_accuracy": rate("answer_ok", results),
        "answers_with_unsupported_numbers": sum(1 for r in results if r["unsupported_numbers"]),
        "answers_with_removed_citations": sum(1 for r in results if r["removed_citations"]),
        "needs_expert_review": [r["id"] for r in results if r["needs_expert_review"]],
        "latency_ms": {"median": latencies[len(latencies) // 2], "max": latencies[-1]},
        "by_category": by_cat, "results": results,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = (engine.settings.model.replace(":", "-").replace("/", "-") if use_llm else "rules")
    out = out_dir / f"{time.strftime('%Y%m%d')}-{tag}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    print(f"report written to {out}")
    return report
