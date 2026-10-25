"""Write the final answer from tool results and check its numbers against them."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .ollama import OllamaClient
from .schemas import ToolResult, Verification

PROMPTS = Path(__file__).parent / "prompts"

# numbers not glued to letters/underscores (so "g1_29dof", "E2", "rev_1_0" are ignored)
_NUMBER = re.compile(r"(?<![\w.\-])-?\d+(?:\.\d+)?(?![\w])")


def results_payload(results: list[ToolResult]) -> str:
    blocks = []
    for r in results:
        block = {"tool": r.tool, "arguments": r.arguments, "ok": r.ok}
        if r.ok:
            block["facts"] = r.summary
            if r.derivations:
                block["derivations"] = r.derivations
            block["evidence"] = [f"[{e.id}] {e.evidence_type}: {e.label}"
                                 + (f" ({e.source})" if e.source else "") for e in r.evidence]
        else:
            block["error"] = r.error
        blocks.append(block)
    return json.dumps(blocks, indent=1, default=str)


def compose_llm(llm: OllamaClient, question: str, results: list[ToolResult],
                history: list[tuple[str, str]]) -> str:
    system = (PROMPTS / "composer.md").read_text(encoding="utf-8")
    messages = [{"role": "system", "content": system}]
    for q, a in history[-2:]:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a[:1200]}]
    messages.append({"role": "user", "content":
                     f"QUESTION: {question}\n\nTOOL RESULTS (JSON):\n{results_payload(results)}"})
    return llm.chat(messages, temperature=0.1).strip()


def compose_template(question: str, results: list[ToolResult]) -> str:
    """Deterministic answer used when no LLM is available."""
    lines = ["*Deterministic answer (no LLM): knowledge-graph results shown directly.*", ""]
    for r in results:
        if not r.ok:
            lines.append(f"**{r.tool}**: {r.error}")
            continue
        ids = " ".join(f"[{e.id}]" for e in r.evidence[:3])
        s = r.summary
        if r.tool == "joint_summary":
            classes = ", ".join(f"{n} {c}" for c, n in s["joints_by_class"].items())
            fmt = "; ".join(f"{f}: {v['total']} ({', '.join(f'{n} {t}' for t, n in v.items() if t != 'total')})"
                            for f, v in s["joints_by_source_format"].items())
            lines.append(f"**{s['configuration']}** has **{s['total_joints_in_graph']} joints** in the "
                         f"knowledge graph: {classes}. Per source file: {fmt}. "
                         f"Articulated DoF: {s['articulated_dof']}; actuated joints: {s['actuated_joints']}. {ids}")
        else:
            lines.append(f"**{r.tool}** {ids}")
            lines.append("```json\n" + json.dumps(s, indent=1, default=str)[:2500] + "\n```")
    return "\n\n".join(lines)


# "[...]" not followed by "(" (so Markdown links survive)
_BRACKET = re.compile(r"\s?\[([^\[\]]{1,80})\](?!\()")


def sanitize_citations(answer: str, evidence_ids: set[str]) -> tuple[str, list[str]]:
    """Remove citations that do not point to real evidence (e.g. invented standard clauses)."""
    removed: list[str] = []

    def repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        if inner in evidence_ids:
            return m.group(0)
        if re.fullmatch(r"E\d+", inner) or re.search(r"\d", inner):
            removed.append(f"[{inner}]")
            return ""
        return m.group(0)  # e.g. a Markdown checkbox or bracketed word without digits

    return _BRACKET.sub(repl, answer), removed


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def _norm(n: str) -> str:
    try:
        v = float(n)
    except ValueError:
        return n
    return f"{v:g}"


def verify_numbers(answer: str, question: str, results: list[ToolResult]) -> Verification:
    """Every number in the answer should appear in a tool result (or in the question)."""
    stripped = re.sub(r"\[E\d+\]", "", answer)
    stripped = re.sub(r"`[^`]*`", "", stripped)  # identifiers in code spans
    stripped = re.sub(r"(?m)^\s*\d+\.\s", "", stripped)  # ordered-list markers
    found = _numbers(stripped)
    corpus = question + json.dumps([r.summary for r in results], default=str)
    corpus += json.dumps([r.data for r in results], default=str)
    # the corpus is matched loosely: "@L161" or "g1_29dof" still contribute 161 and 29
    known = {_norm(n) for n in re.findall(r"-?\d+(?:\.\d+)?", corpus)}
    # 1 and 2 also appear as table indices and phrasing; wrong small counts are a known blind spot
    unsupported = sorted(n for n in found if _norm(n) not in known and not (n.isdigit() and int(n) <= 2))
    note = None
    if unsupported:
        note = "These numbers in the answer were not found in the knowledge-graph results; treat them with caution."
    return Verification(numbers_checked=len(found), unsupported_numbers=unsupported, note=note)
