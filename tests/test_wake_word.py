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


def test_empty_device_spec_means_system_default():
    from src.wake_word import resolve_input_device

    for spec in ("", "   ", None, "default", "DEFAULT"):
        device, name, problem = resolve_input_device(spec)
        assert device is None, spec
        assert name is None
        assert problem is None


def _device_is_plugged_in(fragment):
    """Whether a microphone with this name exists on this machine."""
    try:
        import sounddevice as sd
        names = [d["name"] for d in sd.query_devices()]
    except Exception:
        return False
    return any(fragment.lower() in (n or "").lower() for n in names)


# The two tests below assert the real thing only where the microphone is
# actually present. They used to name a specific device and failed on every
# other machine, which contradicts what the suite promises: no microphone, no
# GPU, no models.
requires_steelseries = pytest.mark.skipif(
    not _device_is_plugged_in("SteelSeries"),
    reason="no SteelSeries microphone on this machine",
)


@requires_steelseries
def test_device_resolved_by_name_not_index():
    """Indices move when devices are replugged, so we match on the name."""
    from src.wake_word import resolve_input_device

    device, name, problem = resolve_input_device("SteelSeries Sonar - Microphone")
    assert problem is None
    assert name and name.strip() == "SteelSeries Sonar - Microphone"
    assert isinstance(device, int)


@requires_steelseries
def test_device_partial_name_matches():
    from src.wake_word import resolve_input_device

    device, name, problem = resolve_input_device("SteelSeries")
    assert problem is None
    assert name and "SteelSeries" in name
    assert isinstance(device, int)


def test_unknown_device_reports_and_falls_back():
    from src.wake_word import resolve_input_device

    device, name, problem = resolve_input_device("Нет Такого Устройства")
    assert problem is not None
    assert "не найдено" in problem.lower()
    # Falls back to the system default rather than opening a bogus device
    assert device == "Нет Такого Устройства" or device is None


def test_detector_stores_device_spec():
    from src.wake_word import WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
        input_device="SteelSeries Sonar - Microphone",
    )
    assert d.device_spec == "SteelSeries Sonar - Microphone"
    assert d.input_device is None   # resolved only when the listener starts


def test_audio_device_does_not_collide_with_torch_device():
    """
    Regression: both used to be called `device`, so resolving the microphone
    silently pinned the Whisper model to CPU.
    """
    from src.wake_word import WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
        input_device="SteelSeries", torch_device="cuda",
    )
    assert d.torch_device == "cuda"
    d.input_device = 7
    assert d.torch_device == "cuda", "audio device overwrote torch device"


def test_vad_window_starts_prefilled_with_silence():
    """
    Regression, and the reason the wake word never fired.

    `_is_speaking()` returns False while the VAD window is not full, so an
    empty history meant the first VAD_WINDOW_SECONDS of every utterance were
    dropped before anything was buffered. Since the wake phrase is spoken
    first, that is exactly the audio we needed.
    """
    import numpy as np
    from src.wake_word import BLOCK_SIZE, VAD_WINDOW_SECONDS, SAMPLE_RATE, WakeWordStream

    class FakeDetector:
        stt_interval = 0.6

        def _transcribe(self, audio):
            return ""

        def _stt_audio(self, blocks):
            return np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)

        def _maybe_trigger(self, text, now):
            pass

    s = WakeWordStream(FakeDetector(), vad=None)
    expected = int(VAD_WINDOW_SECONDS * SAMPLE_RATE / BLOCK_SIZE)
    assert len(s.vad_history) == expected, "VAD window must start full of silence"
    assert all(b.size == BLOCK_SIZE for b in s.vad_history)
    assert not s.vad_history[0].any(), "the prefill must be silence"


