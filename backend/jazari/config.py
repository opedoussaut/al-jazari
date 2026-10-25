"""Runtime configuration, read from environment variables or a .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JAZARI_", env_file=REPO_ROOT / ".env", extra="ignore"
    )

    # Inference. Use http://host.docker.internal:11434 when the backend runs in
    # Docker and Ollama runs on the Windows host.
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen3-coder:30b"
    llm_timeout_s: float = 240.0
    # When the LLM is unreachable, fall back to the deterministic keyword planner
    # and a templated answer instead of failing the request.
    allow_llm_fallback: bool = True

    repo_root: Path = REPO_ROOT
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def manifest_path(self) -> Path:
        return self.repo_root / "knowledge-graphs" / "manifests" / "sources.yaml"

    @property
    def lock_path(self) -> Path:
        return self.repo_root / "knowledge-graphs" / "manifests" / "sources.lock.json"

    @property
    def sources_dir(self) -> Path:
        return self.repo_root / ".cache" / "sources"

    @property
    def generated_dir(self) -> Path:
        return self.repo_root / "knowledge-graphs" / "generated"

    @property
    def ontology_dir(self) -> Path:
        return self.repo_root / "ontology"


@lru_cache
def get_settings() -> Settings:
    return Settings()
