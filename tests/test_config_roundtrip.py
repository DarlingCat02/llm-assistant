"""
Config round-trip: save_config() must persist new keys without wiping others.
"""

import config as cfg_mod
from config import get_config, save_config, reload_config


def _with_env(fn):
    env_path = cfg_mod.Path(cfg_mod.__file__).parent / ".env"
    backup = env_path.read_text(encoding="utf-8") if env_path.exists() else None
    try:
        return fn(env_path)
    finally:
        if backup is not None:
            env_path.write_text(backup, encoding="utf-8")
        else:
            env_path.unlink(missing_ok=True)
        get_config.cache_clear()


def test_stt_model_saved():
    def run(env_path):
        save_config(stt_model="small")
        raw = env_path.read_text(encoding="utf-8")
        assert "STT_MODEL=small" in raw
    _with_env(run)


def test_hotkeys_saved():
    def run(env_path):
        save_config(hotkey_voice="Alt+F9", hotkey_voice_num="Ctrl+Num3", hotkey_live="F12")
        raw = env_path.read_text(encoding="utf-8")
        assert "HOTKEY_VOICE=Alt+F9" in raw
        assert "HOTKEY_VOICE_NUM=Ctrl+Num3" in raw
        assert "HOTKEY_LIVE=F12" in raw
    _with_env(run)


def test_empty_values_do_not_overwrite():
    """An empty string must not wipe an existing value (partial updates)."""
    def run(env_path):
        env_path.write_text("HOTKEY_VOICE=Ctrl+Shift+V\n", encoding="utf-8")
        save_config(hotkey_live="F12")
        raw = env_path.read_text(encoding="utf-8")
        assert "HOTKEY_VOICE=Ctrl+Shift+V" in raw
        assert "HOTKEY_LIVE=F12" in raw
    _with_env(run)


def test_other_keys_survive_partial_update():
    def run(env_path):
        env_path.write_text("LLM_MODEL=qwen\nPERSONALITY_RU=стиль\nSTT_MODEL=small\n",
                            encoding="utf-8")
        save_config(hotkey_live="F12")
        raw = env_path.read_text(encoding="utf-8")
        for expected in ("LLM_MODEL=qwen", "PERSONALITY_RU=стиль", "STT_MODEL=small",
                         "HOTKEY_LIVE=F12"):
            assert expected in raw
    _with_env(run)


def test_config_defaults_present():
    cfg = get_config()
    assert cfg.hotkey.voice
    assert cfg.hotkey.voice_num
    assert cfg.hotkey.live
    assert cfg.stt.model


def test_runtime_save_is_visible_to_reload():
    """
    Regression: the backend calls load_dotenv() at import, so .env values land
    in os.environ and OS variables win over the file in pydantic-settings.
    save_config() must mirror the new values, otherwise a settings change
    saved at runtime is silently ignored until the next restart.
    """
    import os

    def run(env_path):
        os.environ["STT_MODEL"] = "large-v3-turbo"
        os.environ["HOTKEY_LIVE"] = "Ctrl+Shift+L"
        try:
            assert get_config().stt.model == "large-v3-turbo"
            save_config(stt_model="small", hotkey_live="F12")
            assert reload_config().stt.model == "small"
            assert reload_config().hotkey.live == "F12"
        finally:
            os.environ.pop("STT_MODEL", None)
            os.environ.pop("HOTKEY_LIVE", None)

    _with_env(run)