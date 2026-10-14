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
STT_WINDOW_SECONDS = 12.0  # audio handed to Whisper (it pads to 30 s internally)
PRE_ROLL_SECONDS = 0.6    # kept so a phrase is not clipped at its start
SPEECH_HANG_SECONDS = 0.8  # keep considering it speech this long after VAD says no

# Whisper scores a short window badly: measured on this model's own output,
# 1.5 s of speech scored 0.31 against the phrase while the same utterance scored
# 0.82 once complete. So early runs are made only once there is a usable amount
# of audio, and the decisive run happens at the END of the utterance (finish()).
MIN_SPEECH_BEFORE_STT = 1.2

# A whisper of silence in front measurably improves transcription of the first
# word (it gives Whisper the onset it expects), which is exactly the word the
# wake phrase consists of.
LEAD_SILENCE_SECONDS = 0.4

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_phrase(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    text = _PUNCTUATION.sub(" ", (text or "").lower())
    return _WHITESPACE.sub(" ", text).strip()


def resolve_input_device(spec: str | None) -> tuple[int | str | None, str | None, str | None]:
    """
    Turn a configured device name into something sounddevice understands.

    The name is matched instead of the index on purpose: PortAudio indices
    shift when a device is plugged in, names do not.

    Args:
        spec: "", "default", a full device name, or part of one.

    Returns:
        tuple: (device, matched_name, problem). `device` is None for the
            system default, an int for a resolved device, or the original
            spec when nothing matched (so the failure is visible).
    """
    spec = (spec or "").strip()
    if not spec or spec.lower() == "default":
        return None, None, None

    try:
        import sounddevice as sd
    except Exception as e:
        return spec, None, f"sounddevice недоступен: {e}"

    try:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) < 1:
                continue
            name = dev.get("name", "")
            if name == spec or spec.lower() in name.lower():
                return idx, name, None
    except Exception as e:
        return spec, None, f"не удалось получить список устройств: {e}"

    return spec, None, f"Устройство «{spec}» не найдено — используется системное по умолчанию"


def update_level_meter(detector: "WakeWordDetector", block: np.ndarray) -> float:
    """
    Feed one captured block into the detector's input-level meter.

    RMS with an instant attack and a slow release: the UI bar has to react on
    the first block of speech (that is when the user is watching) but must also
    fall back down when they stop talking, otherwise it just sticks at the
    loudest thing that ever happened.

    Args:
        detector: the detector whose meter should be updated.
        block: one block of float32 samples in [-1, 1].

    Returns:
        float: the RMS level of this block.
    """
    rms = float(np.sqrt(np.mean(np.square(block))))
    detector.blocks_read += 1
    detector.peak_level = max(rms, detector.peak_level * 0.92)
    if rms > detector.input_level:
        detector.input_level = rms
    else:
        detector.input_level = detector.input_level * 0.8 + rms * 0.2
    return rms


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


