"""
Can TTS be turned OFF while it is still loading?

The switch used to stay disabled for the whole load - tens of seconds - so it
looked frozen and could not be undone. Racing an unload against an in-flight
load would leave OmniVoice installed after the user asked for it off, so the
disable waits for the load and then unloads.

    python tests/check_tts_cancel.py
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


def post(path, payload, timeout=900):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), time.time() - t0, None
    except urllib.error.HTTPError as e:
        return None, time.time() - t0, f"HTTP {e.code}"
    except Exception as e:
        return None, time.time() - t0, type(e).__name__


def get(path, timeout=15):
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    post("/api/tts/toggle", False)
    time.sleep(1)

    load_result = {}

    def enable():
        load_result["value"] = post("/api/tts/toggle", True)

    t = threading.Thread(target=enable)
    t.start()
    time.sleep(1.0)

    mid = get("/api/tts/status")
    print(f"1s into the load: loading={mid.get('loading')} loaded={mid.get('omnivoice_loaded')}")

    print("asking to turn it OFF mid-load...")
    res, dt, err = post("/api/tts/toggle", False)
    print(f"  disable returned in {dt:.1f}s err={err}")
    if err:
        print(f"\nFAIL: the disable request failed: {err}")
        return 1

    t.join(timeout=900)
    load_res = load_result.get("value", (None, 0, "thread died"))
    print(f"  the original load finished in {load_res[1]:.1f}s (err={load_res[2]})")

    final = get("/api/tts/status")
    print(f"\nfinal: loaded={final.get('omnivoice_loaded')} loading={final.get('loading')}")

    if final.get("omnivoice_loaded"):
        print("\nFAIL: OmniVoice is still loaded - the user asked for it off.")
        return 1
    print("\nPASS: TTS could be turned off mid-load and really is off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())