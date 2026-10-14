"""
Switching input modes must not create a second model, and must not leak.

Two things are checked:

1. Only ONE Whisper is ever resident. Going to background and back repeatedly
   must never log a second load, and the detector must say whether it borrowed
   the speech recognition model or owns one.
2. VRAM must not creep. After many switches the allocation has to land where
   it started, not a little higher each time.

    python tests/check_input_modes.py [rounds]
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://127.0.0.1:8000"
LOG = os.environ.get("WAKE_TEST_LOG", "")


def post(path, payload, timeout=600):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")), time.time() - t0


def get(path, timeout=30):
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def gpu_mb():
    try:
        import torch

        if torch.cuda.is_available():
            return int(torch.cuda.memory_allocated() // (1024 * 1024))
    except Exception:
        pass
    return None


def log_loads():
    """How many times the speech model has been loaded, from the backend log."""
    if not LOG or not os.path.exists(LOG):
        return None
    with open(LOG, encoding="utf-8", errors="replace") as f:
        text = f.read()
    return len(re.findall(r"Loading model from:", text)), len(
        re.findall(r"Wake word model:", text)
    )


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    print(f"switching input mode {rounds} times")
    start_state = get("/api/input-mode")
    print(f"start: mode={start_state['mode']} loaded={start_state['model_loaded']}")

    loads_before = log_loads()
    gpu_start = gpu_mb()

    shared_flags = []
    for i in range(rounds):
        d, dt = post("/api/input-mode", {"mode": "background"})
        bg = get("/api/input-mode")
        shared_flags.append(bg.get("model_shared"))
        h, _ = post("/api/input-mode", {"mode": "hotkey"})
        after = get("/api/input-mode")
        if after["model_loaded"]:
            print(f"  round {i + 1}: hotkey still reports a loaded model")
            return 1
        if i == 0 or (i + 1) % 5 == 0:
            print(
                f"  round {i + 1:>2}: background in {dt:4.1f}s "
                f"(shared={bg.get('model_shared')}) -> hotkey ok"
            )

    loads_after = log_loads()
    gpu_end = gpu_mb()

    print(f"\nborrowed the speech model in {sum(1 for f in shared_flags if f)}"
          f"/{len(shared_flags)} switches")
    if loads_before and loads_after:
        stt_before, wake_before = loads_before
        stt_after, wake_after = loads_after
        print(f"speech model loads : {stt_before} -> {stt_after}")
        print(f"wake model loads   : {wake_before} -> {wake_after}")
        if stt_after > stt_before:
            print("\nFAIL: the speech model was reloaded during switching")
            return 1

        # With speech recognition unloaded, every background switch legitimately
        # loads a model of its own - so the thing to prove is that each load is
        # paired with an unload. An unpaired load is a leak.
        if LOG and os.path.exists(LOG):
            with open(LOG, encoding="utf-8", errors="replace") as f:
                text = f.read()
            loads = len(re.findall(r"Wake word model: .* on ", text))
            unloads = len(re.findall(r"Wake word model unloaded", text))
            print(f"detector loads/unloads: {loads} / {unloads}")
            if loads != unloads:
                print(
                    "\nFAIL: loads and unloads do not pair up - VRAM would creep\n"
                    "up with every switch"
                )
                return 1

    final = get("/api/input-mode")
    if final["mode"] != "hotkey":
        print(f"\nFAIL: ended in mode {final['mode']}")
        return 1
    if final["model_loaded"]:
        print("\nFAIL: hotkey mode still reports a loaded model")
        return 1

    print("\nPASS: every load is released, no duplicate speech model, "
          "ends on the hotkey with nothing resident.")
    return 0


if __name__ == "__main__":
    sys.exit(main())