"""
What happens to the backend and to wake-word while OmniVoice loads?

The user reports the TTS switch greying out and the two features not working
at the same time. This watches the backend and the wake detector throughout a
full load/unload cycle.

    python tests/check_tts_wake_parallel.py
"""

import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://127.0.0.1:8000"


def get(path, timeout=10):
    t0 = time.time()
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
            return time.time() - t0, json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return time.time() - t0, {"error": type(e).__name__}


def post(path, payload, timeout=600):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}", data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return time.time() - t0, json.loads(r.read().decode("utf-8"))


def gpu_mb():
    try:
        import torch

        if torch.cuda.is_available():
            return f"{torch.cuda.memory_allocated() / 1024 ** 2:.0f} MB"
    except Exception:
        pass
    return "n/a"


def main():
    print(f"{'t':>6}  {'status ms':>9}  {'wake ms':>8}  listening  blocks  gpu")
    print("-" * 62)

    stop = threading.Event()
    samples = []
    base_blocks = None

    def poll():
        nonlocal base_blocks
        while not stop.is_set():
            sdt, s = get("/api/status", timeout=8)
            wdt, w = get("/api/wake-word", timeout=8)
            blocks = w.get("blocks_read", 0)
            if base_blocks is None and w.get("listening"):
                base_blocks = blocks
            samples.append((sdt, wdt, w.get("listening"), blocks, w.get("error")))
            time.sleep(2)

    t = threading.Thread(target=poll, daemon=True)
    t.start()
    time.sleep(3)

    print("\n-- enabling TTS --")
    dt, res = post("/api/tts/toggle", True)
    print(f"   took {dt:.1f}s, loaded={res.get('omnivoice_loaded')}, err={res.get('error')}")
    time.sleep(2)

    print("\n-- TTS on, sampling 12s --")
    time.sleep(12)

    print("\n-- disabling TTS --")
    dt, res = post("/api/tts/toggle", False)
    print(f"   took {dt:.1f}s")
    time.sleep(4)

    stop.set()
    t.join(timeout=5)

    slow_status = [s for s in samples if s[0] > 2.0]
    slow_wake = [s for s in samples if s[1] > 2.0]
    errors = [s for s in samples if s[4]]
    not_listening = [s for s in samples if s[2] is False]
    blocks_moving = len({s[3] for s in samples}) > 3

    print(f"\nsamples                : {len(samples)}")
    print(f"wake stopped listening : {len(not_listening)}")
    print(f"wake errors            : {len(errors)}")
    print(f"/api/status over 2s    : {len(slow_status)}")
    print(f"/api/wake-word over 2s : {len(slow_wake)}")
    print(f"audio blocks advancing : {blocks_moving}")
    print(f"local gpu allocation   : {gpu_mb()}")

    if not_listening or errors or slow_wake:
        print("\nFAIL: the wake word or the API stalled during TTS operations")
        return 1
    print("\nPASS: wake word and the API stayed responsive throughout")
    return 0


if __name__ == "__main__":
    sys.exit(main())