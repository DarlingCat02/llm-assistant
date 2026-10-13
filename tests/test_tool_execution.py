"""
Tool execution end-to-end, through the real HTTP parsing path.

Earlier tests stubbed out _generate_single, so a regression in how a real
provider response is turned into ToolCall objects (or in the tool-call loop)
could slip through. Here the httpx client is faked instead: the engine parses a
genuine LM Studio / OpenAI-shaped payload and must still execute the tool and
report it as an action.
"""

import json
from types import SimpleNamespace

import pytest

from src.llm_engine import LLMEngine


def lm_studio_response(tool_calls=None, content="Готово."):
    """A response shaped exactly like LM Studio's /v1/chat/completions."""
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "model": "qwen-3.5-4b",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 120, "total_tokens": 180},
    }


def call(name, args):
    return {
        "id": "call_1",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class ScriptedClient:
    """Returns queued payloads, like a model that first calls a tool."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return FakeResponse(self.payloads.pop(0))

    async def aclose(self):
        return None


@pytest.fixture
def engine():
    e = LLMEngine.__new__(LLMEngine)
    e._config = SimpleNamespace(model="qwen-3.5-4b", temperature=0.7,
                                provider=SimpleNamespace(value="lm_studio"))
    e._client = None
    e._initialized = True
    e._conversation_history = []
    e._tools = {}
    e._persona_prompt = False
    e._persona_prompt_ru = ""
    e._persona_prompt_en = ""
    return e


async def test_tool_call_is_parsed_executed_and_reported(engine):
    """A provider response with tool_calls must produce a real action."""
    engine._client = ScriptedClient([
        lm_studio_response([call("app_open", {"name": "notepad"})], content=""),
        lm_studio_response(content="Открыл блокнот."),
    ])

    executed = []

    async def fake_execute(tc):
        executed.append((tc.name, tc.arguments))
        return "Запущено: notepad"

    engine._execute_tool = fake_execute

    result = await engine.generate("открой блокнот", tools=[{"function": {"name": "app_open"}}])

    # Parsed from the raw provider payload
    assert executed == [("app_open", {"name": "notepad"})]
    # Reported to the UI
    assert [a.name for a in result.actions] == ["app_open"]
    assert result.actions[0].arguments == {"name": "notepad"}
    assert result.actions[0].ok is True
    assert result.content == "Открыл блокнот."
    # Two rounds: tool call + follow-up
    assert len(engine._client.requests) == 2


async def test_tool_result_is_sent_back_to_the_model(engine):
    """The tool output must reach the model, otherwise loops never converge."""
    engine._client = ScriptedClient([
        lm_studio_response([call("file_create", {"path": "a.txt", "content": "x"})], content=""),
        lm_studio_response(content="Готово."),
    ])

    async def fake_execute(tc):
        return "Файл создан: a.txt"

    engine._execute_tool = fake_execute
    await engine.generate("создай файл", tools=[{"function": {"name": "file_create"}}])

    second_messages = engine._client.requests[1][1]["json"]["messages"]
    tool_msgs = [m for m in second_messages if m.get("role") == "tool"]
    assert tool_msgs, "the tool result was never sent back to the model"
    assert "Файл создан: a.txt" in tool_msgs[0]["content"]
    assert tool_msgs[0]["tool_call_id"] == "call_1"


async def test_plain_answer_executes_nothing(engine):
    engine._client = ScriptedClient([lm_studio_response(content="Привет")])
    result = await engine.generate("привет", tools=[{"function": {"name": "app_open"}}])
    assert result.actions == []
    assert len(engine._client.requests) == 1


async def test_failed_tool_is_flagged(engine):
    engine._client = ScriptedClient([
        lm_studio_response([call("file_create", {"path": "a.txt"})], content=""),
        lm_studio_response(content="Не вышло."),
    ])

    async def fake_execute(tc):
        return "Ошибка: [WinError 5] доступ запрещён"

    engine._execute_tool = fake_execute
    result = await engine.generate("создай файл", tools=[{"function": {"name": "file_create"}}])
    assert result.actions[0].ok is False


async def test_malformed_tool_arguments_do_not_crash(engine):
    """A model that sends broken JSON must not take the whole request down."""
    engine._client = ScriptedClient([
        {
            "model": "qwen",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "x",
                        "type": "function",
                        "function": {"name": "app_open", "arguments": "{not json"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {},
        },
        lm_studio_response(content="Что-то пошло не так."),
    ])

    with pytest.raises(Exception):
        # Parsing raises; what matters is that it is a clear error, not a hang
        await engine.generate("открой блокнот", tools=[{"function": {"name": "app_open"}}])