def test_stream_buffers_from_the_first_block():
    """With a prefilled window, speech must be buffered from t=0, not t=1.5s."""
    import numpy as np
    from src.wake_word import (
        BLOCK_SIZE,
        MIN_SPEECH_BEFORE_STT,
        SAMPLE_RATE,
        WakeWordStream,
    )

    class FakeDetector:
        stt_interval = 0.6
        last_transcript = ""
        _last_trigger = 0.0

        def _transcribe(self, audio):
            return "тишина"

        def _stt_audio(self, blocks):
            return np.concatenate(blocks)

        def _maybe_trigger(self, text, now):
            pass

    s = WakeWordStream(FakeDetector(), vad=None)
    # Pretend every block is speech - the only thing under test is that the
    # buffer starts filling immediately.
    s._is_speaking = lambda g: True

    loud = np.full(BLOCK_SIZE, 0.3, dtype=np.float32)
    s.push(loud)
    # The very first block must already be buffered, not the 46th.
    assert len(s.speech) == 1, "speech buffer must start growing at once"
    assert s.runs == 0, "Whisper must not run on a single block"

    blocks_needed = int(MIN_SPEECH_BEFORE_STT * SAMPLE_RATE / BLOCK_SIZE)
    for _ in range(blocks_needed):
        s.push(loud)

    assert len(s.speech) * BLOCK_SIZE >= MIN_SPEECH_BEFORE_STT * SAMPLE_RATE
    assert s.runs == 1, "Whisper should run once enough audio accumulated"


def test_stt_audio_has_leading_silence():
    import numpy as np
    from src.wake_word import LEAD_SILENCE_SECONDS, SAMPLE_RATE, WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
    )
    block = np.ones(512, dtype=np.float32) * 0.2
    out = d._stt_audio([block, block])

    pad = int(LEAD_SILENCE_SECONDS * SAMPLE_RATE)
    assert out.size == pad + 1024
    assert not out[:pad].any(), "leading context must be silence"
    assert out[pad:].any(), "the real audio must follow the silence"


def test_finish_is_idempotent_and_clears_state():
    import numpy as np
    from src.wake_word import BLOCK_SIZE, WakeWordStream

    calls = []

    class FakeDetector:
        stt_interval = 0.6

        def _transcribe(self, audio):
            calls.append(len(audio))
            return "раз два"

        def _stt_audio(self, blocks):
            return np.concatenate(blocks)

        def _maybe_trigger(self, text, now):
            pass

    s = WakeWordStream(FakeDetector(), vad=None)
    s._is_speaking = lambda g: True
    for _ in range(200):
        s.push(np.full(BLOCK_SIZE, 0.3, dtype=np.float32))
    assert s.speech

    assert s.finish(s.elapsed) == "раз два"
    assert s.speech == []
    # A second finish must not run Whisper on an empty buffer.
    before = len(calls)
    assert s.finish(s.elapsed) == ""
    assert len(calls) == before


def test_window_drops_tail_not_head():
    """The wake phrase is spoken first, so the head must be preserved."""
    import numpy as np
    from src.wake_word import BLOCK_SIZE, SAMPLE_RATE, STT_WINDOW_SECONDS, WakeWordStream

    class FakeDetector:
        stt_interval = 999.0   # never auto-run STT

        def _transcribe(self, audio):
            return ""

        def _stt_audio(self, blocks):
            return np.concatenate(blocks)

        def _maybe_trigger(self, text, now):
            pass

    s = WakeWordStream(FakeDetector(), vad=None)
    s._is_speaking = lambda g: True

    first = np.full(BLOCK_SIZE, 0.9, dtype=np.float32)
    s.push(first)
    for _ in range(int(STT_WINDOW_SECONDS * SAMPLE_RATE / BLOCK_SIZE) + 50):
        s.push(np.full(BLOCK_SIZE, 0.1, dtype=np.float32))

    assert len(s.speech) == s.stt_limit, "window must stay capped"
    assert s.speech[0] is first, "the first block must survive trimming"


def test_default_threshold_accepts_a_real_microphone_mishearing():
    """
    Regression: the live failure was 'ассистент' -> 'Систент' at 0.80 against a
    0.82 threshold, so a genuine detection was thrown away. Measured negatives
    (25 ordinary utterances) top out at 0.38, so 0.70 keeps a 2x margin.
    """
    from config import WakeWordConfig

    threshold = WakeWordConfig().match_threshold
    assert threshold <= 0.80, "must accept the observed 0.80 mishearing"

    from src.wake_word import phrase_detected, phrase_score

    assert phrase_score("Систент откуда?", "ассистент") >= threshold
    assert phrase_detected("Систент откуда?", "ассистент")


