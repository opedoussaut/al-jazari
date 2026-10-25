"""Decide which knowledge tools answer a question.

The LLM planner returns a constrained JSON plan (Ollama structured output with an
enum of tool names). The rule planner is a deterministic keyword fallback used when
no LLM is reachable; which planner ran is always reported in the response trace.
"""

from __future__ import annotations

import re
from pathlib import Path

from .ollama import OllamaClient
from .schemas import ToolCall
from .tools import Toolbox

PROMPTS = Path(__file__).parent / "prompts"


def plan_schema(tool_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "tools": {
                "type": "array", "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": tool_names},
                        "arguments": {
                            "type": "object",
                            "properties": {
                                "configuration": {"type": "string"}, "joint": {"type": "string"},
                                "term": {"type": "string"}, "query": {"type": "string"},
                            },
                        },
                    },
                    "required": ["name", "arguments"],
                },
            },
        },
        "required": ["tools"],
    }


def llm_plan(llm: OllamaClient, toolbox: Toolbox, question: str, current: str | None,
             history: list[tuple[str, str]]) -> list[ToolCall]:
    tools = "\n".join(
        f"- {s.name}({', '.join(f'{k}: {v}' for k, v in s.parameters.items())}): {s.description}"
        for s in toolbox.specs.values())
    configs = "\n".join(f"- {c['id']}: {c['label']} (robot: {c['robot']}, {c['category']})"
                        for c in toolbox.configurations())
    hist = "\n".join(f"User: {q}\nJAZARI: {a[:300]}" for q, a in history[-3:]) or "(none)"
    system = ((PROMPTS / "planner.md").read_text(encoding="utf-8")
              .replace("{tools}", tools).replace("{configurations}", configs)
              .replace("{current}", current or "none").replace("{history}", hist))
    out = llm.chat_json([{"role": "system", "content": system}, {"role": "user", "content": question}],
                        plan_schema(list(toolbox.specs)))
    return [ToolCall(name=t["name"], arguments=t.get("arguments") or {}) for t in out.get("tools", [])][:4]


_ONTO_TERM = re.compile(
    r"(?:what is (?:an? |the )?|define |definition of (?:an? )?|concept of (?:an? )?|"
    r"defines? the concept of (?:an? )?)([a-z][a-z \-]{1,40}?)(?:\s+according|\s+in\s|\?|$|,)",
    re.IGNORECASE)


def rule_plan(toolbox: Toolbox, question: str) -> list[ToolCall]:
    q = question.lower()
    calls: list[ToolCall] = []
    robots = [c["id"] for c in toolbox.mentioned_configurations(question)]
    args = {"configuration": robots[0]} if robots else {}

    def add(name: str, **extra: str) -> None:
        if not any(c.name == name for c in calls):
            calls.append(ToolCall(name=name, arguments={**args, **extra}))

    if any(k in q for k in ("ontology", "cora", "ieee", "according to", "concept", "define")):
        m = _ONTO_TERM.search(question)
        term = m.group(1).strip() if m else ("robot" if "robot" in q else question)
        calls.append(ToolCall(name="ontology_lookup", arguments={"term": term}))
    joint = re.search(r"\b([a-z]+(?:_[a-z]+)*_joint)\b", q)
    if joint:
        add("joint_details", joint=joint.group(1))
    if re.search(r"how many joints|joint types?|types of joints|degrees of freedom|\bdof\b|count.*joints|joints.*types", q):
        add("joint_summary")
    if any(k in q for k in ("kinematic", "structure", "chain", "tree", "architecture", "topology")):
        add("kinematic_structure")
    if any(k in q for k in ("actuator", "motor", "actuated")):
        add("actuators")
    if any(k in q for k in ("sensor", "imu", "camera", "lidar")):
        add("sensors")
    if any(k in q for k in ("mass", "weight", "heavy", "links")):
        add("links_and_masses")
    if any(k in q for k in ("inconsisten", "conflict", "disagree", "mismatch", "missing")):
        add("source_inconsistencies")
    if any(k in q for k in ("source", "revision", "variant", "version", "configuration", "which file")):
        add("configuration_info")
    if any(k in q for k in ("which robots", "available robots", "list robots", "robots do you")):
        add("list_robots")
    if not calls and robots:
        add("joint_summary")
    # a comparison names several robots: repeat each robot tool for the others
    robot_calls = [c for c in calls if "configuration" in c.arguments]
    for other in robots[1:]:
        for c in robot_calls:
            if len(calls) < 4:
                calls.append(ToolCall(name=c.name, arguments={**c.arguments, "configuration": other}))
    if not calls:
        calls.append(ToolCall(name="search_documents", arguments={"query": question}))
    return calls[:4]
