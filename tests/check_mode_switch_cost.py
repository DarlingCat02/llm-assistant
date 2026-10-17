"""
Switching from instruct to cloning must not cost a third model.

The extra Whisper inside OmniVoice is dropped on load because instruct mode
never uses it. Without putting it back, switching to cloning left the engine
to fetch a model of its own: the same 1.5 GB by another route, about 3 s
slower, and no cache.

This walks the exact sequence that used to be expensive.

    python tests/check_mode_switch_cost.py <reference-audio>
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


def speak(text):
    req = urllib.request.Request(
        f"{API}/api/tts/speak", data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        return len(r.read()), time.time() - t0


def main():
    ref = sys.argv[1]

    print("1. clearing any resident models")
    post("/api/models/release", {"what": "all"})
    time.sleep(3)
    s = get("/api/gpu-memory")
    print(f"   allocated {s['allocated_mb']} MB")

    print("\n2. turning speech on in instruct mode")
    t0 = time.time()
    post("/api/tts/toggle", {"enabled": True})
    print(f"   took {time.time() - t0:.1f}s")
    s = get("/api/gpu-memory")
    print(f"   allocated {s['allocated_mb']} MB, extra copy resident: "
          f"{s['tts_extra_whisper_loaded']}")
    baseline = s["allocated_mb"]

    print("\n3. switching to cloning (the step that used to be expensive)")
    t0 = time.time()
    post("/api/tts/config", {"mode": "clone", "ref_audio": ref})
    switch = time.time() - t0
    s = get("/api/gpu-memory")
    print(f"   took {switch:.1f}s")
    print(f"   allocated {s['allocated_mb']} MB (instruct used {baseline} MB)")
    print(f"   extra copy resident now: {s['tts_extra_whisper_loaded']}")

    print("\n4. synthesising with the clone")
    nbytes, took = speak("Проверка клонирования после смены режима.")
    s = get("/api/gpu-memory")
    print(f"   {nbytes} bytes in {took:.1f}s")
    print(f"   allocated {s['allocated_mb']} MB")

    ok = True
    if s["allocated_mb"] > baseline + 400:
        print(f"\nFAIL: a third model stayed resident "
              f"(+{s['allocated_mb'] - baseline} MB)")
        ok = False
    if s["tts_extra_whisper_loaded"]:
        print("\nFAIL: the transcription copy was not released afterwards")
        ok = False
    if took > 12:
        print(f"\nFAIL: the first clone took {took:.1f}s - the cache did not fill")
        ok = False
    if nbytes < 1000:
        print("\nFAIL: no audio came out")
        ok = False

    print()
    print("PASS: switching to cloning stayed lean and fast." if ok
          else "FAIL: see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())