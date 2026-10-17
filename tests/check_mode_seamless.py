"""
The seamless path: with the speech model already loaded, entering background
mode must borrow it instead of loading a second copy.

That is the whole point of unifying the model setting - switching modes should
cost nothing when the weights are already in VRAM.

Judged on what the app reports, not on the log: when stderr is redirected to a
file it is block-buffered, so log lines can lag the response by minutes and
"no load line found" means nothing.

    python tests/check_mode_seamless.py
"""

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://127.0.0.1:8000"
MB = 1024 * 1024


def post(path, payload, timeout=600):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")), time.time() - t0


def get(path, timeout=60):
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def release_stt():
    """Get to a known-cold state, waiting for the memory to actually drop."""
    for attempt in range(1, 6):
        post("/api/models/release", {"what": "stt"})
        mem = get("/api/gpu-memory")
        if mem["allocated_mb"] < 100:
            return mem
        time.sleep(1.5)
    return get("/api/gpu-memory")


def upload_stt():
    import io
    import uuid

    import numpy as np
    import soundfile as sf

    t = np.linspace(0, 0.5, 8000, endpoint=False)
    tone = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, tone, 16000, format="WAV", subtype="PCM_16")

    b = uuid.uuid4().hex
    body = (f"--{b}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="t.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n").encode() + buf.getvalue() + \
           f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(
        f"{API}/api/stt", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode("utf-8"))


def fail(msg):
    print(f"\nFAIL: {msg}")
    return 1


def main():
    post("/api/input-mode", {"mode": "hotkey"})
    time.sleep(0.5)

    print("getting to a cold state...")
    cold = release_stt()
    print(f"  allocated {cold['allocated_mb']} MB, stt_loaded={cold['stt_loaded']}")
    if cold["allocated_mb"] >= 100:
        return fail("could not get the recognition model out of memory")

    print("\nloading the speech model with one recognition request...")
    t0 = time.time()
    res = upload_stt()
    loaded = get("/api/gpu-memory")
    print(f"  took {time.time() - t0:.1f}s -> {res.get('text', '')!r}")
    print(f"  allocated {loaded['allocated_mb']} MB, stt_loaded={loaded['stt_loaded']}")
    if not loaded["stt_loaded"]:
        return fail("the model did not load")

    base_mb = loaded["allocated_mb"]
    post("/api/models/release", {"what": "tts"})   # keep TTS out of the way

    print("\nswitching to background...")
    _, dt = post("/api/input-mode", {"mode": "background"})
    bg = get("/api/input-mode")
    bg_mem = get("/api/gpu-memory")
    print(f"  took {dt:.1f}s")
    print(f"  model_shared: {bg.get('model_shared')}")
    print(f"  allocated {bg_mem['allocated_mb']} MB (was {base_mb} MB before switching)")

    if not bg.get("model_shared"):
        return fail("the detector did not borrow the recognition model")
    grown = bg_mem["allocated_mb"] - base_mb

    if not bg.get("model_shared"):
        return fail("the detector did not borrow the recognition model")
    grown = bg_mem["allocated_mb"] - base_mb
    if grown > 200:
        return fail(f"a second copy was loaded: +{grown} MB")

    print("\nswitching back to hotkey...")
    post("/api/input-mode", {"mode": "hotkey"})
    back = get("/api/gpu-memory")
    print(f"  stt_loaded: {back['stt_loaded']} (the model must survive)")
    print(f"  allocated {back['allocated_mb']} MB")
    if not back["stt_loaded"]:
        return fail("switching back took the recognition model away")

    print("\nPASS: background mode borrowed the model and gave it back intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())