"""Typed access to knowledge-graphs/manifests/sources.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class Source(BaseModel):
    id: str
    repo: str
    revision: str
    revision_date: str | None = None
    license: str
    license_file: str | None = None
    license_note: str | None = None
    copyright: str | None = None
    sparse: list[str]

    def blob_url(self, path: str, line: int | None = None) -> str:
        url = f"{self.repo}/blob/{self.revision}/{path}"
        return f"{url}#L{line}" if line else url


class SourceFile(BaseModel):
    source: str
    path: str
    format: str | None = None


class Configuration(BaseModel):
    id: str
    label: str
    native_name: str
    mode_machine: int | None = None
    baseline: bool = False
    selection_rationale: str
    files: list[SourceFile]
    documents: list[SourceFile] = []


class Robot(BaseModel):
    id: str
    name: str
    manufacturer: str
    category: str
    homepage: str | None = None
    configurations: list[Configuration]


class Manifest(BaseModel):
    sources: list[Source]
    robots: list[Robot]

    def source(self, source_id: str) -> Source:
        for s in self.sources:
            if s.id == source_id:
                return s
        raise KeyError(f"unknown source {source_id!r}")

    def configurations(self) -> list[tuple[Robot, Configuration]]:
        return [(r, c) for r in self.robots for c in r.configurations]


def load_manifest(path: Path) -> Manifest:
    return Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
