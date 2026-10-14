"""
Does the model stop calling tools once the chat already contains the exchange?

In the chat where 'открой блокнот' was already answered with 'Блокнот
открыт', the model repeats the answer instead of calling app_open - while a
fresh chat calls it. That would explain "it says notepad is open but nothing
opens", and it is a context problem, not a tool-calling problem.

    python tests/check_tool_repeat.py
"""

import json
import sys
import time
import urllib.request

API = "http://127.0.0.1:8000"
MESSAGE = "открой блокнот"


def chat(message, chat_id):
    body = json.dumps({"message": message, "chat_id": chat_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/api/chat", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8")), time.time() - t0


def report(tag, data, dt):
    actions = data.get("actions") or []
    ran = [a for a in actions if a.get("ok")]
    print(f"  {tag:<28} {dt:5.1f}s  tools={len(actions)} ok={len(ran)}  "
          f"reply={str(data.get('response'))[:40]!r}")
    return bool(ran)


print(f"{MESSAGE!r}\n")
print("fresh chat:")
data, dt = chat(MESSAGE, None)
cid = data.get("chat_id")
first = report("turn 1", data, dt)

print(f"\nsame chat (id={cid}), asking again:")
data2, dt2 = chat(MESSAGE, cid)
second = report("turn 2", data2, dt2)

data3, dt3 = chat(MESSAGE, cid)
third = report("turn 3", data3, dt3)

print()
if first and not (second or third):
    print("CONFIRMED: the first request in a chat calls the tool, later identical\n"
          "requests in the same chat stop calling it - the model copies its own\n"
          "previous answer instead.")
    sys.exit(0)
if first and second and third:
    print("not reproduced: every turn called the tool")
    sys.exit(0)
print("FAIL: even the first request did not call the tool")
sys.exit(1)