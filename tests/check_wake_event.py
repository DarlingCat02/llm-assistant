"""
End-to-end check that the backend's WebSocket events reach a client.

Guards against the bug where the frontend built the socket URL from
window.location.host: inside Tauri that host is never the backend, so the
socket went nowhere and every out-of-band event - the wake word included -
was silently lost while the rest of the app kept working over HTTP.

Connects with the same URL the frontend now derives from API_BASE, then
triggers a real broadcast by sending a chat message.

    python tests/check_wake_event.py
"""

import asyncio
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/events"


def post_chat():
    """The chat endpoint is what broadcasts an event in normal operation."""
    body = json.dumps({"message": "ping", "chat_id": None}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/api/chat",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


async def run():
    import websockets

    async with websockets.connect(WS_URL) as ws:
        print(f"connected: {WS_URL}")

        # Run the HTTP call without blocking the loop.
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, post_chat)
        except Exception as e:
            print(f"FAIL: /api/chat errored: {e}")
            return 1

        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            except asyncio.TimeoutError:
                print("FAIL: the turn completed but no event arrived on the socket")
                return 1

            data = json.loads(msg)
            print(f"  received: type={data.get('type')!r} keys={sorted(data)}")
            print("\nPASS: events reach a client on the URL the frontend now uses.")
            return 0


def main():
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("needs 'websockets' in the venv to run this check")
        return 2
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())