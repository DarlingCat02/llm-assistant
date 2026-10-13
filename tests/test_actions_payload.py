"""
Tool actions: executed tool calls must be reported to the UI.
"""

import dataclasses
from types import SimpleNamespace

import pytest

from src.llm_engine import LLMEngine, LLMResponse, ToolAction, ToolCall


def _resp(content="", tool_calls=None, tokens=0):
    return LLMResponse(
        content=content,
        model="test-model",
        prompt_tokens=tokens,
        tool_calls=tool_calls or [],
    )


class FakeEngine(LLMEngine):
    """LLM engine with the HTTP layer replaced by scripted responses."""

    def __init__(self, responses):
        # Skip LLMEngine.__init__ (config lookups) - build a bare instance
        self._config = SimpleNamespace(
            model="test-model",
            temperature=0.7,
            provider=SimpleNamespace(value="fake"),  # not Ollama -> no extra options
        )
        self._client = None
        self._initialized = True
        self._conversation_history = []
        self._tools = {}
        self._responses = list(responses)
        self.payloads = []

    async def _build_messages(self, *a, **kw):
        return ([], False)

    async def _generate_single(self, payload):
        self.payloads.append(payload)
        return self._responses.pop(0)


async def test_actions_accumulated_across_rounds():
    engine = FakeEngine([
        _resp(tool_calls=[ToolCall(id="1", name="app_open", arguments={"name": "notepad"})]),
        _resp(content="Готово", tool_calls=[ToolCall(id="2", name="file_create",
                                                    arguments={"path": "a.txt", "content": "x"})]),
        _resp(content="Открыл и создал файл."),
    ])

    executed = []

    async def fake_exec(tc):
        executed.append(tc.name)
        return "ok"

    engine._execute_tool = fake_exec

    result = await engine.generate("открой блокнот и создай файл", tools=[{"function": {"name": "x"}}])

    assert executed == ["app_open", "file_create"]
    assert [a.name for a in result.actions] == ["app_open", "file_create"]
    assert result.content == "Открыл и создал файл."


async def test_no_actions_when_model_answers_directly():
    engine = FakeEngine([_resp(content="Привет")])
    result = await engine.generate("привет")
    assert result.actions == []


async def test_action_result_truncated_and_error_marked():
    engine = FakeEngine([_resp(content="готово")])
    tc = ToolCall(id="1", name="capture_screen", arguments={"monitor": 0})

    long_result = "A" * 5000
    action = engine._make_action(tc, long_result)
    assert len(action.result_preview) <= engine.ACTION_PREVIEW_LIMIT + 3
    assert action.result_preview.endswith("...")
    assert action.ok is True

    # agent_tools returns Russian error strings
    assert engine._make_action(tc, "Ошибка: [WinError 5] доступ запрещён").ok is False
    assert engine._make_action(tc, "[Error: ffmpeg not found]").ok is False
    assert engine._make_action(tc, "Запущено: notepad").ok is True


async def test_action_arguments_always_dict():
    engine = FakeEngine([_resp(content="x")])
    action = engine._make_action(ToolCall(id="1", name="t", arguments="plain"), "res")
    assert isinstance(action.arguments, dict)
    assert action.arguments == {"value": "plain"}


async def test_tool_action_serialisable():
    """Frontend receives plain dicts, not dataclasses."""
    action = ToolAction(name="app_open", arguments={"name": "notepad"},
                        result_preview="opened", ok=True)
    payload = dataclasses.asdict(action)
    assert payload == {"name": "app_open", "arguments": {"name": "notepad"},
                       "result_preview": "opened", "ok": True}