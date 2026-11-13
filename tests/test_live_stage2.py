"""Unit tests for Stage 2 Live Mode (VAD, hallucination filter, session & barge-in)."""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace

import numpy as np
import pytest

from src.live_session import (
    BLOCK_SIZE,
    SAMPLE_RATE,
    LiveSessionManager,
    LiveVADProcessor,
    is_whisper_hallucination,
)
from src.llm_engine import LLMResponse, LLMStreamEvent, ToolAction


def _block(val: float = 0.05) -> np.ndarray:
    return np.full(BLOCK_SIZE, val, dtype=np.float32)


def test_whisper_hallucination_filter():
    assert is_whisper_hallucination("") is True
    assert is_whisper_hallucination("   ...   ") is True
    assert is_whisper_hallucination("[Музыка]") is True
    assert is_whisper_hallucination("Субтитры создавал DimaTorzok") is True
    assert is_whisper_hallucination("Спасибо за просмотр!") is True
    assert is_whisper_hallucination("Thank you for watching.") is True

    assert is_whisper_hallucination("Да") is False
    assert is_whisper_hallucination("Нет, не надо") is False
    assert is_whisper_hallucination("Привет! Открой блокнот.") is False


def test_vad_preroll_pause_and_noise_rejection():
    probs: list[float] = []

    def fake_vad(block: np.ndarray) -> float:
        return probs.pop(0) if probs else 0.0

    vad = LiveVADProcessor(
        vad_fn=fake_vad,
        pre_roll_blocks=3,
        pause_silence_blocks=4,
        min_speech_blocks=5,
        barge_in_blocks=3,
    )

    # 3 blocks of silence -> sit in pre-roll
    probs.extend([0.0, 0.0, 0.0])
    for i in range(3):
        res = vad.process_block(_block(0.01 * (i + 1)))
        assert res["speech_started"] is False
        assert res["utterance"] is None

    # 2 blocks of transient noise (< min_speech_blocks=5), followed by 4 silence -> dropped
    probs.extend([0.9, 0.9, 0.1, 0.1, 0.1, 0.1])
    utt = None
    for _ in range(6):
        res = vad.process_block(_block(0.2))
        if res["utterance"] is not None:
            utt = res["utterance"]
    assert utt is None

    # Now 3 silence pre-roll, 5 voiced blocks, 4 silence pause -> accepted utterance!
    probs.extend([0.0, 0.0, 0.0] + [0.9] * 5 + [0.0] * 4)
    started = False
    for idx in range(12):
        res = vad.process_block(_block(0.3 if 3 <= idx < 8 else 0.0))
        if res["speech_started"]:
            started = True
        if res["utterance"] is not None:
            utt = res["utterance"]

    assert started is True
    assert utt is not None
    # Lead zero pad (0.25s = 4000 samples) + pre-roll (3) + speech (5) + kept tail (3)
    expected_samples = int(0.25 * SAMPLE_RATE) + (3 + 5 + 3) * BLOCK_SIZE
    assert len(utt) == expected_samples
    assert np.all(utt[: int(0.25 * SAMPLE_RATE)] == 0.0)


def test_vad_barge_in_and_mute():
    probs = [0.9] * 6
    vad = LiveVADProcessor(
        vad_fn=lambda _: probs.pop(0) if probs else 0.0,
        barge_in_blocks=3,
    )

    barge_hits = []
    for _ in range(6):
        res = vad.process_block(_block(0.2), assistant_active=True)
        if res["barge_in"]:
            barge_hits.append(True)

    # Barge-in fires exactly once on the 3rd consecutive voiced block
    assert barge_hits == [True]

    vad.set_muted(True)
    res_muted = vad.process_block(_block(0.5), assistant_active=True)
    assert res_muted == {
        "level": 0.0,
        "prob": 0.0,
        "speech_started": False,
        "barge_in": False,
        "utterance": None,
    }


class _FakeDB:
    def __init__(self) -> None:
        self.chats: dict[int, str] = {}
        self.messages: list[tuple[int, str, str, list | None]] = []
        self._next_chat = 10

    async def create_chat(self, title: str = "New") -> int:
        cid = self._next_chat
        self._next_chat += 1
        self.chats[cid] = title
        return cid

    async def add_message(self, chat_id: int, role: str, content: str, actions=None) -> int:
        self.messages.append((chat_id, role, content, actions))
        return len(self.messages)

    async def get_chat_history(self, chat_id: int):
        return [
            SimpleNamespace(role=r, content=c)
            for cid, r, c, _ in self.messages
            if cid == chat_id
        ]


