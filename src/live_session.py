"""
Live Mode (full-duplex real-time voice conversation) session management.

Provides:
- `is_whisper_hallucination`: filters known Whisper silence hallucinations
- `LiveVADProcessor`: low-latency per-block Silero VAD with pre-roll & barge-in
- `LiveSessionManager`: orchestrates mic capture, Whisper STT, streaming LLM+tools,
  SentenceChunker, pipelined OmniVoice TTS, DB persistence, and WebSocket events.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import logging
import re
import time
from collections import deque
from typing import Any, Awaitable, Callable, Optional

import numpy as np

from src.sentence_chunker import SentenceChunker

logger = logging.getLogger(__name__)

# Audio constants matching src/wake_word.py and Whisper 16 kHz input
SAMPLE_RATE = 16000
BLOCK_SIZE = 512  # 32 ms @ 16 kHz

# Common Whisper hallucinations produced on silence / breathing / background hum.
_HALLUCINATION_PHRASES = (
    "субтитры создавал",
    "субтитры сделал",
    "субтитры подготовил",
    "редактор субтитров",
    "dimatorzok",
    "продолжение следует",
    "подписывайтесь на канал",
    "ставь лайк",
    "ставьте лайки",
    "спасибо за просмотр",
    "благодарим за просмотр",
    "thank you for watching",
    "thanks for watching",
    "subscribe to my channel",
    "amara.org",
    "mbc 뉴스",
    "ご視聴ありがとうございました",
)

_BRACKET_NOISE_RE = re.compile(r"^[\[\(][^\]\)]{1,40}[\]\)]$")
_PUNCT_ONLY_RE = re.compile(r"^[\s.,!?;:\-—–…\"'«»()\[\]*~_`]+$")


def is_whisper_hallucination(text: str) -> bool:
    """Return True if *text* is empty, pure punctuation, or a known Whisper silence artifact."""
    if not text:
        return True
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return True
    if _PUNCT_ONLY_RE.match(cleaned):
        return True
    if _BRACKET_NOISE_RE.match(cleaned):
        return True

    lowered = cleaned.lower().strip(".,!?;:\"'«»-—… ")
    if not lowered:
        return True
    for phrase in _HALLUCINATION_PHRASES:
        if phrase in lowered:
            return True
    return False


class LiveVADProcessor:
    """
    Stateful per-block Voice Activity Detector for full-duplex Live Mode.

    Detects:
    - Speech onset (with pre-roll audio preserved so first phoneme isn't clipped)
    - Barge-in (sustained speech while assistant is speaking/thinking)
    - End of utterance (~512 ms trailing silence or max utterance cap)
    """

    def __init__(
        self,
        vad_fn: Optional[Callable[[np.ndarray], float]] = None,
        speech_threshold: float = 0.5,
        sample_rate: int = SAMPLE_RATE,
        block_size: int = BLOCK_SIZE,
        pre_roll_blocks: int = 7,
        pause_silence_blocks: int = 16,
        min_speech_blocks: int = 9,
        barge_in_blocks: int = 4,
        max_speech_blocks: int = 937,
    ) -> None:
        self._vad_fn = vad_fn
        self._silero_model = None
        self.speech_threshold = speech_threshold
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.pre_roll_blocks = max(0, pre_roll_blocks)
        self.pause_silence_blocks = max(1, pause_silence_blocks)
        self.min_speech_blocks = max(1, min_speech_blocks)
        self.barge_in_blocks = max(1, barge_in_blocks)
        self.max_speech_blocks = max(min_speech_blocks + 1, max_speech_blocks)
        self._lead_zero_samples = int(0.25 * sample_rate)

        self.muted = False
        self._pre_roll: deque[np.ndarray] = deque(maxlen=self.pre_roll_blocks)
        self._speech_blocks: list[np.ndarray] = []
        self._in_speech = False
        self._silence_count = 0
        self._voiced_blocks = 0
        self._consecutive_speech = 0
        self._barge_in_fired = False

    def ensure_loaded(self) -> None:
        """Load Silero VAD once when no injected callable was supplied."""
        if self._vad_fn is not None or self._silero_model is not None:
            return
        from silero_vad import load_silero_vad

        self._silero_model = load_silero_vad()

    def _get_prob(self, block: np.ndarray) -> float:
        if self._vad_fn is not None:
            return float(self._vad_fn(block))
        self.ensure_loaded()
        import torch

        tensor = torch.from_numpy(block).float()
        return float(self._silero_model(tensor, self.sample_rate).item())

    def reset_utterance(self, reset_vad_states: bool = False) -> None:
        """Reset current utterance capture buffers."""
        self._pre_roll.clear()
        self._speech_blocks.clear()
        self._in_speech = False
        self._silence_count = 0
        self._voiced_blocks = 0
        self._consecutive_speech = 0
        self._barge_in_fired = False
        if reset_vad_states and self._silero_model is not None:
            try:
                self._silero_model.reset_states()
            except Exception:
                pass

    def set_muted(self, muted: bool) -> None:
        """Toggle microphone mute and discard any half-captured utterance on mute."""
        self.muted = bool(muted)
        if self.muted:
            self.reset_utterance(reset_vad_states=True)

    def _finalize_utterance(self) -> Optional[np.ndarray]:
        """Package completed speech blocks into a 1D float32 array with 0.25s lead padding."""
        enough_speech = self._voiced_blocks >= self.min_speech_blocks
        silence_count = self._silence_count
        blocks = list(self._speech_blocks)
        self.reset_utterance(reset_vad_states=False)

        if not enough_speech or not blocks:
            return None

        # Trim excessive trailing silence down to ~3 blocks (~96 ms) for cleaner STT.
        if silence_count > 3:
            trim = silence_count - 3
            if 0 < trim < len(blocks):
                blocks = blocks[:-trim]

        lead = np.zeros(self._lead_zero_samples, dtype=np.float32)
        body = np.concatenate([b.astype(np.float32, copy=False) for b in blocks])
        return np.concatenate([lead, body])

    def process_block(
        self, block: np.ndarray, assistant_active: bool = False
    ) -> dict[str, Any]:
        """
        Process one 16 kHz mono float32 block (typically 512 samples).

        Returns dict with:
        - level: normalized RMS level in [0.0, 1.0]
        - prob: speech probability in [0.0, 1.0]
        - speech_started: True on transition from idle to speech
        - barge_in: True once per utterance when user speaks over active assistant
        - utterance: finalized float32 numpy array or None
        """
        if self.muted:
            return {
                "level": 0.0,
                "prob": 0.0,
                "speech_started": False,
                "barge_in": False,
                "utterance": None,
            }

        arr = np.asarray(block, dtype=np.float32).reshape(-1)
        rms = float(np.sqrt(np.mean(arr * arr))) if arr.size else 0.0
        level = min(1.0, rms * 6.0)

        prob = self._get_prob(arr)
        is_speech = prob >= self.speech_threshold

        speech_started = False
        barge_in = False
        utterance: Optional[np.ndarray] = None

        if is_speech:
            self._consecutive_speech += 1
            self._silence_count = 0
            self._voiced_blocks += 1

            if not self._in_speech:
                self._in_speech = True
                self._speech_blocks = list(self._pre_roll) + [arr.copy()]
                self._barge_in_fired = False
                speech_started = True
            else:
                self._speech_blocks.append(arr.copy())

            if (
                assistant_active
                and not self._barge_in_fired
                and self._consecutive_speech >= self.barge_in_blocks
            ):
                self._barge_in_fired = True
                barge_in = True

            if len(self._speech_blocks) >= self.max_speech_blocks:
                utterance = self._finalize_utterance()
        else:
            self._consecutive_speech = 0
            if self._in_speech:
                self._speech_blocks.append(arr.copy())
                self._silence_count += 1
                if (
                    self._silence_count >= self.pause_silence_blocks
                    or len(self._speech_blocks) >= self.max_speech_blocks
                ):
                    utterance = self._finalize_utterance()
            else:
                if self.pre_roll_blocks > 0:
                    self._pre_roll.append(arr.copy())

        return {
            "level": level,
            "prob": prob,
            "speech_started": speech_started,
            "barge_in": barge_in,
            "utterance": utterance,
        }


EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class LiveSessionManager:
    """
    Coordinates full-duplex Live Mode audio, streaming LLM/tools, TTS synthesis,
    database persistence, and WebSocket event streaming.
    """

    def __init__(
        self,
        *,
        assistant: Any,
        stt: Any,
        tts: Any,
        db: Any,
        config: Any,
        event_cb: EventCallback,
        before_turn_cb: Optional[Callable[[], Awaitable[Optional[int]]]] = None,
        get_context_max_cb: Optional[Callable[[], Awaitable[int]]] = None,
        vad: Optional[LiveVADProcessor] = None,
        mic_stream_factory: Optional[Callable[[Callable[..., None]], Any]] = None,
        input_device: str | int | None = None,
    ) -> None:
        self.assistant = assistant
        self.stt = stt
        self.tts = tts
        self.db = db
        self.config = config
        self.event_cb = event_cb
        self.before_turn_cb = before_turn_cb
        self.get_context_max_cb = get_context_max_cb
        self.vad = vad or LiveVADProcessor()
        self._mic_stream_factory = mic_stream_factory
        self._input_device = input_device

        self.chat_id: Optional[int] = None
        self.thinking: bool = False
        self.state: str = "idle"
        self.running: bool = False

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stream: Any = None
        self._audio_queue: Optional[asyncio.Queue[np.ndarray]] = None
        self._utterance_queue: Optional[asyncio.Queue[np.ndarray]] = None
        self._tts_queue: Optional[asyncio.Queue[tuple[int, int, str] | None]] = None

        self._audio_task: Optional[asyncio.Task] = None
        self._utterance_task: Optional[asyncio.Task] = None
        self._tts_task: Optional[asyncio.Task] = None

        self._generation_id: int = 0
        self._turn_counter: int = 0
        self._audio_seq: int = 0
        self._turn_running: bool = False
        self._client_playing: bool = False
        self._active_cancel_event: Optional[asyncio.Event] = None
        self._last_level_emit: float = 0.0
        self._last_level_value: float = -1.0

    @property
    def assistant_active(self) -> bool:
        """True while the assistant is generating, calling tools, or speaking."""
        return self.state in ("thinking", "tool", "speaking") or self._client_playing

    async def _emit(self, payload: dict[str, Any]) -> None:
        try:
            await self.event_cb(payload)
        except Exception as e:
            logger.debug(f"Live event emit skipped: {e}")

    async def _set_state(self, new_state: str) -> None:
        if self.vad.muted and new_state == "listening":
            new_state = "muted"
        if self.state == new_state:
            return
        self.state = new_state
        await self._emit({"type": "live_state", "state": new_state})

    def _open_mic_stream(self) -> Any:
        def callback(indata, frames, time_info, status) -> None:
            if not self.running or self._loop is None or self._audio_queue is None:
                return
            mono = np.asarray(indata, dtype=np.float32)
            if mono.ndim > 1:
                mono = mono[:, 0]
            block = mono.copy()

            def enqueue() -> None:
                if self._audio_queue is None:
                    return
                if self._audio_queue.full():
                    try:
                        self._audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    self._audio_queue.put_nowait(block)
                except asyncio.QueueFull:
                    pass

            try:
                self._loop.call_soon_threadsafe(enqueue)
            except RuntimeError:
                pass

        if self._mic_stream_factory is not None:
            stream = self._mic_stream_factory(callback)
            if hasattr(stream, "start"):
                stream.start()
            return stream

        import sounddevice as sd
        from src.wake_word import resolve_input_device

        device_spec = self._input_device
        if device_spec is None and self.config is not None:
            wake_cfg = getattr(self.config, "wake", None)
            if wake_cfg is not None:
                device_spec = getattr(wake_cfg, "input_device", None)

        device_id, device_name, err = resolve_input_device(device_spec)
        if err and device_spec:
            logger.warning(f"Live mic resolve failed ({err}), falling back to default input")
            device_id = None

        stream = sd.InputStream(
            device=device_id,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=callback,
        )
        stream.start()
        logger.info(f"Live mic started (device={device_name or device_id or 'default'})")
        return stream

    async def start(
        self,
        chat_id: Optional[int] = None,
        thinking: bool = False,
        open_mic: bool = True,
    ) -> None:
        """Start audio capture and Live Mode worker tasks."""
        if self.running:
            return

        self._loop = asyncio.get_running_loop()
        self.chat_id = chat_id
        self.thinking = bool(thinking)
        self.running = True
        self._client_playing = False
        self._turn_running = False
        self.vad.reset_utterance(reset_vad_states=True)
        self.vad.set_muted(False)

        self._audio_queue = asyncio.Queue(maxsize=128)
        self._utterance_queue = asyncio.Queue(maxsize=16)
        self._tts_queue = asyncio.Queue(maxsize=64)

        self._audio_task = asyncio.create_task(self._audio_loop(), name="live_audio_loop")
        self._utterance_task = asyncio.create_task(
            self._utterance_loop(), name="live_utterance_loop"
        )
        self._tts_task = asyncio.create_task(self._tts_loop(), name="live_tts_loop")

        if open_mic:
            try:
                self._stream = await asyncio.to_thread(self._open_mic_stream)
            except Exception as e:
                await self.stop()
                await self._emit({"type": "error", "detail": str(e)})
                raise

        await self._set_state("listening")

    async def stop(self) -> None:
        """Stop mic stream, cancel active turns/TTS, and clean up workers."""
        if not self.running and self.state == "idle":
            return

        self.running = False
        self._generation_id += 1
        if self._active_cancel_event is not None:
            self._active_cancel_event.set()
        self._drain_tts_queue()

        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                if hasattr(stream, "stop"):
                    stream.stop()
                if hasattr(stream, "close"):
                    stream.close()
            except Exception as e:
                logger.warning(f"Error closing live mic stream: {e}")

        for task in (self._audio_task, self._utterance_task, self._tts_task):
            if task is not None and not task.done():
                task.cancel()
        for task in (self._audio_task, self._utterance_task, self._tts_task):
            if task is not None:
                try:
                    await asyncio.wait_for(task, timeout=1.5)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass

        self._audio_task = None
        self._utterance_task = None
        self._tts_task = None
        self._client_playing = False
        self._turn_running = False
        self.vad.reset_utterance(reset_vad_states=True)
        await self._set_state("idle")

    def _drain_tts_queue(self) -> None:
        if self._tts_queue is None:
            return
        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
                self._tts_queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def set_muted(self, muted: bool) -> None:
        """Mute or unmute microphone processing."""
        self.vad.set_muted(muted)
        if muted:
            await self._set_state("muted")
        elif self.running and not self.assistant_active:
            await self._set_state("listening")

    def set_client_playing(self, playing: bool) -> None:
        """Track whether the frontend Web Audio player still has buffered audio playing."""
        self._client_playing = bool(playing)
        if not self._client_playing and self.running and self.state == "speaking":
            if self._tts_queue is None or self._tts_queue.empty():
                if not self._turn_running and self._loop is not None:
                    self._loop.create_task(
                        self._set_state("muted" if self.vad.muted else "listening")
                    )

    async def interrupt(self) -> None:
        """Immediately abort active LLM stream and flush pending/playing TTS."""
        self._generation_id += 1
        self._client_playing = False
        if self._active_cancel_event is not None:
            self._active_cancel_event.set()
        self._drain_tts_queue()
        await self._emit({"type": "interrupt", "generation_id": self._generation_id})
        if self.running:
            await self._set_state("muted" if self.vad.muted else "listening")

    def push_audio_block(self, block: np.ndarray) -> None:
        """Inject a raw audio block synchronously (primarily for tests)."""
        if self._audio_queue is not None:
            self._audio_queue.put_nowait(np.asarray(block, dtype=np.float32))

    async def _audio_loop(self) -> None:
        while self.running and self._audio_queue is not None:
            try:
                block = await self._audio_queue.get()
            except asyncio.CancelledError:
                break

            res = self.vad.process_block(block, assistant_active=self.assistant_active)

            now = time.monotonic()
            level = float(res["level"])
            if now - self._last_level_emit >= 0.08 and (
                abs(level - self._last_level_value) >= 0.02 or level > 0.02
            ):
                self._last_level_emit = now
                self._last_level_value = level
                await self._emit({"type": "mic_level", "level": round(level, 3)})

            if res["barge_in"] and self.assistant_active:
                logger.info("Live Mode: barge-in detected, interrupting assistant")
                await self.interrupt()

            utterance = res["utterance"]
            if utterance is not None and self._utterance_queue is not None:
                if self._utterance_queue.full():
                    try:
                        self._utterance_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                await self._utterance_queue.put(utterance)

    async def _utterance_loop(self) -> None:
        while self.running and self._utterance_queue is not None:
            try:
                audio = await self._utterance_queue.get()
            except asyncio.CancelledError:
                break

            try:
                await self._process_utterance(audio)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Live utterance processing failed: {e}", exc_info=True)
                await self._emit({"type": "error", "detail": str(e)})
                if self.running:
                    await self._set_state("muted" if self.vad.muted else "listening")

    async def _tts_loop(self) -> None:
        while self.running and self._tts_queue is not None:
            try:
                item = await self._tts_queue.get()
            except asyncio.CancelledError:
                break

            if item is None:
                self._tts_queue.task_done()
                break

            turn_id, gen_id, chunk_text = item
            try:
                if gen_id != self._generation_id or not self.running:
                    continue
                if not chunk_text.strip():
                    continue
                if not self.tts or getattr(self.tts, "is_dummy", False):
                    continue

                if hasattr(self.tts, "is_omnivoice_loaded") and not self.tts.is_omnivoice_loaded:
                    if hasattr(self.tts, "enable_omnivoice"):
                        ok = await self.tts.enable_omnivoice()
                        if not ok:
                            continue

                if gen_id != self._generation_id or not self.running:
                    continue

                await self._set_state("speaking")
                result = await self.tts.speak(chunk_text)

                if gen_id != self._generation_id or not self.running:
                    continue

                if result and getattr(result, "success", False) and getattr(result, "audio_data", None):
                    self._audio_seq += 1
                    b64 = base64.b64encode(result.audio_data).decode("ascii")
                    await self._emit(
                        {
                            "type": "ai_audio",
                            "turn_id": turn_id,
                            "gen_id": gen_id,
                            "seq": self._audio_seq,
                            "format": "wav",
                            "text": chunk_text,
                            "data": b64,
                        }
                    )
                elif result and getattr(result, "error", None):
                    logger.warning(f"Live TTS chunk error: {result.error}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Live TTS loop error: {e}", exc_info=True)
            finally:
                self._tts_queue.task_done()

                if (
                    self.running
                    and not self._turn_running
                    and self._tts_queue.empty()
                    and not self._client_playing
                    and gen_id == self._generation_id
                ):
                    await self._set_state("muted" if self.vad.muted else "listening")

    async def _ensure_chat_id(self, seed_text: str) -> int:
        if self.chat_id is not None:
            return self.chat_id
        snippet = " ".join(seed_text.split())[:36].strip()
        title = f"Live: {snippet}" if snippet else "Live диалог"
        self.chat_id = await self.db.create_chat(title)
        await self._emit({"type": "chat_created", "chat_id": self.chat_id, "title": title})
        return self.chat_id

    async def _load_history(self, chat_id: int, latest_user_text: str) -> list[dict[str, str]]:
        history_messages = await self.db.get_chat_history(chat_id)
        if (
            history_messages
            and history_messages[-1].role == "user"
            and history_messages[-1].content == latest_user_text
        ):
            history_messages = history_messages[:-1]
        if len(history_messages) > 30:
            history_messages = history_messages[-30:]
        return [
            {"role": msg.role, "content": msg.content}
            for msg in history_messages
            if msg.role in ("user", "assistant")
        ]

    async def _process_utterance(self, audio: np.ndarray) -> None:
        if not self.running:
            return
        if not getattr(self.stt, "is_initialized", True):
            await self.stt.initialize()

        text = await self.stt.transcribe_numpy(audio, sample_rate=SAMPLE_RATE)
        if is_whisper_hallucination(text):
            logger.debug(f"Live Mode: ignored Whisper silence/hallucination: {text!r}")
            return

        await self.submit_text(text)

    async def submit_text(self, text: str) -> None:
        """Process a recognized (or typed) utterance as a full Live turn."""
        if not self.running:
            return
        cleaned = (text or "").strip()
        if not cleaned:
            return

        # Cancel any stale in-flight turn before starting the new turn.
        if self._turn_running or (self._tts_queue is not None and not self._tts_queue.empty()):
            await self.interrupt()

        chat_id = await self._ensure_chat_id(cleaned)
        user_msg_id = await self.db.add_message(chat_id, "user", cleaned)
        await self._emit(
            {
                "type": "user_transcript",
                "chat_id": chat_id,
                "message_id": user_msg_id,
                "text": cleaned,
            }
        )

        chat_history = await self._load_history(chat_id, cleaned)

        if self.before_turn_cb is not None:
            try:
                await self.before_turn_cb()
            except Exception as e:
                logger.warning(f"before_turn_cb failed: {e}")

        self._turn_counter += 1
        turn_id = self._turn_counter
        gen_id = self._generation_id
        cancel_event = asyncio.Event()
        self._active_cancel_event = cancel_event
        self._turn_running = True

        chunker = SentenceChunker()
        full_response = ""
        actions: list[dict[str, Any]] = []
        prompt_tokens = 0
        was_cancelled = False

        await self._set_state("thinking")

        try:
            async for event in self.assistant.process_message_stream(
                cleaned,
                thinking=self.thinking,
                search="",
                chat_history=chat_history,
                cancel_event=cancel_event,
            ):
                if cancel_event.is_set() or gen_id != self._generation_id or not self.running:
                    was_cancelled = True
                    break

                ev_type = event.type
                if ev_type == "token":
                    token = event.token or ""
                    full_response += token
                    await self._emit(
                        {
                            "type": "ai_token",
                            "turn_id": turn_id,
                            "chat_id": chat_id,
                            "content": token,
                        }
                    )
                    for chunk in chunker.feed(token):
                        if chunk.strip() and self._tts_queue is not None:
                            await self._tts_queue.put((turn_id, gen_id, chunk))

                elif ev_type == "tool_start":
                    await self._set_state("tool")
                    await self._emit(
                        {
                            "type": "tool_start",
                            "turn_id": turn_id,
                            "chat_id": chat_id,
                            "tool": event.tool_name,
                            "args": event.tool_arguments or {},
                        }
                    )

                elif ev_type == "tool_done":
                    action = event.action
                    if dataclasses.is_dataclass(action):
                        action = dataclasses.asdict(action)
                    if action is not None:
                        actions.append(action)
                    await self._set_state("thinking")
                    await self._emit(
                        {
                            "type": "tool_done",
                            "turn_id": turn_id,
                            "chat_id": chat_id,
                            "action": action,
                        }
                    )

                elif ev_type == "done":
                    resp = getattr(event, "response", None)
                    if resp is not None:
                        prompt_tokens = int(getattr(resp, "prompt_tokens", 0) or 0)
                        if not full_response and getattr(resp, "content", ""):
                            full_response = resp.content
                    for chunk in chunker.flush():
                        if chunk.strip() and self._tts_queue is not None:
                            await self._tts_queue.put((turn_id, gen_id, chunk))

            if cancel_event.is_set() or gen_id != self._generation_id:
                was_cancelled = True

            saved_text = full_response.strip()
            ai_msg_id: Optional[int] = None
            if saved_text or actions:
                ai_msg_id = await self.db.add_message(
                    chat_id,
                    "assistant",
                    saved_text,
                    actions=actions or None,
                )

            max_ctx = 4096
            if self.get_context_max_cb is not None:
                try:
                    max_ctx = int(await self.get_context_max_cb())
                except Exception:
                    pass

            await self._emit(
                {
                    "type": "ai_done",
                    "turn_id": turn_id,
                    "chat_id": chat_id,
                    "message_id": ai_msg_id,
                    "content": saved_text,
                    "actions": actions,
                    "used_context_tokens": prompt_tokens,
                    "max_context_tokens": max_ctx,
                    "cancelled": was_cancelled,
                }
            )
        finally:
            self._turn_running = False
            if self._active_cancel_event is cancel_event:
                self._active_cancel_event = None
            if (
                self.running
                and not self._client_playing
                and (self._tts_queue is None or self._tts_queue.empty())
                and gen_id == self._generation_id
            ):
                await self._set_state("muted" if self.vad.muted else "listening")