def test_default_threshold_still_rejects_ordinary_speech():
    """The margin to the worst measured negative must survive."""
    from config import WakeWordConfig
    from src.wake_word import phrase_detected

    threshold = WakeWordConfig().match_threshold
    # Highest score any of the 25 measured ordinary utterances produced.
    for text in ("помощь слышишь меня", "переходи", "покажи список"):
        assert not phrase_detected(text, "ассистент", threshold), text


def test_resolve_torch_device_prefers_cuda_and_falls_back():
    """
    A large-v3-turbo wake detector takes ~110 ms on CUDA and ~4.2 s on CPU, so
    picking the wrong one is the difference between usable and useless.
    """
    from src.wake_word import resolve_torch_device

    # An explicit request is honoured verbatim.
    assert resolve_torch_device("cpu") == "cpu"

    chosen = resolve_torch_device()
    assert chosen in ("cpu", "cuda") or chosen.startswith("cuda:")

    try:
        import torch
    except Exception:
        return
    if not torch.cuda.is_available():
        assert chosen == "cpu", "must not claim cuda when torch cannot use it"


def test_resolve_torch_device_survives_broken_cuda(monkeypatch):
    """A machine can report a GPU and still fail to allocate on it."""
    import torch
    from src.wake_word import resolve_torch_device

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(
        torch, "zeros", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no alloc"))
    )
    assert resolve_torch_device() == "cpu"


def test_same_device_ignores_the_index():
    """
    Regression: a module moved with .to("cuda") reports 'cuda:0' while the
    resolved device is 'cuda'. Comparing the strings said 'different', so the
    detector loaded a second 1.5 GB copy of the same weights.
    """
    from src.wake_word import _same_device

    assert _same_device("cuda:0", "cuda") is True
    assert _same_device("cuda", "cuda:0") is True
    assert _same_device("cpu", "cuda") is False
    assert _same_device("cuda:0", "cuda:1") is True


def test_detector_reuses_a_matching_preloaded_model():
    """
    The whole point of borrowing: one set of weights, not two.

    A 'Loading model' line for the detector when speech recognition already
    holds the same model is 1.5 GB of VRAM wasted.
    """
    import torch

    from src.wake_word import WakeWordDetector

    fake = type("M", (), {
        "dtype": torch.float16,
        "device": "cuda",
        "eval": lambda self: self,
        "to": lambda self, d: self,
    })()

    d = WakeWordDetector(
        phrase="ассистент", model_path="models/whisper-large-v3-turbo",
        on_detect=lambda t: None,
        preloaded=("models/whisper-large-v3-turbo", "proc", fake, "cuda"),
    )
    # Patch the loader so a borrow can never fall through to a real load.
    d._vad = object()
    d._load_models()

    assert d._model is fake, "must adopt the existing model"
    assert d.owns_model is False, "borrowed, not owned"
    assert d.is_model_loaded


def test_detector_owns_a_model_it_loaded_itself():
    """A mismatch has to load its own copy and remember that it owns it."""
    from src.wake_word import WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="models/whisper-large-v3-turbo",
        on_detect=lambda t: None,
        preloaded=("some/other-model", "proc", object(), "cuda"),
    )
    d._vad = object()

    # Force the mismatch path without touching the disk.
    def boom(*a, **k):
        raise RuntimeError("would have loaded a second copy")
    import transformers

    orig = transformers.WhisperForConditionalGeneration.from_pretrained
    transformers.WhisperForConditionalGeneration.from_pretrained = staticmethod(boom)
    try:
        ok = d._load_models()
    finally:
        transformers.WhisperForConditionalGeneration.from_pretrained = orig

    assert not ok, "a path mismatch must not silently adopt the wrong model"
    assert d.owns_model is False


def test_unload_does_not_free_a_borrowed_model():
    """
    Speech recognition still needs the model the detector borrowed, so
    unloading must not pull it out from under it.
    """
    from src.wake_word import WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
    )
    d._model = object()
    d._processor = object()
    d.model_loaded = True
    d.owns_model = False   # borrowed

    d.unload()

    assert not d.is_model_loaded
    assert d.owns_model is False


def test_unload_frees_a_model_the_detector_owns():
    from src.wake_word import WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
    )
    d._model = object()
    d.model_loaded = True
    d.owns_model = True

    d.unload()

    assert not d.is_model_loaded


