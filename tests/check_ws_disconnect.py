"""
Does the backend survive a WebSocket client vanishing?

Regression: the global handler caught WebSocketDisconnect with a bare
`except Exception: continue`. Disconnect is a subclass of Exception, so the
loop spun forever at full CPU and the whole event loop starved - the backend
stopped answering even plain HTTP.

    python tests/check_ws_disconnect.py
"""

import asyncio
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/events"
ROUNDS = 5


def http_alive(timeout=8):
    """Is the backend still serving plain HTTP?"""
    try:
        with urllib.request.urlopen(f"{API}/api/status", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


async def connect_and_drop():
    """Connect, then drop the socket the way a closing tab does."""
    import websockets

    for i in range(ROUNDS):
        ws = await websockets.connect(WS_URL, open_timeout=10)
        # Abrupt close: no close frame, no farewell.
        ws.transport.abort()
        try:
            await ws.wait_closed()
        except Exception:
            pass
        print(f"  round {i + 1}: connected then aborted")
        await asyncio.sleep(0.4)


async def run():
    if not http_alive():
        print("FAIL: backend was not answering before the test")
        return 1

    print(f"aborting the socket {ROUNDS} times...")
    await connect_and_drop()
    await asyncio.sleep(1.0)

    # The real question: does HTTP still work afterwards?
    for attempt in range(10):
        if http_alive():
            print(f"\nPASS: backend still answers after {ROUNDS} aborted sockets")
            return 0
        await asyncio.sleep(1.0)

    print(f"\nFAIL: backend stopped answering after {ROUNDS} aborted sockets")
    return 1


def main():
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("needs 'websockets' in the venv to run this check")
        return 2
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())