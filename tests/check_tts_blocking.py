"""
Does enabling TTS block the whole backend?

enable_omnivoice() is async but does only blocking work (from_pretrained on a
3 GB model, ensure_ffmpeg, ...). Nothing ever yields to the event loop, so
the load runs on the loop thread. This measures what a plain HTTP request
feels like while the model is loading.

    python tests/check_tts_blocking.py
"""

import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://127.0.0.1:8000"


def get(path, timeout=60):
    t0 = time.time()
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
            r.read()
        return time.time() - t0, None
    except Exception as e:
        return time.time() - t0, str(e)[:60]


def main():
    base, err = get("/api/status", timeout=20)
    print(f"baseline /api/status : {base * 1000:7.0f} ms  {err or 'ok'}")
    if err:
        print("backend not reachable")
        return 1

    result = {}

    def toggle():
        t0 = time.time()
        dt, err = get("/api/tts/status", timeout=5)
        body = json.dumps(True).encode()
        req = urllib.request.Request(
            f"{API}/api/tts/toggle", data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                result["payload"] = r.read().decode("utf-8")[:200]
        except Exception as e:
            result["error"] = str(e)[:120]
        result["seconds"] = time.time() - t0
        result["done"].set()

    result["done"] = threading.Event()
    threading.Thread(target=toggle, daemon=True).start()

    print("\nprobing /api/status while TTS loads:")
    worst = 0.0
    for _ in range(12):
        if result["done"].is_set():
            break
        dt, err = get("/api/status", timeout=20)
        worst = max(worst, dt)
        flag = "  <-- BLOCKED" if dt > 1.0 else ""
        print(f"  {dt * 1000:8.0f} ms{err or ''}{flag}")
        time.sleep(2)

    result["done"].wait(timeout=600)
    print(f"\nTTS toggle finished in {result.get('seconds', 0):.1f} s")
    print(f"  payload: {result.get('payload', result.get('error'))}")
    print(f"worst /api/status during load: {worst * 1000:.0f} ms")

    if worst > 1.0:
        print(
            f"\nFAIL: a plain HTTP request stalled for {worst:.1f}s while TTS loaded.\n"
            "The model load must not run on the event loop thread - while it does,\n"
            "the whole backend is unresponsive, including the wake-word status the\n"
            "UI polls. Measured before this was fixed: 1.96 s with a warm disk\n"
            "cache and far longer on a cold load."
        )
        return 1
    print(f"\nPASS: the backend stayed responsive (worst {worst * 1000:.0f} ms) while TTS loaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())