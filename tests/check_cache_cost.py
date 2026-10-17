"""
Does returning the CUDA cache cost a slow reload?

The measurements showed the memory is not the models: unloading leaves 3.6 GB
reserved by PyTorch, which is why the GPU looks busy. Handing that back is
only worth it if the next load is not suddenly slow again.

So: load TTS, unload it, drop the cache, load it again, and compare.

    python tests/check_cache_cost.py <log-file>
"""

import io
import json
import os
import re
import sys
import time
import urllib.request

API = "http://127.0.0.1:8000"


def post(path, payload, timeout=900):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path, timeout=30):
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def line(label, state):
    print(f"  {label:<26} allocated {state['allocated_mb']:>5} MB | "
          f"reserved {state['reserved_mb']:>5} MB | free {state['vram_free_mb']:>5} MB")


def main():
    log = sys.argv[1]

    if get("/api/gpu-memory")["tts_loaded"]:
        post("/api/tts/toggle", {"enabled": False})
        time.sleep(3)

    print("1. first load, with the cache empty")
    t0 = time.time()
    post("/api/tts/toggle", {"enabled": True})
    cold = time.time() - t0
    line("TTS loaded", get("/api/gpu-memory"))
    print(f"  took {cold:.1f}s")

    print("\n2. unload, without touching the cache")
    t0 = time.time()
    post("/api/tts/toggle", {"enabled": False})
    time.sleep(3)
    after_unload = get("/api/gpu-memory")
    line("after unload", after_unload)
    print(f"  took {time.time() - t0:.1f}s")

    print("\n3. hand the cache back")
    freed = post("/api/gpu-memory/release", {})
    line("after release", freed)
    print(f"  handed back: {freed.get('freed_mb')} MB")

    print("\n4. load again, with the cache gone")
    t0 = time.time()
    post("/api/tts/toggle", {"enabled": True})
    warm = time.time() - t0
    line("TTS loaded again", get("/api/gpu-memory"))
    print(f"  took {warm:.1f}s")

    print("\n--- verdict ---")
    print(f"  first load      : {cold:>5.1f}s")
    print(f"  load after free : {warm:>5.1f}s")
    extra = warm - cold
    if extra <= 2:
        print("  freeing the cache costs nothing measurable - free it by default.")
    else:
        print(f"  freeing the cache costs {extra:+.1f}s per load "
              "- only worth it on a real idle timer.")
    post("/api/tts/toggle", {"enabled": False})
    return 0


if __name__ == "__main__":
    sys.exit(main())