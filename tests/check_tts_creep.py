"""
Does the leftover VRAM grow every time speech synthesis is cycled?

~790 MB stays after unloading (the OmniVoice network is held by a closure
inside that library, which we do not modify). One-off overhead is acceptable;
growth per cycle is not, and only measurement can tell the difference.

    python tests/check_tts_creep.py [cycles] <reference-audio>
"""

import io
import json
import sys
import time
import urllib.request

API = "http://127.0.0.1:8000"


def get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, payload=None, timeout=900):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def speak():
    req = urllib.request.Request(
        f"{API}/api/tts/speak",
        data=json.dumps({"text": "Проверка накопления памяти."}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        r.read()


def main():
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    ref = sys.argv[2] if len(sys.argv) > 2 else r"voices\RU_Wushu_MatchStartMap_Ascent.mp3"

    if get("/api/gpu-memory")["tts_loaded"]:
        post("/api/tts/toggle", {"enabled": False})
        time.sleep(3)
    base = get("/api/gpu-memory")
    print(f"start: {base['allocated_mb']} MB\n")

    rows = []
    for i in range(cycles):
        post("/api/tts/toggle", {"enabled": True})
        post("/api/tts/config", {"mode": "clone", "ref_audio": ref})
        speak()
        loaded = get("/api/gpu-memory")["allocated_mb"]

        post("/api/tts/toggle", {"enabled": False})
        time.sleep(3)
        post("/api/gpu-memory/release")
        time.sleep(2)
        after = get("/api/gpu-memory")["allocated_mb"]
        rows.append((loaded, after))
        print(f"  cycle {i+1}: {loaded:>5} MB loaded -> {after:>5} MB after unload")

    floor = rows[0][1]
    last = rows[-1][1]
    print(f"\n  floor after the first cycle: {floor} MB")
    print(f"  after {cycles} cycles:            {last} MB")
    drift = last - floor
    if drift > 128:
        print(f"\nFAIL: grew by {drift} MB across cycles - that is a leak")
        return 1
    print(f"\nPASS: steady at {last} MB (drift {drift:+d} MB).")
    print("The floor is what the OmniVoice library keeps alive through a closure;")
    print("it does not grow, so repeated use is safe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())