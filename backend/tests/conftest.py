from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from jazari.config import get_settings
from jazari.manifest import Manifest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def demo_dir() -> Path:
    return FIXTURES / "src" / "demo"


@pytest.fixture
def demo_manifest() -> Manifest:
    return Manifest.model_validate({
        "sources": [{"id": "demo", "repo": "https://example.org/demo", "license": "MIT",
                     "revision": "0" * 40, "sparse": ["*"]}],
        "robots": [{"id": "demo-arm", "name": "Demo Arm", "manufacturer": "Test", "category": "manipulator",
                    "configurations": [{
                        "id": "base", "label": "Demo arm base", "native_name": "demo_arm", "baseline": True,
                        "selection_rationale": "fixture",
                        "files": [{"source": "demo", "path": "arm.urdf", "format": "urdf"},
                                  {"source": "demo", "path": "arm.xml", "format": "mjcf"}],
                        "documents": [{"source": "demo", "path": "README.md"}],
                    }]}],
    })


def _g1_ready() -> bool:
    s = get_settings()
    lock = s.lock_path
    return lock.exists() and (s.generated_dir / "unitree-g1__g1-29dof-rev-1-0.ttl").exists() and \
        "unitree_ros" in json.loads(lock.read_text()).get("sources", {})


def _ollama_ready() -> bool:
    s = get_settings()
    try:
        tags = httpx.get(f"{s.ollama_url}/api/tags", timeout=3).json()
    except httpx.HTTPError:
        return False
    return any(m["name"] == s.model for m in tags.get("models", []))


def pytest_collection_modifyitems(config, items):
    g1, ollama = _g1_ready(), None
    for item in items:
        if "sources" in item.keywords and not g1:
            item.add_marker(pytest.mark.skip(reason="run `jazari fetch && jazari build && jazari validate` first"))
        if "ollama" in item.keywords:
            ollama = _ollama_ready() if ollama is None else ollama
            if not ollama:
                item.add_marker(pytest.mark.skip(reason="Ollama or the configured model is not available"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()