@pytest.mark.asyncio
async def test_live_session_full_turn_with_tools_and_tts():
    events: list[dict] = []
    db = _FakeDB()

    class _FakeSTT:
        is_initialized = True

        async def initialize(self):
            pass

        async def transcribe_numpy(self, audio, sample_rate=16000) -> str:
            return "Открой калькулятор и скажи привет."

    class _FakeTTS:
        is_dummy = False
        is_omnivoice_loaded = True

        async def speak(self, text: str):
            return SimpleNamespace(success=True, audio_data=b"RIFFfakewav:" + text.encode("utf-8"))

    class _FakeAssistant:
        async def process_message_stream(
            self,
            user_message: str,
            thinking: bool = False,
            search: str = "",
            chat_history=None,
            images=None,
            cancel_event=None,
        ):
            assert "Открой калькулятор" in user_message
            yield LLMStreamEvent(
                type="tool_start",
                tool_name="app_open",
                tool_arguments={"name": "calc"},
            )
            act = ToolAction(
                name="app_open",
                arguments={"name": "calc"},
                result_preview="Opened",
                ok=True,
            )
            yield LLMStreamEvent(type="tool_done", tool_name="app_open", action=act)
            yield LLMStreamEvent(type="token", token="Калькулятор открыт. ")
            yield LLMStreamEvent(type="token", token="Привет!")
            yield LLMStreamEvent(
                type="done",
                response=LLMResponse(
                    content="Калькулятор открыт. Привет!",
                    model="test",
                    actions=[act],
                    prompt_tokens=120,
                ),
            )

    probs = [0.9] * 4 + [0.0] * 3
    vad = LiveVADProcessor(
        vad_fn=lambda _: probs.pop(0) if probs else 0.0,
        pre_roll_blocks=1,
        pause_silence_blocks=3,
        min_speech_blocks=4,
        barge_in_blocks=2,
    )

    session = LiveSessionManager(
        assistant=_FakeAssistant(),
        stt=_FakeSTT(),
        tts=_FakeTTS(),
        db=db,
        config=None,
        event_cb=lambda payload: asyncio.sleep(0, result=events.append(payload)),
        get_context_max_cb=lambda: asyncio.sleep(0, result=8192),
        vad=vad,
    )

    await session.start(chat_id=None, thinking=False, open_mic=False)
    for _ in range(7):
        session.push_audio_block(_block(0.2))

    # Wait briefly for async turn + TTS queue to drain
    for _ in range(50):
        if any(e.get("type") == "ai_audio" for e in events) and any(
            e.get("type") == "ai_done" for e in events
        ):
            break
        await asyncio.sleep(0.02)

    await session.stop()

    types = [e["type"] for e in events]
    assert "chat_created" in types
    assert "user_transcript" in types
    assert "tool_start" in types
    assert "tool_done" in types
    assert "ai_token" in types
    assert "ai_done" in types
    assert "ai_audio" in types

    audio_events = [e for e in events if e["type"] == "ai_audio"]
    decoded = b"".join(base64.b64decode(e["data"]) for e in audio_events)
    assert b"RIFFfakewav:" in decoded

    assert len(db.messages) == 2
    assert db.messages[0][1] == "user"
    assert db.messages[1][1] == "assistant"
    assert db.messages[1][3][0]["name"] == "app_open"


