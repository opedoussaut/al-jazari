"""Keyword (BM25) retrieval over pinned technical documents.

Documents are split into paragraph-sized chunks that keep their line range, so every
hit can be cited as a GitHub permalink to exact lines. Semantic embeddings are planned
(see docs/roadmap.md); BM25 is used first because it needs no model download and is
fully deterministic.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..manifest import Manifest

_TOKEN = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    # split snake_case identifiers too, so "hip_pitch" matches "hip pitch"
    return tokens + [p for t in tokens if "_" in t for p in t.split("_") if p]


@dataclass
class Chunk:
    source_id: str
    path: str
    start_line: int
    end_line: int
    text: str
    url: str
    configuration: str


class DocumentIndex:
    k1, b = 1.5, 0.75

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.tfs = [Counter(tokenize(c.text)) for c in chunks]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avg = sum(self.lens) / max(len(self.lens), 1)
        df = Counter(t for tf in self.tfs for t in tf)
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    @classmethod
    def from_manifest(cls, manifest: Manifest, sources_dir: Path) -> DocumentIndex:
        chunks: list[Chunk] = []
        for _, config in manifest.configurations():
            for doc in config.documents:
                src = manifest.source(doc.source)
                path = sources_dir / doc.source / doc.path
                if not path.exists():
                    continue
                lines = path.read_text(encoding="utf-8").splitlines()
                chunks += _chunk(lines, doc.source, doc.path, src.blob_url(doc.path), config.id)
        return cls(chunks)

    def search(self, query: str, k: int = 4) -> list[tuple[float, Chunk]]:
        q = tokenize(query)
        scored = []
        for i, tf in enumerate(self.tfs):
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg))
            if s > 0:
                scored.append((s, self.chunks[i]))
        return sorted(scored, key=lambda x: -x[0])[:k]


def _chunk(lines: list[str], source_id: str, path: str, url: str, config: str,
           max_lines: int = 14) -> list[Chunk]:
    """Split on blank lines and headings; long blocks (tables) are cut every max_lines."""
    chunks, start, buf = [], 0, []
    table_header: list[str] = []

    def flush(end: int) -> None:
        body = buf
        if table_header and buf and buf[0] not in table_header and buf[0].startswith("|"):
            body = table_header + buf  # repeat the header in table continuation chunks
        text = "\n".join(body).strip()
        if text:
            chunks.append(Chunk(source_id, path, start + 1, end, text,
                                f"{url}#L{start + 1}-L{end}", config))

    for i, line in enumerate(lines):
        is_row = line.startswith("|")
        if not is_row:
            table_header = []
        elif not table_header and i + 1 < len(lines) and set(lines[i + 1].strip()) <= set("|-: "):
            table_header = [line, lines[i + 1]]
        boundary = not line.strip() or line.startswith("#") or len(buf) >= max_lines
        if boundary and buf:
            flush(i)
            buf = []
        if not buf:
            start = i
        if line.strip():
            buf.append(line)
    if buf:
        flush(len(lines))
    return chunks
