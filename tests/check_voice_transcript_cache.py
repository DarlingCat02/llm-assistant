"""
A voice sample is transcribed once, then never again.

The engine kept its transcription in memory only, so every switch-on paid for
it again - visible in the user's own log as "Transcribing reference (caching)"
appearing once per start. This walks the cycle that has to get cheaper:

  1. first use      - transcribed, saved to storage/tts_voices.json
  2. later use      - read from the file, no model loaded at all
  3. edited by hand - the edit survives
  4. file replaced  - the stale transcription is refused

    python tests/check_voice_transcript_cache.py <reference-audio>
"""

import io
import json
import os
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://127.0.0.1:8000"
STORE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "storage", "tts_voices.json")


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
        data=json.dumps({"text": "Проверка кэша транскрибации."}).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        return len(r.read()), time.time() - t0


def read_store():
    if not os.path.exists(STORE):
        return {}
    with io.open(STORE, encoding="utf-8") as f:
        return json.load(f).get("voices", {})


def round_trip(ref, label):
    """Switch off, switch on in clone mode, speak. Returns (seconds, MB)."""
    post("/api/tts/toggle", {"enabled": False})
    time.sleep(3)
    post("/api/gpu-memory/release")
    t0 = time.time()
    post("/api/tts/toggle", {"enabled": True})
    load = time.time() - t0
    post("/api/tts/config", {"mode": "clone", "ref_audio": ref})
    nbytes, spoke = speak()
    peak = get("/api/gpu-memory")["allocated_mb"]
    print(f"  {label}: load {load:.1f}s, speak {spoke:.1f}s, {nbytes} bytes, "
          f"{peak} MB resident")
    return load, spoke, peak


def main():
    ref = os.path.abspath(sys.argv[1])
    failures = []

    def check(ok, msg):
        print(f"  {'PASS' if ok else 'FAIL'}  {msg}")
        if not ok:
            failures.append(msg)

    print("1. starting with an empty store")
    if os.path.exists(STORE):
        os.remove(STORE)
    post("/api/models/release", {"what": "all"})
    post("/api/tts/toggle", {"enabled": False})
    time.sleep(2)
    check(not read_store(), "the store starts empty")

    print("\n2. first use - the sample has to be transcribed")
    first_load, _, _ = round_trip(ref, "first")
    store = read_store()
    check(len(store) == 1, f"exactly one entry was saved (got {len(store)})")
    entry = next(iter(store.values()), {})
    text = entry.get("text", "")
    check(bool(text.strip()), f"the entry has text: {text[:50]!r}")
    check(entry.get("size", 0) > 0, "the entry records the file size")

    print("\n3. second use - must not touch the model")
    second_load, _, second_peak = round_trip(ref, "second")
    check(len(read_store()) == 1, "still exactly one entry (no duplicate key)")
    check(second_peak < 2400, f"no third model resident ({second_peak} MB)")

    print("\n4. a hand-edited transcription must survive")
    edited = text + " (правка вручную)"
    key = next(iter(read_store()))
    data = json.load(io.open(STORE, encoding="utf-8"))
    data["voices"][key]["text"] = edited
    with io.open(STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    round_trip(ref, "after edit")
    now = read_store().get(key, {}).get("text", "")
    check(now == edited, f"the manual edit was not overwritten: {now[:60]!r}")
    # Put the real words back: leaving the probe's edit behind would be junk in
    # the user's voice settings.
    data = json.load(io.open(STORE, encoding="utf-8"))
    data["voices"][key]["text"] = text
    with io.open(STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("\n5. replacing the audio file must invalidate it")
    copy_path = os.path.join(os.path.dirname(ref), "_transcript_probe.mp3")
    shutil.copyfile(ref, copy_path)
    round_trip(copy_path, "copy of the sample")
    key2 = next((k for k in read_store() if "_transcript_probe" in k), None)
    check(bool(key2), "the copy got its own entry")
    time.sleep(1.1)
    with io.open(copy_path, "ab") as f:
        f.write(b"\x00" * 64)
    round_trip(copy_path, "after touching the file")
    entries = read_store()
    text_now = entries.get(key2, {}).get("text", "")
    check(text_now != edited, "the stale transcription was replaced, not reused")
    try:
        os.remove(copy_path)
    except OSError:
        pass
    if key2:
        data = json.load(io.open(STORE, encoding="utf-8"))
        data["voices"].pop(key2, None)
        with io.open(STORE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {failures}")
        return 1
    print("PASS: transcribed once, reused forever, edits kept, changes noticed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())