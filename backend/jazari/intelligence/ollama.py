"""Minimal Ollama HTTP client. The rest of JAZARI only depends on `LLMClient.chat`, so
another OpenAI-compatible or local runtime can be substituted later."""

from __future__ import annotations

import json
from typing import Any

import httpx


class LLMUnavailable(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout_s: float):
        self.base_url, self.model, self.timeout_s = base_url.rstrip("/"), model, timeout_s

    def chat(self, messages: list[dict[str, str]], schema: dict | None = None,
             temperature: float = 0.0, num_ctx: int = 16384) -> str:
        payload: dict[str, Any] = {
            "model": self.model, "messages": messages, "stream": False, "keep_alive": "30m",
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        }
        if schema is not None:
            payload["format"] = schema
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout_s)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMUnavailable(f"Ollama request failed: {e}") from e
        return r.json()["message"]["content"]

    def chat_json(self, messages: list[dict[str, str]], schema: dict) -> dict:
        text = self.chat(messages, schema=schema)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMUnavailable(f"model returned invalid JSON: {text[:200]}") from e

    def status(self) -> dict:
        try:
            v = httpx.get(f"{self.base_url}/api/version", timeout=5).json()
            tags = httpx.get(f"{self.base_url}/api/tags", timeout=5).json()
        except httpx.HTTPError as e:
            return {"reachable": False, "url": self.base_url, "error": str(e), "model": self.model}
        names = [m["name"] for m in tags.get("models", [])]
        return {"reachable": True, "url": self.base_url, "version": v.get("version"),
                "model": self.model, "model_installed": self.model in names, "installed_models": names}
