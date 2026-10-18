"""
Config round-trip: save_config() must persist new keys without wiping others.

These tests used to rewrite the developer's real .env and restore it afterwards.
That works right up to the moment a run is interrupted, and it silently ate a
real .env once. Each test now gets a file of its own in tmp_path, and the
process environment is put back the way it was - save_config() mirrors values
into os.environ, so without that they leaked into the rest of the session.
"""

import os

import pytest

import config as cfg_mod
from config import get_config, save_config, reload_config


@pytest.fixture
def env_file(tmp_path):
    """An .env of this test's own, with the environment left as found."""
    path = tmp_path / ".env"
    environment = dict(os.environ)
    try:
        yield path
    finally:
        os.environ.clear()
        os.environ.update(environment)
        get_config.cache_clear()


def test_stt_model_saved(env_file):
    save_config(stt_model="small", env_path=env_file)
    raw = env_file.read_text(encoding="utf-8")
    assert "STT_MODEL=small" in raw


def test_hotkeys_saved(env_file):
    save_config(hotkey_voice="Alt+F9", hotkey_voice_num="Ctrl+Num3",
                hotkey_live="F12", env_path=env_file)
    raw = env_file.read_text(encoding="utf-8")
    assert "HOTKEY_VOICE=Alt+F9" in raw
    assert "HOTKEY_VOICE_NUM=Ctrl+Num3" in raw
    assert "HOTKEY_LIVE=F12" in raw


def test_empty_values_do_not_overwrite(env_file):
    """An empty string must not wipe an existing value (partial updates)."""
    env_file.write_text("HOTKEY_VOICE=Ctrl+Shift+V\n", encoding="utf-8")
    save_config(hotkey_live="F12", env_path=env_file)
    raw = env_file.read_text(encoding="utf-8")
    assert "HOTKEY_VOICE=Ctrl+Shift+V" in raw
    assert "HOTKEY_LIVE=F12" in raw


def test_other_keys_survive_partial_update(env_file):
    env_file.write_text("LLM_MODEL=qwen\nPERSONALITY_RU=стиль\nSTT_MODEL=small\n",
                        encoding="utf-8")
    save_config(hotkey_live="F12", env_path=env_file)
    raw = env_file.read_text(encoding="utf-8")
    for expected in ("LLM_MODEL=qwen", "PERSONALITY_RU=стиль", "STT_MODEL=small",
                     "HOTKEY_LIVE=F12"):
        assert expected in raw


def test_personality_en_newlines_are_escaped(env_file):
    """Regression: written raw, a multi-line English personality became several
    physical lines in .env and everything after the first newline was lost."""
    save_config(personality_en="Line 1\nLine 2", env_path=env_file)
    raw = env_file.read_text(encoding="utf-8")
    assert "PERSONALITY_EN=Line 1\\nLine 2" in raw
    assert raw.count("\n") == 1, "the value leaked across physical lines"


def test_lm_studio_host_gets_a_scheme():
    """Regression: the fixup only recognised the literal "localhost", so pointing
    the config at another machine produced a URL httpx cannot open and every
    chat request failed."""
    from config import LLMConfig, LLMProvider

    def base(host):
        return LLMConfig(provider=LLMProvider.LM_STUDIO, host=host,
                         model="x").api_base_url

    assert base("localhost") == "http://localhost:1234/v1"
    assert base("localhost:1234") == "http://localhost:1234/v1"
    assert base("192.168.1.50:1234") == "http://192.168.1.50:1234/v1"
    assert base("192.168.1.50") == "http://192.168.1.50:1234/v1"
    assert base("gpu-box.lan") == "http://gpu-box.lan:1234/v1"
    assert base("http://gpu-box.lan:1234/") == "http://gpu-box.lan:1234/v1"
    assert base("https://host:443") == "https://host:443/v1"


def test_lm_studio_host_may_already_end_in_v1():
    """Regression: someone who writes the full OpenAI-style base got
    /v1/v1/chat/completions. LM Studio answers that with 200 and an empty
    completion, so the assistant looks broken while the setting is at fault."""
    from config import LLMConfig, LLMProvider

    def base(host):
        return LLMConfig(provider=LLMProvider.LM_STUDIO, host=host,
                         model="x").api_base_url

    assert base("http://localhost:1234/v1") == "http://localhost:1234/v1"
    assert base("http://localhost:1234/v1/") == "http://localhost:1234/v1"
    assert base("localhost:1234/v1") == "http://localhost:1234/v1"
    assert base("gpu-box.lan/v1") == "http://gpu-box.lan:1234/v1"
    assert base("http://gpu-box.lan:1234/V1") == "http://gpu-box.lan:1234/v1"


def test_ollama_host_is_left_alone():
    """Ollama is addressed without /v1 by default, but its OpenAI-compatible
    endpoint exists, so the host must not be rewritten either way."""
    from config import LLMConfig, LLMProvider

    def base(host):
        return LLMConfig(provider=LLMProvider.OLLAMA, host=host, model="x").api_base_url

    assert base("http://localhost:11434") == "http://localhost:11434"
    assert base("http://localhost:11434/v1") == "http://localhost:11434/v1"


def test_config_defaults_present():
    cfg = get_config()
    assert cfg.hotkey.voice
    assert cfg.hotkey.voice_num
    assert cfg.hotkey.live
    assert cfg.stt.model


def test_runtime_save_is_visible_to_reload(env_file):
    """
    Regression: the backend calls load_dotenv() at import, so .env values land
    in os.environ and OS variables win over the file in pydantic-settings.
    save_config() must mirror the new values, otherwise a settings change
    saved at runtime is silently ignored until the next restart.
    """
    os.environ["STT_MODEL"] = "large-v3-turbo"
    os.environ["HOTKEY_LIVE"] = "Ctrl+Shift+L"
    assert get_config().stt.model == "large-v3-turbo"
    save_config(stt_model="small", hotkey_live="F12", env_path=env_file)
    assert reload_config().stt.model == "small"
    assert reload_config().hotkey.live == "F12"