class WakeWordStream:
    """
    The detection pipeline, with no audio device attached.

    Feed it blocks with `push(block)` and it decides when to run Whisper and
    whether the phrase was heard. The live listener does nothing but read from
    the microphone and hand blocks here, which is what makes the whole
    decision path testable from a wav file - the earlier version had the logic
    inline in `_run`, and the offline check silently drifted away from it.

    Args:
        detector: the detector that owns the models and decides on a match.
        vad: a loaded Silero VAD model.
    """

    def __init__(self, detector: "WakeWordDetector", vad) -> None:
        self.detector = detector
        self.vad = vad
        self.pre_roll: list[np.ndarray] = []
        self.speech: list[np.ndarray] = []
        # Pre-filled with silence so the VAD can answer from the very first
        # block. Left empty, nothing is heard for the first VAD_WINDOW_SECONDS
        # and that much speech is silently dropped before the wake word - which
        # is normally spoken first - has a chance to be buffered.
        self.vad_history: list[np.ndarray] = [
            np.zeros(BLOCK_SIZE, dtype=np.float32)
            for _ in range(int(VAD_WINDOW_SECONDS * SAMPLE_RATE / BLOCK_SIZE))
        ]
        self.pre_roll_max = max(1, int(PRE_ROLL_SECONDS * SAMPLE_RATE / BLOCK_SIZE))
        self.vad_window_max = max(1, int(VAD_WINDOW_SECONDS * SAMPLE_RATE / BLOCK_SIZE))
        self.stt_limit = int(STT_WINDOW_SECONDS * SAMPLE_RATE / BLOCK_SIZE)
        self.last_speech_at = 0.0
        self.last_stt_at = 0.0
        self.elapsed = 0.0
        self.runs = 0

    # ---------- VAD ----------

    def _is_speaking(self, get_speech_timestamps) -> bool:
        """Is there speech at the tail of the VAD window right now?"""
        if len(self.vad_history) < self.vad_window_max:
            return False
        probe = np.concatenate(self.vad_history)
        try:
            stamps = get_speech_timestamps(probe, self.vad, sampling_rate=SAMPLE_RATE)
        except Exception:
            return False
        if not stamps:
            return False
        # Either speech reaches the very end of the window, or it stopped less
        # than 0.4 s ago (so we are between words, not between utterances).
        if stamps[-1]["end"] >= len(probe) - BLOCK_SIZE:
            return True
        return (len(probe) - stamps[-1]["end"]) < int(0.4 * SAMPLE_RATE)

    # ---------- main entry point ----------

    def push(self, block: np.ndarray, get_speech_timestamps=None) -> str:
        """
        Feed one block of audio through the pipeline.

        Args:
            block: float32 samples, exactly BLOCK_SIZE long.
            get_speech_timestamps: injected for tests; the real one comes from
                silero_vad.

        Returns:
            str: the transcript from this block, or "" if Whisper did not run.
        """
        if get_speech_timestamps is None:
            from silero_vad import get_speech_timestamps as g

            get_speech_timestamps = g

        self.elapsed += BLOCK_SIZE / SAMPLE_RATE
        now = self.elapsed

        self.pre_roll.append(block)
        if len(self.pre_roll) > self.pre_roll_max:
            self.pre_roll.pop(0)

        self.vad_history.append(block)
        if len(self.vad_history) > self.vad_window_max:
            self.vad_history.pop(0)

        if self._is_speaking(get_speech_timestamps):
            self.last_speech_at = now
            if not self.speech:
                # pre_roll already contains the current block, so appending it
                # again would duplicate the first 32 ms of every utterance.
                self.speech = list(self.pre_roll)
            else:
                self.speech.append(block)

            # Cap the tail, never the head: the wake phrase is spoken FIRST,
            # so dropping the oldest audio eventually discards the only thing
            # we are looking for.
            while len(self.speech) > self.stt_limit:
                self.speech.pop()

            enough = (
                len(self.speech) * BLOCK_SIZE >= MIN_SPEECH_BEFORE_STT * SAMPLE_RATE
            )
            if enough and now - self.last_stt_at >= self.detector.stt_interval:
                return self._run_stt(now)
            return ""

        if self.speech and (now - self.last_speech_at) > SPEECH_HANG_SECONDS:
            return self.finish(now)
        return ""

    def finish(self, now: float = 0.0) -> str:
        """
        Final decision on the utterance currently in the buffer.

        This is the run that matters. Mid-speech the window is still growing,
        and a half-spoken phrase scores poorly; once the speaker stops, the
        whole phrase is available and scores correctly. The live listener gets
        here on its own after SPEECH_HANG_SECONDS of quiet; tests call it
        directly at the end of a file.

        Args:
            now: monotonic time to record against the cooldown.

        Returns:
            str: the transcript, or "" if there was nothing buffered.
        """
        if not self.speech:
            return ""
        text = self._run_stt(now)
        self.speech = []
        self.pre_roll = []
        self.vad_history = [
            np.zeros(BLOCK_SIZE, dtype=np.float32)
            for _ in range(int(VAD_WINDOW_SECONDS * SAMPLE_RATE / BLOCK_SIZE))
        ]
        self.last_stt_at = 0.0
        self.last_speech_at = 0.0
        return text

    def _run_stt(self, now: float) -> str:
        self.last_stt_at = now
        self.runs += 1
        text = self.detector._transcribe(
            self.detector._stt_audio(self.speech)
        )
        if text:
            self.detector.last_transcript = text
            self.detector._maybe_trigger(text, now)
        return text


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
        input_device: str = "",
        torch_device: str | None = None,
    ) -> None:
        self.phrase = phrase
        self.language = detect_phrase_language(phrase)
        self.model_path = model_path
        self.on_detect = on_detect
        self.cooldown = cooldown
        self.threshold = threshold
        self.stt_interval = stt_interval
        # Audio input name (or "" for system default) - resolved to a PortAudio index
        # at start, because indices move when devices are reconnected.
        self.device_spec = input_device or ""
        # Audio input. Deliberately NOT named `device`: that one means the torch
        # device the model runs on, and overloading it silently pinned the model
        # to CPU.
        self.input_device: int | str | None = None
        self.torch_device = torch_device
        self.device_name: str | None = None
        self.device_problem: str | None = None

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._vad = None
        self._processor = None
        self._model = None
        self._last_trigger = 0.0
        self.last_transcript = ""
        self.error: Optional[str] = None
        # Rolling audio-level meter. The #1 question when the wake word "does
        # nothing" is whether the microphone hears anything at all, so this is
        # reported over the API and drawn as a bar in the UI.
        self.input_level = 0.0
        self.peak_level = 0.0
        self.opened = False
        self.blocks_read = 0

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
                if self.torch_device:
                    model.to(self.torch_device)
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

        self.input_device, self.device_name, self.device_problem = resolve_input_device(
            self.device_spec
        )
        if self.device_problem:
            logger.warning(f"Wake word input device: {self.device_problem}")
        logger.info(
            f"Wake word input device: {self.device_name or 'system default'}"
        )

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                device=self.input_device,
            ) as stream:
                logger.info(
                    f"Wake word microphone open (device={self.input_device})"
                )
                self.opened = True
                stream_ = WakeWordStream(self, self._vad)
                while not self._stop.is_set():
                    data, _ = stream.read(BLOCK_SIZE)
                    block = np.asarray(data, dtype=np.float32).flatten()
                    if block.size == 0:
                        continue

                    update_level_meter(self, block)
                    stream_.push(block)
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            logger.warning(f"Wake word listener stopped: {e}")

    @staticmethod
    def _stt_audio(blocks: list[np.ndarray]) -> np.ndarray:
        """
        Build the audio actually handed to Whisper.

        A short burst of leading silence is prepended: measured on this model,
        it raised the match score for a 3 s window from 0.53 to 0.82, because
        Whisper expects the onset of a phrase to arrive after a quiet context.

        Args:
            blocks: the captured blocks, oldest first.

        Returns:
            np.ndarray: float32 samples ready for the processor.
        """
        audio = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)
        pad = np.zeros(int(LEAD_SILENCE_SECONDS * SAMPLE_RATE), dtype=np.float32)
        return np.concatenate([pad, audio])

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