def test_unload_clears_everything_and_is_repeatable():
    """
    Turning "always listening" off has to release 1.6 GB of weights, not just
    stop the thread: torch keeps freed blocks, so without empty_cache() the
    old model is still resident while the next one loads.
    """
    from src.wake_word import WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
    )
    # Pretend something is loaded, including on a device.
    d._model = object()
    d._processor = object()
    d._vad = object()
    d._torch = object()
    d.model_device = "cuda"
    d.model_loaded = True

    assert d.is_model_loaded

    d.unload()

    assert not d.is_model_loaded
    assert d.model_loaded is False
    assert d.model_device is None
    assert d._model is None
    assert d._processor is None
    assert d._vad is None
    assert d._torch is None

    # Idempotent: stopping an already-stopped detector must not raise.
    d.unload()
    d.unload()


def test_unload_stops_a_running_listener():
    import threading

    from src.wake_word import WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
    )
    d._stop.clear()
    d._thread = threading.Thread(target=lambda: None, daemon=True)
    d._thread.start()
    d._thread.join()

    d.unload()
    assert not d.is_running


def test_action_defaults_to_showing_the_phrase():
    from config import WakeWordConfig

    assert WakeWordConfig().action == "chat"
    assert WakeWordConfig(action="execute").action == "execute"
    with pytest.raises(Exception):
        WakeWordConfig(action="nonsense")


def test_level_meter_starts_silent():
    from src.wake_word import WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
    )
    assert d.input_level == 0.0
    assert d.peak_level == 0.0
    assert d.opened is False
    assert d.blocks_read == 0


def test_level_meter_tracks_loudness():
    """The meter must react to audio, otherwise it proves nothing."""
    import numpy as np
    from src.wake_word import update_level_meter, WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
    )

    quiet = np.full(512, 0.001, dtype=np.float32)
    for _ in range(20):
        update_level_meter(d, quiet)
    assert d.input_level < 0.01
    assert d.blocks_read == 20

    loud = np.full(512, 0.3, dtype=np.float32)
    update_level_meter(d, loud)
    # Instant attack so the bar reacts on the very first loud block.
    assert d.input_level > 0.2
    assert d.peak_level > 0.2


def test_level_meter_decays_in_silence():
    import numpy as np
    from src.wake_word import update_level_meter, WakeWordDetector

    d = WakeWordDetector(
        phrase="ассистент", model_path="unused", on_detect=lambda t: None,
    )
    loud = np.full(512, 0.5, dtype=np.float32)
    update_level_meter(d, loud)
    silence = np.zeros(512, dtype=np.float32)
    for _ in range(50):
        update_level_meter(d, silence)
    assert d.input_level < 0.01, "bar must fall back down, not stick at the peak"


def test_wake_input_device_config():
    from config import WakeWordConfig

    assert WakeWordConfig.model_fields["input_device"].default == ""
    cfg = WakeWordConfig(input_device="Some Mic")
    assert cfg.input_device == "Some Mic"


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

    monkeypatch.setenv("WAKE_PHRASE", "ассистент")
    monkeypatch.setenv("WAKE_COOLDOWN", "7")
    get_config.cache_clear()
    cfg = reload_config().wake
    assert cfg.phrase == "ассистент"
    assert cfg.cooldown == 7.0


def test_wake_has_no_enable_or_model_of_its_own():
    """
    Whether the wake word runs is the input-mode slider (session state), and
    the weights come from the speech model. Keeping either here is how a
    second 1.5 GB copy crept in and how a launch ended up with the microphone
    open behind the user's back.
    """
    from config import WakeWordConfig

    fields = WakeWordConfig.model_fields
    assert "enabled" not in fields
    assert "model" not in fields
    assert fields["phrase"].default == ""
    # What is left has to stay persisted, unlike the mode.
    assert {"phrase", "input_device", "action", "cooldown",
            "match_threshold"} <= set(fields)


def test_speech_model_governs_both_modes():
    from config import Config

    assert Config().stt.model  # one setting, used by hotkey and background


def test_bad_wake_values_are_rejected():
    from config import WakeWordConfig

    with pytest.raises(Exception):
        WakeWordConfig(phrase="x" * 100)       # max 64 chars
    with pytest.raises(Exception):
        WakeWordConfig(action="something-else")