@pytest.mark.asyncio
async def test_live_session_barge_in_cancels_llm_and_tts():
    events: list[dict] = []
    db = _FakeDB()
    observed_cancel = asyncio.Event()

    class _FakeSTT:
        is_initialized = True

        async def transcribe_numpy(self, audio, sample_rate=16000) -> str:
            return "Расскажи длинную историю"

    class _FakeTTS:
        is_dummy = False
        is_omnivoice_loaded = True

        async def speak(self, text: str):
            await asyncio.sleep(0.15)
            return SimpleNamespace(success=True, audio_data=b"WAV")

    class _SlowAssistant:
        async def process_message_stream(
            self,
            user_message: str,
            thinking: bool = False,
            search: str = "",
            chat_history=None,
            images=None,
            cancel_event=None,
        ):
            yield LLMStreamEvent(type="token", token="Первое предложение. ")
            for _ in range(30):
                if cancel_event is not None and cancel_event.is_set():
                    observed_cancel.set()
                    return
                await asyncio.sleep(0.02)
            yield LLMStreamEvent(
                type="done",
                response=LLMResponse(
                    content="Первое предложение.",
                    model="test",
                    prompt_tokens=50,
                ),
            )

    vad = LiveVADProcessor(
        vad_fn=lambda _: 0.9,
        pause_silence_blocks=2,
        min_speech_blocks=3,
        barge_in_blocks=2,
    )

    session = LiveSessionManager(
        assistant=_SlowAssistant(),
        stt=_FakeSTT(),
        tts=_FakeTTS(),
        db=db,
        config=None,
        event_cb=lambda payload: asyncio.sleep(0, result=events.append(payload)),
        vad=vad,
    )

    await session.start(chat_id=1, thinking=False, open_mic=False)
    turn_task = asyncio.create_task(session.submit_text("Расскажи длинную историю"))

    # Let first token enter TTS queue
    for _ in range(30):
        if any(e.get("type") == "ai_token" for e in events):
            break
        await asyncio.sleep(0.01)

    # User starts speaking (2 consecutive voiced blocks -> triggers barge-in!)
    session.push_audio_block(_block(0.3))
    session.push_audio_block(_block(0.3))

    for _ in range(40):
        if any(e.get("type") == "interrupt" for e in events):
            break
        await asyncio.sleep(0.01)

    await asyncio.wait_for(turn_task, timeout=1.0)
    await session.stop()

    assert observed_cancel.is_set()
    assert any(e.get("type") == "interrupt" for e in events)
    # Slow TTS should have been aborted / dropped due to generation_id increment
    assert not any(e.get("type") == "ai_audio" for e in events)


def test_backend_live_websocket_wiring(monkeypatch):
    from fastapi.testclient import TestClient
    import backend.main as bm

    fake_db = _FakeDB()

    class _MockSTT:
        is_initialized = True

        async def initialize(self):
            pass

        async def transcribe_numpy(self, audio, sample_rate=16000) -> str:
            return "Привет"

    class _MockTTS:
        is_dummy = False
        is_omnivoice_loaded = True

        async def speak(self, text: str):
            return SimpleNamespace(success=True, audio_data=b"WAVDATA")

    class _MockAssistant:
        _tts = _MockTTS()
        _llm = None

        async def process_message_stream(
            self,
            user_message: str,
            thinking: bool = False,
            search: str = "",
            chat_history=None,
            images=None,
            cancel_event=None,
        ):
            yield LLMStreamEvent(type="token", token="Привет!")
            yield LLMStreamEvent(
                type="done",
                response=LLMResponse(content="Привет!", model="test", prompt_tokens=10),
            )

    async def _fake_get_stt_engine():
        return _MockSTT()

    async def _fake_noop():
        return None

    async def _fake_ctx():
        return 8192

    # Avoid opening a real hardware microphone during CI/sandbox test
    orig_start = LiveSessionManager.start

    async def _safe_start(self, chat_id=None, thinking=False, open_mic=True):
        return await orig_start(self, chat_id=chat_id, thinking=thinking, open_mic=False)

    monkeypatch.setattr(bm, "_assistant", _MockAssistant())
    monkeypatch.setattr(bm, "_db", fake_db)
    monkeypatch.setattr(bm, "_config", None)
    monkeypatch.setattr(bm, "get_stt_engine", _fake_get_stt_engine)
    monkeypatch.setattr(bm, "_tts_engine_ready", lambda: True)
    monkeypatch.setattr(bm, "_sync_lmstudio_before_live_turn", _fake_noop)
    monkeypatch.setattr(bm, "get_effective_context_length", _fake_ctx)
    monkeypatch.setattr(LiveSessionManager, "start", _safe_start)

    client = TestClient(bm.app)
    with client.websocket_connect("/ws/live?thinking=false") as ws:
        connecting = ws.receive_json()
        assert connecting == {"type": "live_state", "state": "connecting"}
        listening = ws.receive_json()
        assert listening == {"type": "live_state", "state": "listening"}
        ws.send_json({"type": "text", "content": "Привет"})
        seen = []
        for _ in range(15):
            ev = ws.receive_json()
            seen.append(ev["type"])
            if ev["type"] == "ai_done":
                break
        assert "user_transcript" in seen
        assert "ai_token" in seen
        assert "ai_done" in seen
        ws.send_json({"type": "stop"})
