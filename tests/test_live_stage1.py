"""Unit tests for Live Mode Stage 1: SentenceChunker and streaming tool-call parser."""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest

from config import LLMConfig, LLMProvider
from src.llm_engine import LLMEngine
from src.sentence_chunker import SentenceChunker, clean_for_speech


def test_clean_for_speech_strips_markdown():
    raw = "## Заголовок\n- **Привет**, [ссылка](https://example.com) и `код`!"
    cleaned = clean_for_speech(raw)
    assert "**" not in cleaned
    assert "`" not in cleaned
    assert "https://example.com" not in cleaned
    assert "Заголовок" in cleaned
    assert "Привет, ссылка и код!" in cleaned


def test_sentence_chunker_respects_decimals_and_abbreviations():
    chunker = SentenceChunker()
    tokens = [
        "Версия ", "3", ".", "5 ", "работает ", "стабильно", ". ",
        "Там ", "есть ", "текст", ", ", "звук ", "и ", "т", ".", "д", ".", " ",
        "Отлично", "!"
    ]
    out: list[str] = []
    for tok in tokens:
        out.extend(chunker.feed(tok))
    out.extend(chunker.flush())

    assert out == [
        "Версия 3.5 работает стабильно.",
        "Там есть текст, звук и т.д.",
        "Отлично!",
    ]


def test_sentence_chunker_strips_think_and_code_blocks():
    chunker = SentenceChunker()
    stream = (
        "<th" + "ink>Скрытые размышления. Не говорить.</thi" + "nk>"
        "Привет! "
        "```python\nprint('hello')\n```"
        " Готово."
    )
    out: list[str] = []
    for i in range(0, len(stream), 4):
        out.extend(chunker.feed(stream[i : i + 4]))
    out.extend(chunker.flush())

    assert out == ["Привет!", "Готово."]


def test_sentence_chunker_splits_long_clause_early():
    chunker = SentenceChunker(min_clause_words=6)
    text = "Сегодня на улице очень солнечная и приятная погода, поэтому стоит прогуляться."
    out: list[str] = []
    for word in text.split(" "):
        out.extend(chunker.feed(word + " "))
    out.extend(chunker.flush())

    assert len(out) == 2
    assert out[0] == "Сегодня на улице очень солнечная и приятная погода,"
    assert out[1] == "поэтому стоит прогуляться."


class _FakeSSEResponse:
    def __init__(self, lines: list[str]):
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            await asyncio.sleep(0)
            yield line


class _FakeAsyncClient:
    def __init__(self, rounds: list[list[str]]):
        self._rounds = list(rounds)
        self.calls = 0

    @asynccontextmanager
    async def stream(self, method: str, url: str, json: dict):
        idx = self.calls
        self.calls += 1
        yield _FakeSSEResponse(self._rounds[idx])


@pytest.mark.asyncio
async def test_stream_generate_multi_round_tool_calls():
    cfg = LLMConfig(provider=LLMProvider.LM_STUDIO, model="qwen-test")
    engine = LLMEngine(cfg)
    engine._initialized = True

    round1_sse = [
        'data: {"model":"qwen-test","choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"app_"}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"open","arguments":"{\\"name\\": \\""}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"notepad\\"}"}}]}}]}',
        "data: [DONE]",
    ]
    round2_sse = [
        'data: {"model":"qwen-test","choices":[{"delta":{"content":"Блокнот "}}]}',
        'data: {"choices":[{"delta":{"content":"открыт."}}]}',
        'data: {"usage":{"prompt_tokens":128}}',
        "data: [DONE]",
    ]

    engine._client = _FakeAsyncClient([round1_sse, round2_sse])

    async def fake_tool(name: str):
        return f"Opened {name}"

    engine.register_tool("app_open", fake_tool)

    events = []
    async for ev in engine.stream_generate("Открой блокнот"):
        events.append(ev)

    types = [e.type for e in events]
    assert types == ["tool_start", "tool_done", "token", "token", "done"]
    assert events[0].tool_name == "app_open"
    assert events[0].tool_arguments == {"name": "notepad"}
    assert events[1].action is not None and events[1].action.ok is True
    done_ev = events[-1]
    assert done_ev.response is not None
    assert done_ev.response.content == "Блокнот открыт."
    assert done_ev.response.prompt_tokens == 128
    assert len(done_ev.response.actions) == 1
