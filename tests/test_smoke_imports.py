"""
Smoke tests: every module of the project must be importable.

Catches regressions like a removed import or a broken optional dependency
without needing a GPU, an LLM server or downloaded models.
"""

import importlib

import pytest

MODULES = [
    "config",
    "src",
    "src.agent_tools",
    "src.file_processor",
    "src.i18n",
    "src.llm_engine",
    "src.main",
    "src.memory_manager",
    "src.stt_engine",
    "src.tts_engine",
    "src.web_search",
    "backend",
    "backend.api",
    "backend.background_tasks",
    "backend.database",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    assert importlib.import_module(name) is not None


def test_optional_heavy_deps_present():
    """Dependencies that must be installed by requirements.txt."""
    missing = []
    for dep in ("fastapi", "httpx", "chromadb", "pydantic_settings", "mss", "PIL"):
        try:
            importlib.import_module(dep)
        except Exception:
            missing.append(dep)
    assert not missing, f"missing runtime dependencies: {missing}"