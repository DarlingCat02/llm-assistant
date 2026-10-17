"""
Voice cloning must survive the extra Whisper copy being dropped.

The copy is what transcribes a voice sample. Dropping it is only safe because
the engine falls back to transcribing by itself (ref_text=None, FFmpeg auto) -
so this sets a real voice, drops the copy, and then clones with it. If the
fallback were wrong, synthesis would fail or return silence.

    python tests/check_clone_after_drop.py <reference-audio>
"""

import io
import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"
TEXT = "Это проверка клонирования голоса."


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
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            body = r.read()
            return r.status, len(body), time.time() - t0
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        return e.code, 0, time.time() - t0, detail


def main():
    ref = sys.argv[1]

    print("1. making sure synthesis is on")
    if not get("/api/gpu-memory")["tts_loaded"]:
        post("/api/tts/toggle", {"enabled": True})
        time.sleep(2)

    print("\n2. setting the voice to clone")
    r = post("/api/tts/config", {"mode": "clone", "ref_audio": ref})
    print(f"   applied={r.get('applied')}  error={r.get('error')}")

    s = get("/api/gpu-memory")
    print(f"   extra Whisper copy: {'still resident' if s['tts_extra_whisper_loaded'] else 'dropped'}")
    print(f"   allocated: {s['allocated_mb']} MB")

    print("\n3. cloning with the copy already dropped")
    out = speak(TEXT)
    status, nbytes, took = out[0], out[1], out[2]
    if len(out) > 3:
        print(f"   FAILED: HTTP {status} - {out[3]}")
        return 1
    print(f"   HTTP {status}, {nbytes} bytes in {took:.1f}s")

    if status != 200 or nbytes < 1000:
        print("\nFAIL: cloning produced nothing usable")
        return 1

    print("\n4. and once more, to prove it is not a one-off")
    status2, nbytes2, _ = speak(TEXT)
    print(f"   HTTP {status2}, {nbytes2} bytes")

    ok = status == 200 and nbytes > 1000 and status2 == 200 and nbytes2 > 1000
    print("\n" + ("PASS: cloning works without the extra Whisper copy."
                  if ok else "FAIL: cloning broke."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())