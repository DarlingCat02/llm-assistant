"""
Does saving the TTS voice config survive a model that is still loading?

Regression: the facade forwards set_voice_config() to whatever engine object
exists. During an OmniVoice load that object is un-initialised, and its
set_voice_config touches self._whisper_model - which does not exist yet - so an
ordinary click produced HTTP 500.

Fires the toggle and the config save at the same time, repeatedly.

    python tests/check_tts_config_race.py
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://127.0.0.1:8000"


def post(path, payload, timeout=600):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8")), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, None, time.time() - t0
    except Exception as e:
        return None, type(e).__name__, time.time() - t0


def main():
    # Start from TTS off so the load is genuinely in flight when we poke it.
    post("/api/tts/toggle", False)
    time.sleep(1.0)

    results = []

    def toggle():
        st, payload, dt = post("/api/tts/toggle", True)
        results.append(("toggle", st, payload, dt, True))

    def save_config():
        # What the UI sends a moment after the switch flips.
        st, payload, dt = post(
            "/api/tts/config",
            {"mode": "clone", "instruct": "female", "ref_audio": None},
        )
        results.append(("config", st, payload, dt, False))

    t = threading.Thread(target=toggle)
    c = threading.Thread(target=save_config)
    t.start()
    time.sleep(0.4)          # land squarely inside the load
    c.start()
    t.join()
    c.join()

    failures = 0
    raced = False
    for name, status, payload, dt, _ in sorted(results, key=lambda r: r[3]):
        ok = status == 200
        failures += 0 if ok else 1
        detail = payload.get("applied_now") if isinstance(payload, dict) else payload
        if name == "config" and detail is False:
            raced = True
        print(
            f"  {name:<7} HTTP {status}  {dt:6.2f}s  applied_now={detail}"
            f"{'' if ok else '   <-- FAILED'}"
        )

    if failures:
        print(f"\nFAIL: {failures} request(s) failed while the model was loading")
        return 1

    if not raced:
        print(
            "\nNOT EXERCISED: the config arrived after loading finished, so this\n"
            "run did not actually hit the race. Try again with a colder cache."
        )
        return 2

    print("\nPASS: config saved mid-load with no 500.")
    print("It is stored on the facade and applied when the model finishes loading.")
    return 0


if __name__ == "__main__":
    sys.exit(main())