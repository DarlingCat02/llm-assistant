"""
Tests for Sprint 1 features:
- TTS Volume slider & configuration
- Stop TTS hotkey (Ctrl+Shift+X / Escape)
- Voice cues ("Слушаю") and sound cues (wake/stop)
"""

import sys
from pathlib import Path
import pytest

# Add project root to sys.path
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from config import Config, TTSConfig, HotkeyConfig, WakeWordConfig, save_config, reload_config, get_config


def test_config_sprint1_fields(tmp_path):
    env_file = tmp_path / ".env.test"
    
    # Save config with custom sprint 1 settings
    save_config(
        tts_volume=85,
        hotkey_stop_tts="Ctrl+Alt+S",
        wake_cue_mode="sound",
        wake_cue_stop=False,
        env_path=env_file,
    )
    
    # Verify .env contents
    content = env_file.read_text(encoding="utf-8")
    assert "TTS_VOLUME=85" in content
    assert "HOTKEY_STOP_TTS=Ctrl+Alt+S" in content
    assert "WAKE_CUE_WAKE_MODE=sound" in content
    assert "WAKE_CUE_STOP_ENABLED=false" in content


def test_cue_voice_id_helper():
    from backend.main import _get_cue_voice_id
    
    # Instruct voice
    id1 = _get_cue_voice_id(mode="instruct", instruct="female")
    assert id1 == "instruct_female"
    
    id2 = _get_cue_voice_id(mode="instruct", instruct="female, russian")
    assert "female" in id2 and "russian" in id2
    
    # Cloned voice
    id3 = _get_cue_voice_id(mode="clone", ref_audio="voices/my_voice_sample.wav")
    assert id3 == "clone_my_voice_sample"


def test_sounds_exist():
    sounds_dir = root_dir / "sounds"
    wake_wav = sounds_dir / "wake.wav"
    stop_wav = sounds_dir / "stop.wav"
    readme = sounds_dir / "README.txt"
    
    assert wake_wav.is_file(), "sounds/wake.wav missing"
    assert stop_wav.is_file(), "sounds/stop.wav missing"
    assert readme.is_file(), "sounds/README.txt missing"
    assert wake_wav.stat().st_size > 1000
    assert stop_wav.stat().st_size > 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
