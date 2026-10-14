"""
Wake phrase matching - pure logic, no microphone and no models needed.
"""

import pytest

from src.wake_word import normalize_phrase, phrase_detected, phrase_score


def test_detect_phrase_language():
    from src.wake_word import detect_phrase_language

    assert detect_phrase_language("ассистент") == "ru"
    assert detect_phrase_language("Эй, ассистент") == "ru"
    assert detect_phrase_language("помощник") == "ru"
    assert detect_phrase_language("assistant") == "en"
    assert detect_phrase_language("") == "en"


def test_detector_picks_language_from_phrase():
    from src.wake_word import WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None
    )
    assert d.language == "ru"

    d2 = WakeWordDetector(
        phrase="assistant", model_path="unused", on_detect=lambda t: None
    )
    assert d2.language == "en"


def test_trigger_fires_only_on_the_phrase():
    """The match -> callback path, with audio and models stubbed out."""
    from src.wake_word import WakeWordDetector

    fired = []
    d = WakeWordDetector(
        phrase="ассистент",
        model_path="unused",
        on_detect=fired.append,
        cooldown=5.0,
        threshold=0.82,
    )

    d._maybe_trigger("сегодня хорошая погода", 100.0)
    d._maybe_trigger("", 100.0)
    assert fired == []

    d._maybe_trigger("ассистент открой блокнот", 200.0)
    assert len(fired) == 1
    assert "ассистент" in fired[0]

    # Cooldown suppresses an immediate repeat
    d._maybe_trigger("ассистент", 202.0)
    assert len(fired) == 1
    # ... but not once it expires
    d._maybe_trigger("ассистент", 206.0)
    assert len(fired) == 2


def test_callback_failure_does_not_kill_the_loop():
    from src.wake_word import WakeWordDetector

    def boom(_text):
        raise RuntimeError("frontend gone")

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=boom, cooldown=0.0
    )
    d._maybe_trigger("ассистент", 100.0)   # must not raise
    d._maybe_trigger("ассистент", 101.0)   # still keeps working


def test_normalize_strips_case_and_punctuation():
    assert normalize_phrase("Ассистент, помоги!") == "ассистент помоги"
    assert normalize_phrase("  Эй,   АССИСТЕНТ  ") == "эй ассистент"
    assert normalize_phrase("") == ""
    assert normalize_phrase("!!! ,,, ") == ""


def test_whole_word_match_scores_one():
    assert phrase_score("Ассистент, открой блокнот", "ассистент") == 1.0
    assert phrase_score("Эй, ассистент!", "ассистент") == 1.0
    assert phrase_score("assistant open notepad", "ассистент") == 0.0


def test_substring_is_not_enough():
    """'станция' must not fire for the phrase 'станция'? it must, but
    'ссистент' inside 'ассистент' - a glued fragment must not count as a
    different word."""
    assert phrase_score("ассистент", "станция") < 0.82
    # "ассист" is a fragment of "ассистент", not the whole word
    assert phrase_detected("ассистент", "ассист", threshold=0.82) is False


def test_multi_word_phrase():
    assert phrase_score("Эй ассистент открой блокнот", "эй ассистент") == 1.0
    assert phrase_score("Ну привет ассистент", "эй ассистент") < 0.82


def test_fuzzy_absorbs_small_asr_mistakes():
    """A tiny model writes 'асистент' / 'асистент' - must still match."""
    assert phrase_detected("асистент", "ассистент", threshold=0.82) is True
    assert phrase_detected("асистент", "ассистент", threshold=0.95) is False


def test_unrelated_speech_does_not_match():
    assert phrase_detected("сегодня хорошая погода", "ассистент") is False
    assert phrase_detected("открой блокнот", "ассистент") is False
    assert phrase_detected("", "ассистент") is False
    assert phrase_detected("ассистент", "") is False


def test_empty_phrase_never_matches():
    assert phrase_score("ассистент", "") == 0.0
    assert phrase_score("", "") == 0.0
    assert phrase_detected("ассистент", "  ") is False


def test_threshold_is_respected():
    """A borderline match should flip depending on the configured threshold."""
    transcript = "асистент"          # one vowel off - a realistic tiny-ASR slip
    score = phrase_score(transcript, "ассистент")
    assert 0.5 < score < 1.0        # genuinely borderline, not a clear miss
    assert phrase_detected(transcript, "ассистент", threshold=0.5) is True
    assert phrase_detected(transcript, "ассистент", threshold=0.99) is False


def test_letters_spaced_out_do_not_match():
    """Splitting the word into letters is not a match - the phrase is a word."""
    assert phrase_detected("а с и с и с т е н т", "ассистент") is False


def test_phrase_at_end_and_middle():
    assert phrase_detected("слушай ассистент", "ассистент") is True
    assert phrase_detected("ассистент слушай", "ассистент") is True
    assert phrase_detected("слушай ассистент пожалуйста", "ассистент") is True


def test_english_phrase_works_too():
    assert phrase_detected("Assistant, open notepad", "assistant") is True
    assert phrase_detected("open notepad", "assistant") is False


def test_score_is_bounded():
    for t in ("ассистент", "x" * 200, "ассист ассист"):
        s = phrase_score(t, "ассистент")
        assert 0.0 <= s <= 1.0


def test_config_validation(tmp_path, monkeypatch):
    from config import get_config, reload_config

    monkeypatch.setenv("WAKE_ENABLED", "true")
    monkeypatch.setenv("WAKE_PHRASE", "ассистент")
    monkeypatch.setenv("WAKE_MODEL", "tiny")
    monkeypatch.setenv("WAKE_COOLDOWN", "7")
    get_config.cache_clear()
    cfg = reload_config().wake
    assert cfg.enabled is True
    assert cfg.phrase == "ассистент"
    assert cfg.model == "tiny"
    assert cfg.cooldown == 7.0


def test_wake_is_off_by_default():
    """A fresh clone must never open the microphone unasked.

    Checks the field default, not the loaded value: the developer's own .env
    may well have it enabled for testing.
    """
    from config import WakeWordConfig

    fields = WakeWordConfig.model_fields
    assert fields["enabled"].default is False
    assert fields["phrase"].default == ""
    assert fields["model"].default == "tiny"


def test_bad_wake_values_are_rejected():
    from config import WakeWordConfig

    with pytest.raises(Exception):
        WakeWordConfig(model="large")          # only tiny/base supported
    with pytest.raises(Exception):
        WakeWordConfig(phrase="x" * 100)       # max 64 chars
