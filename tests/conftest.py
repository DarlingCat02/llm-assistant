"""
Shared pytest fixtures.

Tests must not require a GPU, an LLM server, or real models — they exercise
pure logic only (prompt assembly, persona store, memory scoping, API models).
"""

import os
import sys
from pathlib import Path

import pytest

# Make sure the project root is importable regardless of the invocation dir
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import get_config  # noqa: E402


@pytest.fixture(autouse=True)
def reset_config_cache():
    """Drop the lru_cache on get_config around every test."""
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """Point the process at a throwaway project dir (config.base_dir)."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_PROVIDER=ollama\n"
        "LLM_HOST=http://localhost:11434\n"
        "LLM_MODEL=test-model\n"
        "GENERAL_LANGUAGE=en\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_HOST", "http://localhost:11434")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("GENERAL_LANGUAGE", "en")
    monkeypatch.delenv("PERSONALITY_RU", raising=False)
    monkeypatch.delenv("PERSONALITY_EN", raising=False)
    get_config.cache_clear()
    yield tmp_path


@pytest.fixture
def ru_env(monkeypatch):
    """Force the UI/prompt language to Russian."""
    monkeypatch.setenv("GENERAL_LANGUAGE", "ru")
    get_config.cache_clear()
    yield
    get_config.cache_clear()