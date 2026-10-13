"""
Diagnostic: can the currently loaded LM Studio model emit tool calls at all?

Bypasses the app entirely and sends a plain OpenAI-style request with one tool
tool. If tool_calls is empty here, the problem is the model, not our code.

Usage: python tests/check_tool_calling.py
"""

import json
import urllib.request

HOST = "http://localhost:1234"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "app_open",
            "description": "Open an application on the user's computer.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Application name"}},
                "required": ["name"],
            },
        },
    }
]


def post(path, payload, timeout=120):
    req = urllib.request.Request(
        HOST + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def loaded_models():
    data = json.loads(urllib.request.urlopen(HOST + "/api/v0/models", timeout=10).read())
    return [m["id"] for m in data.get("data", []) if m.get("state") == "loaded"]


def try_model(model, message):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant with tools. Use them when asked."},
            {"role": "user", "content": message},
        ],
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.7,
        "stream": False,
    }
    try:
        resp = post("/v1/chat/completions", payload)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    msg = resp.get("choices", [{}])[0].get("message", {})
    return {
        "content": (msg.get("content") or "")[:150],
        "tool_calls": msg.get("tool_calls"),
    }


def main() -> None:
    models = loaded_models()
    print("loaded models:", models)
    if not models:
        print("no model loaded in LM Studio")
        return

    for model in models:
        for msg in ["Открой блокнот", "Open notepad"]:
            r = try_model(model, msg)
            if "error" in r:
                print(f"  {model} | {msg!r} -> {r['error']}")
            else:
                has = bool(r["tool_calls"])
                print(f"  {model} | {msg!r} -> tool_calls={'YES' if has else 'no'}")
                if has:
                    print(f"      {json.dumps(r['tool_calls'], ensure_ascii=False)[:200]}")
                elif r["content"]:
                    print(f"      content: {r['content'].encode('ascii', 'backslashreplace').decode()}")


if __name__ == "__main__":
    main()