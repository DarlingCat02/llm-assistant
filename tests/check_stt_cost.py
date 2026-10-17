"""
What does speech recognition cost, and what does releasing it cost?

Same question as check_cache_cost.py, for the recognition model: how long the
load takes, how much VRAM it holds, and whether handing the memory back makes
the next load slow again.

    python tests/check_stt_cost.py <log-file>
"""

import io
import json
import os
import re
import sys
import time
import urllib.request
import uuid

API = "http://127.0.0.1:8000"


def get(path, timeout=30):
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, payload, timeout=600):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def line(label, s):
    print(f"  {label:<24} allocated {s['allocated_mb']:>5} MB | "
          f"reserved {s['reserved_mb']:>5} MB | free {s['vram_free_mb']:>5} MB | "
          f"stt_loaded {str(s['stt_loaded']):>5}")


def wav():
    import numpy as np
    import soundfile as sf

    buf = io.BytesIO()
    t = np.linspace(0, 0.5, 8000, endpoint=False)
    sf.write(buf, (0.1 * np.sin(2 * 3.14159 * 220 * t)).astype("float32"),
             16000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def stt():
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="t.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n").encode() + wav() + \
           f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{API}/api/stt", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode("utf-8")), time.time() - t0


def main():
    log = sys.argv[1]
    if get("/api/gpu-memory")["wake_running"]:
        print("background mode is on - it holds the recognition model.")
        return 2

    print("1. first recognition (loads the model)")
    before = get("/api/gpu-memory")
    line("before", before)
    res, took = stt()
    line("after recognition", get("/api/gpu-memory"))
    print(f"  took {took:.1f}s -> {str(res.get('text',''))[:40]!r}")

    print("\n2. release, then recognise again")
    freed = post("/api/gpu-memory/release", {})
    line("after release", freed)
    print(f"  handed back: {freed.get('freed_mb')} MB "
          f"(note: the model itself is still loaded)")

    print("\n3. what the model actually costs")
    s = get("/api/gpu-memory")
    print(f"  stt_loaded: {s['stt_loaded']}, shared with wake: {s['stt_shared_with_wake']}")
    print(f"  allocated now: {s['allocated_mb']} MB")

    with io.open(log, encoding="utf-8", errors="replace") as f:
        tail = f.read()[-6000:]
    loads = len(re.findall(r"Loading model from:", tail))
    print(f"  'Loading model from:' occurrences in the recent log: {loads}")
    if loads > 1:
        print("  WARNING: the model was loaded more than once")
    print("\nNOTE: releasing the cache does NOT unload the recognition model -")
    print("that needs the explicit release endpoint (step 4 of the plan).")
    return 0


if __name__ == "__main__":
    sys.exit(main())