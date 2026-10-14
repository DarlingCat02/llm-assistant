"""
Does the assistant still call a tool in a chat it has already polluted?

Regression: chat 62 accumulated a dozen 'открой блокнот' -> 'Блокнот открыт.'
pairs with no tool ever invoked. Seeing that pattern, the model kept answering
in the same words and never called app_open - so it claimed success while
nothing happened, and the claim got copied forward into every later turn.

This sends the same command to that polluted chat and to a fresh one.

    python tests/check_tool_polluted_chat.py [chat_id]
"""

import json
import sys
import urllib.request

API = "http://127.0.0.1:8000"
CHAT = int(sys.argv[1]) if len(sys.argv) > 1 else 62
MESSAGE = "открой блокнот"


def chat(message, chat_id):
    body = json.dumps({"message": message, "chat_id": chat_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/api/chat", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def ran_tools(data):
    return [a for a in (data.get("actions") or []) if a.get("ok")]


def main():
    msgs = json.load(urllib.request.urlopen(f"{API}/api/chats/{CHAT}/messages", timeout=30))
    print(f"chat {CHAT} holds {len(msgs)} messages")

    print(f"\n{MESSAGE!r}")
    for label, cid in ((f"polluted chat {CHAT}", CHAT), ("fresh chat", None)):
        data = chat(MESSAGE, cid)
        tools = ran_tools(data)
        verdict = "TOOL RAN" if tools else "NO TOOL (claims success anyway?)"
        print(f"  {label:<20} tools={len(tools)}  verdict={verdict}")

    polluted = ran_tools(chat(MESSAGE, CHAT))
    if not polluted:
        print(
            "\nFAIL: the polluted chat still swallows the tool call.\n"
            "The assistant says the app opened while nothing happened."
        )
        return 1

    print("\nPASS: the polluted chat calls the tool again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())