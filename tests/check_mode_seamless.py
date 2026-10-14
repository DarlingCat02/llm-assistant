"""
The seamless path: with the speech model already loaded, entering background
mode must borrow it instead of loading a second copy.

That is the whole point of unifying the model setting - switching modes should
cost nothing when the weights are already in VRAM.

    python tests/check_mode_seamless.py
"""

import io
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://127.0.0.1:8000"
LOG = os.environ.get("WAKE_TEST_LOG", "")


def post_json(path, payload, timeout=600):
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


def log_since(marker_index):
    if not LOG or not os.path.exists(LOG):
        return ""
    with open(LOG, encoding="utf-8", errors="replace") as f:
        return f.read()[marker_index:]


def log_size():
    if not LOG or not os.path.exists(LOG):
        return 0
    return os.path.getsize(LOG)


def wav_bytes(seconds=0.5, rate=16000):
    import numpy as np
    import soundfile as sf

    t = np.linspace(0, seconds, int(seconds * rate), endpoint=False)
    tone = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, tone, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def upload_stt():
    """One recognition request, which loads the speech model."""
    import uuid

    boundary = uuid.uuid4().hex
    payload = wav_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="t.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{API}/api/stt", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    post_json("/api/input-mode", {"mode": "hotkey"})
    time.sleep(0.5)

    mark = log_size()
    print("loading the speech model with one recognition request...")
    t0 = time.time()
    res = upload_stt()
    print(f"  done in {time.time() - t0:.1f}s -> {res}")

    own = len(re.findall(r"Loading model from:", log_since(mark)))
    print(f"  'Loading model from:' occurrences: {own}")
    if own != 1:
        print("\nFAIL: expected exactly one speech model load")
        return 1

    mark = log_size()
    print("\nswitching to background...")
    _, dt = post_json("/api/input-mode", {"mode": "background"})
    state = get("/api/input-mode")
    tail = log_since(mark)

    borrowed = "reuses the speech recognition model" in tail
    own_loads = len(re.findall(r"Wake word model:", tail))

    print(f"  took {dt:.1f}s")
    print(f"  model_shared reported : {state.get('model_shared')}")
    print(f"  borrowed in the log   : {borrowed}")
    print(f"  wake model own loads  : {own_loads}")

    if not borrowed or own_loads:
        print("\nFAIL: the detector loaded a second copy instead of borrowing")
        return 1

    mark = log_size()
    print("\nswitching back to hotkey...")
    post_json("/api/input-mode", {"mode": "hotkey"})
    tail = log_since(mark)
    released_only = "released its borrowed model" in tail
    unloaded = "Wake word model unloaded" in tail
    print(f"  released without unloading: {released_only}")
    print(f"  wrongly unloaded it       : {unloaded}")

    if not released_only or unloaded:
        print("\nFAIL: switching back took the shared model away from recognition")
        return 1

    print("\nPASS: background mode borrowed the model, and gave it back intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())