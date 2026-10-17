"""
How long does each part of TTS loading take, and how much memory does it hold?

The point is to decide between two fixes for the same waste:

  A) unload the extra Whisper copy OmniVoice loads, after it did its job
  B) hand OmniVoice the speech recognition model instead of loading its own

B is only worth its extra machinery if the copy costs real time and real
VRAM. This measures both, from the timestamps the engine already logs, so the
decision rests on numbers instead of on reading the code.

Needs a running backend and the path to its log.

    python tests/check_tts_load.py <log-file> [--mode both|off|on]
"""

import io
import json
import os
import re
import sys
import threading
import time
import urllib.request

API = "http://127.0.0.1:8000"
MB = 1024 * 1024

T_START = "Loading OmniVoice model:"
T_OMNI_DONE = "OmniVoice model loaded on"
T_W_START = "Loading local Whisper for caching:"
T_W_DONE = "Local Whisper loaded for caching"
T_UNLOADED = "OmniVoice model unloaded from memory"


def post(path, payload, timeout=900):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path, timeout=30):
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def log_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def read_from(path, offset):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        return f.read()


TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}")


def stamp(line):
    m = TS.match(line)
    if not m:
        return None
    try:
        from datetime import datetime

        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        return None


def moments(text):
    """Timestamp of each marker line we care about."""
    found = {}
    for line in text.splitlines():
        for key, needle in (("start", T_START), ("w_start", T_W_START),
                            ("w_done", T_W_DONE), ("omni_done", T_OMNI_DONE),
                            ("unloaded", T_UNLOADED)):
            if needle in line and key not in found:
                found[key] = stamp(line)
    return {k: v for k, v in found.items() if v is not None}


class Watcher(threading.Thread):
    """Polls /api/gpu-memory while the backend is loading, to catch the peak."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.samples = []
        self.errors = 0

    def run(self):
        while not self.stop.is_set():
            try:
                self.samples.append(get("/api/gpu-memory"))
            except Exception:
                self.errors += 1
            self.stop.wait(0.4)


def fmt(v):
    return "-" if v is None else f"{v}"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    log = sys.argv[1]
    mode = "both"
    if "--mode" in sys.argv:
        mode = sys.argv[sys.argv.index("--mode") + 1]

    print("checking the backend is up...")
    before = get("/api/gpu-memory")
    print(f"  input mode      : {before['input_mode']}")
    print(f"  stt loaded      : {before['stt_loaded']}")
    print(f"  tts loaded      : {before['tts_loaded']}")
    print(f"  ours allocated  : {fmt(before['allocated_mb'])} MB")
    print(f"  vram free       : {fmt(before['vram_free_mb'])} MB "
          f"of {fmt(before['vram_total_mb'])} MB")

    if before["tts_loaded"]:
        print("\nTTS is already loaded - turning it off for a clean run.")
        post("/api/tts/toggle", {"enabled": False})
        time.sleep(3)

    offset = log_size(log)
    base = get("/api/gpu-memory")

    print(f"\nturning TTS on (mode={mode}), watching memory...")
    watcher = Watcher()
    watcher.start()
    t0 = time.time()
    result = post("/api/tts/toggle", {"enabled": True, "mode": mode})
    elapsed = time.time() - t0
    time.sleep(2)
    watcher.stop.set()
    watcher.join(timeout=5)

    loaded = get("/api/gpu-memory")
    text = read_from(log, offset)
    m = moments(text)

    print(f"  request returned in {elapsed:.1f}s -> {json.dumps(result)[:120]}")

    alloc = [s["allocated_mb"] for s in watcher.samples if s.get("allocated_mb")]
    peak = max(alloc) if alloc else None

    print("\n--- time, from the engine's own log timestamps ---")
    omni = None
    whisper = None
    if "start" in m and "omni_done" in m:
        omni = m["omni_done"] - m["start"]
        print(f"  OmniVoice model      : {omni:>4} s")
    if "w_start" in m and "w_done" in m:
        whisper = m["w_done"] - m["w_start"]
        print(f"  extra Whisper copy   : {whisper:>4} s")
    if omni and whisper:
        pct = whisper * 100 // omni
        print(f"  share of the load    : {pct}%")
    if not omni:
        print("  (no load markers found - was it already loaded?)")

    print("\n--- memory ---")
    print(f"  ours before TTS      : {fmt(base['allocated_mb'])} MB")
    print(f"  peak while loading   : {fmt(peak)} MB")
    print(f"  ours with TTS loaded : {fmt(loaded['allocated_mb'])} MB")
    if base.get("allocated_mb") is not None and loaded.get("allocated_mb") is not None:
        delta = loaded["allocated_mb"] - base["allocated_mb"]
        print(f"  TTS costs            : {delta} MB")
    print(f"  extra Whisper copy   : "
          f"{'loaded' if loaded['tts_extra_whisper_loaded'] else 'absent'}")
    if watcher.errors:
        print(f"  (poll errors: {watcher.errors})")

    print("\nturning TTS off again...")
    post("/api/tts/toggle", {"enabled": False})
    time.sleep(4)
    after = get("/api/gpu-memory")
    print(f"  ours after unload    : {fmt(after['allocated_mb'])} MB")
    print(f"  returned to baseline : "
          f"{'yes' if base.get('allocated_mb') == after.get('allocated_mb') else 'NO'}")

    if whisper is not None and whisper > 10:
        print("\nVERDICT: the copy costs over 10 s - worth sharing the model (path B).")
    elif whisper is not None:
        print("\nVERDICT: the copy is cheap to load - unloading it is enough (path A).")
    else:
        print("\nVERDICT: not measured, run against a backend that actually loads TTS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())