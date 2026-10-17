"""
Everything the memory work claims, checked against a running backend.

The measurements said unloading frees the models but leaves 3.6 GB cached, and
that the copy inside OmniVoice is only needed once. This walks the whole
chain and, most importantly, speaks after the copy was dropped - the one thing
that must not break.

    python tests/check_memory_release.py
"""

import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "http://127.0.0.1:8000"
failures = []


def get(path, timeout=60):
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, payload, timeout=900):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"__status": e.code, "detail": e.read().decode("utf-8", "replace")[:200]}


def speak(path, payload):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return r.status, len(r.read())


def stt():
    import numpy as np
    import soundfile as sf

    buf = io.BytesIO()
    t = np.linspace(0, 0.5, 8000, endpoint=False)
    sf.write(buf, (0.1 * np.sin(2 * 3.14159 * 220 * t)).astype("float32"),
             16000, format="WAV", subtype="PCM_16")
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="t.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n").encode() + buf.getvalue() + \
           f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{API}/api/stt", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode("utf-8")), time.time() - t0


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)
    return ok


def main():
    print("1. starting state")
    # Everything out first: leaving the recognition model resident would make
    # "models are gone" fail on someone else's memory, not on ours.
    post("/api/models/release", {"what": "all"})
    time.sleep(3)
    for _ in range(5):
        s = get("/api/gpu-memory")
        if s["allocated_mb"] < 100:
            break
        post("/api/models/release", {"what": "all"})
        time.sleep(2)
    print(f"   allocated {s['allocated_mb']} MB | reserved {s['reserved_mb']} MB | "
          f"tts {s['tts_loaded']} | stt {s['stt_loaded']}")
    if s["allocated_mb"] >= 100:
        print("FAIL: could not reach an empty state to measure from")
        return 1
    if s["tts_loaded"]:
        post("/api/tts/toggle", {"enabled": False})
        time.sleep(3)

    print("\n2. turning speech synthesis on (instruct mode)")
    # Instruct mode never transcribes a voice sample, so the extra Whisper is
    # dead weight there and must be dropped. Cloning keeps it on purpose - it
    # is what fills the transcription cache.
    post("/api/tts/config", {"mode": "instruct", "instruct": "female"})
    t0 = time.time()
    r = post("/api/tts/toggle", {"enabled": True})
    took = time.time() - t0
    s = get("/api/gpu-memory")
    print(f"   took {took:.1f}s -> allocated {s['allocated_mb']} MB | "
          f"reserved {s['reserved_mb']} MB")
    check("speech synthesis is loaded", bool(s["tts_loaded"]))
    check("the extra Whisper copy was dropped",
          not s["tts_extra_whisper_loaded"],
          "still resident" if s["tts_extra_whisper_loaded"] else "")

    print("\n3. speaking with the copy gone (the thing that must not break)")
    try:
        status, nbytes = speak("/api/tts/speak", {"text": "Проверка синтеза речи."})
        check("synthesis still produces audio", status == 200 and nbytes > 1000,
              f"HTTP {status}, {nbytes} bytes")
    except Exception as e:
        check("synthesis still produces audio", False, str(e)[:120])
    after = get("/api/gpu-memory")
    print(f"   allocated now {after['allocated_mb']} MB")

    print("\n4. turning speech synthesis off")
    post("/api/tts/toggle", {"enabled": False})
    time.sleep(4)
    s = get("/api/gpu-memory")
    print(f"   allocated {s['allocated_mb']} MB | reserved {s['reserved_mb']} MB | "
          f"free {s['vram_free_mb']} MB")
    check("models are gone", (s["allocated_mb"] or 0) < 100,
          f"{s['allocated_mb']} MB still in use")
    # ~800 MB stays reserved no matter what: the CUDA context and the cuBLAS
    # workspaces are allocated once and never handed back. What matters is that
    # it is a floor and not a number that grows - measured across 5 cycles with
    # zero drift.
    check("the VRAM went back to the driver", (s["reserved_mb"] or 0) < 1000,
          f"{s['reserved_mb']} MB still reserved (floor is the CUDA context)")

    print("\n5. loading the recognition model")
    res, took = stt()
    s = get("/api/gpu-memory")
    print(f"   took {took:.1f}s -> allocated {s['allocated_mb']} MB | stt {s['stt_loaded']}")
    check("recognition model is resident", bool(s["stt_loaded"]))

    print("\n6. releasing it by hand")
    r = post("/api/models/release", {"what": "stt"})
    s = get("/api/gpu-memory")
    print(f"   freed {r.get('freed_mb')} MB (reserved {r.get('freed_reserved_mb')} MB) "
          f"-> allocated {s['allocated_mb']} MB")
    check("recognition model was released", not s["stt_loaded"])
    check("its memory went back", (s["allocated_mb"] or 0) < 100,
          f"{s['allocated_mb']} MB still in use")

    print("\n7. it has to work again afterwards")
    res, took = stt()
    s = get("/api/gpu-memory")
    print(f"   took {took:.1f}s -> {str(res.get('text',''))[:40]!r}")
    check("recognition reloads after being released", bool(s["stt_loaded"]))

    print("\n8. background mode must refuse to release it")
    post("/api/input-mode", {"mode": "background"})
    time.sleep(6)
    r = post("/api/models/release", {"what": "stt"})
    s = get("/api/gpu-memory")
    print(f"   blocked={r.get('stt_blocked')} stt_loaded={s['stt_loaded']}")
    check("release is refused in background mode",
          r.get("stt_blocked") == "background" and s["stt_loaded"])
    post("/api/input-mode", {"mode": "hotkey"})
    time.sleep(3)

    print("\n9. cleaning up")
    post("/api/models/release", {"what": "all"})
    s = get("/api/gpu-memory")
    print(f"   allocated {s['allocated_mb']} MB | reserved {s['reserved_mb']} MB | "
          f"free {s['vram_free_mb']} MB")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {failures}")
        return 1
    print("PASS: models unload, memory goes back, and everything still works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())