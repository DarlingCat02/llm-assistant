"""
Wake word - activate the assistant by saying a configurable phrase.

Design notes
------------
The phrase is whatever the user types in the settings (for example just the
assistant's name), so a fixed keyword-spotting model is not usable here: those
only know a handful of baked-in English phrases. Instead detection is done with
a small Whisper model, gated by a VAD so the cost is only paid while somebody
is actually talking:

    microphone (always open)
      -> Silero VAD            ~4% of one core, constant
      -> Whisper tiny, int8    ~110 ms per inference, only while speech is
                                detected (~19% of one core)
      -> phrase match          cheap string comparison
      -> callback              the app starts the normal push-to-talk pipeline

The wake model is intentionally separate from `stt_engine`: the heavy
large-v3-turbo model used for real commands is never loaded here, and nothing
in this module touches STT/TTS behaviour.

The microphone is only opened when the feature is explicitly enabled, so a
fresh install never records anything.
"""

import logging
import re
import threading
import time
from difflib import SequenceMatcher
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
BLOCK_SIZE = 512          # Silero VAD v5 expects exactly 512 samples @16 kHz
VAD_WINDOW_SECONDS = 1.5  # how much audio the VAD looks at per decision
STT_INTERVAL = 0.6        # seconds between Whisper runs while speech is active
STT_WINDOW_SECONDS = 2.5  # audio handed to Whisper (padded to 30 s internally)
PRE_ROLL_SECONDS = 0.6    # kept so a phrase is not clipped at its start
SPEECH_HANG_SECONDS = 0.8  # keep considering it speech this long after VAD says no

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_phrase(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    text = _PUNCTUATION.sub(" ", (text or "").lower())
    return _WHITESPACE.sub(" ", text).strip()


_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def detect_phrase_language(phrase: str) -> str:
    """
    Which Whisper decoding language to use for this phrase.

    Whisper defaults to English, which turns a Russian phrase into noise (and
    also makes the model hallucinate English from room noise). The phrase the
    user typed is the best available hint about what they will actually say.
    """
    if _CYRILLIC.search(phrase or ""):
        return "ru"
    return "en"


def phrase_score(transcript: str, phrase: str) -> float:
    """
    How well `transcript` contains `phrase`, from 0.0 to 1.0.

    A whole-word hit scores 1.0 so the usual "ассистент, открой блокнот" matches
    immediately. Otherwise the best fuzzy score over the transcript's word
    windows is used, which absorbs the small ASR mistakes that are normal for a
    very small model ("асистент" vs "ассистент").
    """
    norm_phrase = normalize_phrase(phrase)
    norm_text = normalize_phrase(transcript)
    if not norm_phrase or not norm_text:
        return 0.0

    phrase_words = norm_phrase.split()
    text_words = norm_text.split()

    # Exact whole-word match anywhere in the transcript
    if " ".join(phrase_words) in text_words:
        return 1.0

    # Same, but allowing the phrase to be glued to adjacent words
    padded = f" {' '.join(text_words)} "
    if f" {' '.join(phrase_words)} " in padded:
        return 1.0

    # Fuzzy: slide a window the length of the phrase over the transcript
    span = len(phrase_words)
    best = 0.0
    for i in range(0, max(1, len(text_words) - span + 1)):
        window = " ".join(text_words[i:i + span])
        if not window:
            continue
        best = max(best, SequenceMatcher(None, norm_phrase, window).ratio())
        if best >= 0.99:
            break

    # A single-word phrase can also match a close word on its own
    if span == 1 and best < 0.85:
        for w in text_words:
            best = max(best, SequenceMatcher(None, norm_phrase, w).ratio())
    return best


def phrase_detected(transcript: str, phrase: str, threshold: float = 0.82) -> bool:
    """True when the transcript contains the wake phrase."""
    return phrase_score(transcript, phrase) >= threshold


class WakeWordDetector:
    """
    Always-listening wake-word detector.

    Runs its own capture thread. Everything audio related is injectable so the
    detection logic can be tested without a microphone.
    """

    def __init__(
        self,
        phrase: str,
        model_path: str,
        on_detect: Callable[[str], None],
        cooldown: float = 5.0,
        threshold: float = 0.82,
        stt_interval: float = STT_INTERVAL,
        device: Optional[str] = None,
    ) -> None:
        self.phrase = phrase
        self.language = detect_phrase_language(phrase)
        self.model_path = model_path
        self.on_detect = on_detect
        self.cooldown = cooldown
        self.threshold = threshold
        self.stt_interval = stt_interval
        self.device = device

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._vad = None
        self._processor = None
        self._model = None
        self._last_trigger = 0.0
        self.last_transcript = ""
        self.error: Optional[str] = None

    # ---------- lifecycle ----------

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start listening. Returns False and sets .error if it cannot run."""
        if self.is_running:
            return True
        if not self.phrase.strip():
            self.error = "Пробуждающая фраза не задана"
            return False
        if not self._load_models():
            return False

        self._stop.clear()
        self.error = None
        self._thread = threading.Thread(
            target=self._run, name="wake-word", daemon=True
        )
        self._thread.start()
        logger.info(f"Wake word listening for '{self.phrase}'")
        return True

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
        self._thread = None
        logger.info("Wake word stopped")

    # ---------- model loading ----------

    def _load_models(self) -> bool:
        try:
            import torch
            from silero_vad import load_silero_vad
            from transformers import (
                WhisperForConditionalGeneration,
                WhisperProcessor,
            )
            import transformers

            # Whisper.generate() emits a wall of warnings on every call
            # (max_new_tokens vs max_length, forced_decoder_ids, ...). This
            # runs in a background loop, so they would drown the app terminal.
            transformers.logging.set_verbosity_error()
            transformers.logging.disable_progress_bar()

            if self._vad is None:
                self._vad = load_silero_vad()

            if self._model is None:
                self._processor = WhisperProcessor.from_pretrained(
                    self.model_path, local_files_only=True
                )
                model = WhisperForConditionalGeneration.from_pretrained(
                    self.model_path,
                    local_files_only=True,
                    torch_dtype=torch.float32,
                )
                if self.device:
                    model.to(self.device)
                model.eval()
                self._model = model
                self._torch = torch
            return True
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            logger.warning(f"Wake word disabled, models unavailable: {e}")
            return False

    # ---------- audio loop ----------

    def _run(self) -> None:
        try:
            import sounddevice as sd
        except Exception as e:
            self.error = f"sounddevice: {e}"
            logger.warning(f"Wake word disabled, no audio backend: {e}")
            return

        from silero_vad import get_speech_timestamps

        vad_history: list[np.ndarray] = []
        speech_window: list[np.ndarray] = []
        last_speech_at = 0.0
        last_stt_at = 0.0
        pre_roll: list[np.ndarray] = []
        pre_roll_max = max(1, int(PRE_ROLL_SECONDS * SAMPLE_RATE / BLOCK_SIZE))
        vad_window_max = max(1, int(VAD_WINDOW_SECONDS * SAMPLE_RATE / BLOCK_SIZE))

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                device=None,
            ) as stream:
                logger.info("Wake word microphone open")
                while not self._stop.is_set():
                    data, _ = stream.read(BLOCK_SIZE)
                    block = np.asarray(data, dtype=np.float32).flatten()
                    if block.size == 0:
                        continue

                    pre_roll.append(block)
                    if len(pre_roll) > pre_roll_max:
                        pre_roll.pop(0)

                    # --- VAD: only ask Whisper when somebody is talking
                    vad_history.append(block)
                    if len(vad_history) > vad_window_max:
                        vad_history.pop(0)

                    now = time.monotonic()
                    speaking = False
                    if len(vad_history) >= vad_window_max:
                        probe = np.concatenate(vad_history)
                        try:
                            stamps = get_speech_timestamps(
                                probe, self._vad, sampling_rate=SAMPLE_RATE
                            )
                            # speech still in progress?
                            if stamps and stamps[-1]["end"] >= len(probe) - BLOCK_SIZE:
                                speaking = True
                            elif stamps and (len(probe) - stamps[-1]["end"]) < int(
                                0.4 * SAMPLE_RATE
                            ):
                                speaking = True
                        except Exception:
                            speaking = False

                    if speaking:
                        last_speech_at = now
                        if not speech_window:
                            speech_window = list(pre_roll)
                        speech_window.append(block)
                        limit = int(STT_WINDOW_SECONDS * SAMPLE_RATE / BLOCK_SIZE)
                        while len(speech_window) > limit:
                            speech_window.pop(0)

                        if now - last_stt_at >= self.stt_interval:
                            last_stt_at = now
                            text = self._transcribe(np.concatenate(speech_window))
                            self.last_transcript = text
                            self._maybe_trigger(text, now)
                    else:
                        if speech_window and (now - last_speech_at) > SPEECH_HANG_SECONDS:
                            speech_window = []
                            last_stt_at = 0.0
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            logger.warning(f"Wake word listener stopped: {e}")

    def _transcribe(self, audio: np.ndarray) -> str:
        try:
            torch = self._torch
            inputs = self._processor(
                audio, sampling_rate=SAMPLE_RATE, return_tensors="pt"
            )
            with torch.no_grad():
                ids = self._model.generate(
                    inputs.input_features,
                    max_new_tokens=16,
                    num_beams=1,
                    do_sample=False,
                    language=self.language,
                )
            text = self._processor.batch_decode(ids, skip_special_tokens=True)[0]
            return (text or "").strip()
        except Exception as e:
            logger.debug(f"Wake transcription failed: {e}")
            return ""

    def _maybe_trigger(self, transcript: str, now: float) -> None:
        if not transcript:
            return
        if (now - self._last_trigger) < self.cooldown:
            return
        if not phrase_detected(transcript, self.phrase, self.threshold):
            return
        self._last_trigger = now
        logger.info(f"Wake word detected in: {transcript!r}")
        try:
            self.on_detect(transcript)
        except Exception as e:
            logger.warning(f"Wake word callback failed: {e}")
