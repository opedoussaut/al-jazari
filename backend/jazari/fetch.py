"""Fetch pinned upstream sources and write a lock file with file hashes.

Downloaded trees are untrusted data: they are only ever parsed (XML with
entity resolution and network access disabled, OWL via rdflib), never executed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .manifest import Manifest, Source


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def fetch_source(source: Source, dest_root: Path) -> Path:
    dest = dest_root / source.id
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--quiet", "--filter=blob:none", "--no-checkout", source.repo, str(dest))
    _git("sparse-checkout", "set", "--no-cone", *source.sparse, cwd=dest)
    try:
        _git("checkout", "--quiet", source.revision, cwd=dest)
    except subprocess.CalledProcessError:
        _git("fetch", "--quiet", "origin", source.revision, cwd=dest)
        _git("checkout", "--quiet", source.revision, cwd=dest)
    head = _git("rev-parse", "HEAD", cwd=dest)
    if head != source.revision:
        raise RuntimeError(f"{source.id}: checked out {head}, expected {source.revision}")
    return dest


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_all(manifest: Manifest, sources_dir: Path, lock_path: Path) -> dict:
    retrieved = datetime.now(UTC).isoformat(timespec="seconds")
    lock: dict = {"retrieved": retrieved, "sources": {}}
    for source in manifest.sources:
        dest = fetch_source(source, sources_dir)
        files = sorted(
            p for p in dest.rglob("*") if p.is_file() and ".git" not in p.relative_to(dest).parts
        )
        lock["sources"][source.id] = {
            "repo": source.repo,
            "revision": source.revision,
            "license": source.license,
            "files": {p.relative_to(dest).as_posix(): sha256(p) for p in files},
        }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return lock


def verify_file(lock: dict, source_id: str, rel_path: str, path: Path) -> None:
    expected = lock["sources"][source_id]["files"].get(rel_path)
    if expected is None:
        raise RuntimeError(f"{source_id}:{rel_path} is not in sources.lock.json; run `jazari fetch`")
    if sha256(path) != expected:
        raise RuntimeError(f"{source_id}:{rel_path} hash mismatch with sources.lock.json")
