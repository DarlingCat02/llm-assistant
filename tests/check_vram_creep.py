"""
Does the VRAM creep across load/unload cycles?

After the first load the process keeps a fixed overhead that empty_cache() does
not return - the CUDA context and the cuBLAS/cuDNN workspaces. That is
expected. Creeping *past* it would be a leak, which is the thing that must be
ruled out.

    python tests/check_vram_creep.py [cycles]
"""

import io
import json
import sys
import time
import urllib.request
import uuid

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


def stt():
    import numpy as np
    import soundfile as sf

    buf = io.BytesIO()
    t = np.linspace(0, 0.4, 6400, endpoint=False)
    sf.write(buf, (0.1 * np.sin(2 * 3.14159 * 220 * t)).astype("float32"),
             16000, format="WAV", subtype="PCM_16")
    b = uuid.uuid4().hex
    body = (f"--{b}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="t.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n").encode() + buf.getvalue() + \
           f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(
        f"{API}/api/stt", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=900) as r:
        r.read()


def main():
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    print(f"{cycles} load/unload cycles of the recognition model\n")
    rows = []
    for i in range(cycles):
        stt()
        post("/api/models/release", {"what": "stt"})
        post("/api/gpu-memory/release", {})
        time.sleep(1.5)
        s = get("/api/gpu-memory")
        rows.append((i + 1, s["allocated_mb"], s["reserved_mb"], s["vram_free_mb"]))
        print(f"  cycle {i+1}: allocated {s['allocated_mb']:>5} MB | "
              f"reserved {s['reserved_mb']:>5} MB | free {s['vram_free_mb']:>5} MB")

    base = rows[0][2]
    last = rows[-1][2]
    print(f"\n  reserved floor after the first cycle: {base} MB")
    print(f"  after {cycles} cycles:                  {last} MB")
    drift = last - base
    if drift > 128:
        print(f"\nFAIL: reserved grew by {drift} MB - that is a leak")
        return 1
    print(f"\nPASS: steady at {last} MB (drift {drift:+d} MB).")
    print("The floor is the CUDA context and cuBLAS workspaces, which are")
    print("allocated once and never returned - normal, not a leak.")
    return 0


if __name__ == "__main__":
    sys.exit(main())