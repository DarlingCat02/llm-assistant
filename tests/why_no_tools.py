"""
Why is the model not calling tools? Replay the app's REAL payload.

Sends exactly what the assistant would send - same system prompt, same tool
definitions, same options - straight to LM Studio, bypassing the app. Prints
what comes back so we can tell "model cannot do tools" from "our prompt/tools
are wrong".

Usage: python tests/why_no_tools.py
"""

import asyncio
import json
import sys

import httpx

sys.path.insert(0, ".")

from config import get_config                      # noqa: E402
from src.main import Assistant                     # noqa: E402
from src.agent_tools import (                       # noqa: E402
    FILE_CREATE_DEFINITION, APP_OPEN_DEFINITION, FILE_OPEN_DEFINITION,
    BROWSER_OPEN_DEFINITION, SCREENSHOT_DEFINITION,
)

HOST = "http://localhost:1234"

TOOLS = [FILE_CREATE_DEFINITION, APP_OPEN_DEFINITION, FILE_OPEN_DEFINITION,
         BROWSER_OPEN_DEFINITION, SCREENSHOT_DEFINITION]


async def main() -> None:
    assistant = Assistant(get_config())
    await assistant.initialize()

    llm = assistant._llm
    system_prompt = llm.get_system_prompt()
    tools = TOOLS
    lang = get_config().general.language

    print("=" * 70)
    print(f"MODEL: {llm._config.model}   LANG: {lang}")
    print(f"SYSTEM PROMPT ({len(system_prompt)} chars):")
    print("-" * 70)
    print(system_prompt)
    print("-" * 70)
    print(f"TOOLS ({len(tools)}): {[t['function']['name'] for t in tools]}")
    print("=" * 70)

    payload = {
        "model": llm._config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Открой блокнот"},
        ],
        "tools": tools,
        "temperature": 0.7,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        for variant, extra in (
            ("as the app sends it", {}),
            ("+ tool_choice=auto", {"tool_choice": "auto"}),
            ("+ tool_choice=required", {"tool_choice": "required"}),
        ):
            body = {**payload, **extra}
            try:
                r = await client.post(f"{HOST}/v1/chat/completions", json=body)
                data = r.json()
            except Exception as e:
                print(f"\n[{variant}] request failed: {type(e).__name__}: {e}")
                continue

            if "error" in data:
                print(f"\n[{variant}] API error: {data['error']}")
                continue

            msg = data["choices"][0]["message"]
            tcs = msg.get("tool_calls")
            finish = data["choices"][0].get("finish_reason")
            print(f"\n[{variant}] finish_reason={finish} tool_calls={'YES' if tcs else 'no'}")
            if tcs:
                print("   ", json.dumps(tcs, ensure_ascii=False)[:300])
            else:
                text = (msg.get("content") or "")[:220]
                print("    content:", text.encode("ascii", "backslashreplace").decode())

    await assistant.close()


if __name__ == "__main__":
    asyncio.run(main())