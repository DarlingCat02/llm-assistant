"""
Switching speech synthesis off and on again must cost the same both times.

Found by the user: the first switch-on settled at 1937 MB, but switching off
and on again left 1.5 GB more. enable_omnivoice applies the saved voice config
while loading, so by the time it returns the transcription copy has already
done its job in cloning mode too - and it was being kept there anyway.

    python tests/check_tts_reswitch.py <reference-audio>
"""

import json
import sys
import time
import urllib.request

API = "http://127.0.0.1:8000"


def get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, payload, timeout=900):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def speak():
    req = urllib.request.Request(
        f"{API}/api/tts/speak",
        data=json.dumps({"text": "Проверка повторного включения."}).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        return len(r.read()), time.time() - t0


def cycle(label, ref):
    t0 = time.time()
    post("/api/tts/toggle", {"enabled": True})
    load = time.time() - t0
    s = get("/api/gpu-memory")
    nbytes, spoke = speak()
    after_speak = get("/api/gpu-memory")
    print(f"  {label}: loaded in {load:.1f}s -> {s['allocated_mb']} MB, "
          f"after speaking {after_speak['allocated_mb']} MB, "
          f"speech {spoke:.1f}s / {nbytes} bytes")
    return after_speak["allocated_mb"]


def main():
    ref = sys.argv[1]

    print("clearing everything first...")
    post("/api/models/release", {"what": "all"})
    time.sleep(3)

    print("\nsetting the voice to cloning (this is the mode that was leaking)")
    post("/api/tts/toggle", {"enabled": True})
    post("/api/tts/config", {"mode": "clone", "ref_audio": ref})
    speak()
    post("/api/tts/toggle", {"enabled": False})
    time.sleep(3)
    get("/api/gpu-memory")

    print("\nnow two switch-on rounds in a row:")
    first = cycle("1st", ref)
    post("/api/tts/toggle", {"enabled": False})
    time.sleep(4)
    released = get("/api/gpu-memory")
    print(f"  after switching off: {released['allocated_mb']} MB")
    second = cycle("2nd", ref)

    print()
    drift = second - first
    if abs(drift) > 150:
        print(f"FAIL: the second switch-on costs {drift:+d} MB more than the first")
        return 1
    if released["allocated_mb"] > 150:
        print(f"FAIL: {released['allocated_mb']} MB still in use after switching off")
        return 1

    print(f"PASS: both switch-ons settled at {first} / {second} MB "
          f"(drift {drift:+d} MB).")
    return 0


if __name__ == "__main__":
    sys.exit(main())