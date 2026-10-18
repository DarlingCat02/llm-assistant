"""
Personality layer: user instructions appended to the base system prompt.

Critical regression guarantee: with an empty personality the assembled prompt
must stay byte-identical to the base prompt.
"""

import pytest

from config import get_config
from src.llm_engine import LLMEngine


@pytest.fixture
def engine():
    return LLMEngine()


def test_empty_personality_keeps_base_prompt(engine):
    assert engine.get_system_prompt() == engine._get_base_system_prompt()


def test_personality_from_env_is_appended(monkeypatch, ru_env, engine):
    monkeypatch.setenv("PERSONALITY_RU", "Отвечай как рыцарь")
    get_config.cache_clear()
    prompt = engine.get_system_prompt()
    base = engine._get_base_system_prompt()
    assert prompt.startswith(base)
    assert prompt.endswith("Отвечай как рыцарь")


def test_personality_is_language_isolated(monkeypatch, ru_env, engine):
    """A prompt written for RU must not leak into an EN session."""
    monkeypatch.setenv("PERSONALITY_RU", "только по-русски")
    monkeypatch.setenv("PERSONALITY_EN", "english only")
    get_config.cache_clear()

    assert engine.get_system_prompt().endswith("только по-русски")

    monkeypatch.setenv("GENERAL_LANGUAGE", "en")
    get_config.cache_clear()
    assert engine.get_system_prompt().endswith("english only")


def test_persona_overrides_env_layer(monkeypatch, ru_env, engine):
    monkeypatch.setenv("PERSONALITY_RU", "из .env")
    get_config.cache_clear()
    engine.set_persona_prompt("из персоны", "from persona")
    assert engine.get_system_prompt().endswith("из персоны")

    # Empty persona -> fall back to the .env layer
    engine.set_persona_prompt("", "")
    assert engine.get_system_prompt().endswith("из .env")

    # No env layer either -> base prompt
    monkeypatch.setenv("PERSONALITY_RU", "")
    get_config.cache_clear()
    assert engine.get_system_prompt() == engine._get_base_system_prompt()


def test_persona_state_roundtrip(engine):
    engine.set_persona_prompt("ru text", "en text")
    state = engine.get_persona_prompt()
    assert state["ru"] == "ru text" and state["en"] == "en text" and state["active"] is True

    engine.set_persona_prompt("", "")
    assert engine.get_persona_prompt()["active"] is False


def test_persona_with_empty_language_falls_back(monkeypatch, ru_env, engine):
    """Persona with only an EN prompt: RU session must not get a broken prompt."""
    engine.set_persona_prompt("", "You are an editor")
    assert engine.get_system_prompt() == engine._get_base_system_prompt()


def test_newlines_survive_env_roundtrip(tmp_path, monkeypatch):
    """.env is line based - newlines must be escaped on write, restored on read.

    The file used to be the developer's real .env. If the file did not exist
    yet, this test left one behind containing nothing but a personality.
    """
    import os

    from config import save_config, reload_config

    env_path = tmp_path / ".env"
    environment = dict(os.environ)
    try:
        text = "Строка 1\nСтрока 2"
        save_config(personality_ru=text, env_path=env_path)
        raw = env_path.read_text(encoding="utf-8")
        assert "PERSONALITY_RU=Строка 1\\nСтрока 2" in raw
        assert get_config.cache_clear() is None
        monkeypatch.setenv("PERSONALITY_RU",
                           raw.split("PERSONALITY_RU=")[1].split("\n")[0])
        reload_config()
        assert get_config().personality.ru == text
    finally:
        os.environ.clear()
        os.environ.update(environment)
        get_config.cache_clear()