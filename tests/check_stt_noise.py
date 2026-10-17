"""
The app terminal must stay readable: recognition should not spray warnings.

Voice notes arrive as webm/opus. soundfile cannot open that, so librosa falls
back to audioread - and Whisper adds a handful of warnings per generate() call.
Both used to print on every single recognition, burying the one thing the
terminal is for.

    python tests/check_stt_noise.py <webm-file> <log-file>
"""

import io
import json
import os
import sys
import urllib.request
import uuid

API = "http://127.0.0.1:8000"

# Every one of these used to appear on every recognition.
NOISE = [
    "PySoundFile failed",
    "__audioread_load",
    "attention mask is not set",
    "custom logits processor",
    "forced_decoder_ids",
]


def upload(path):
    boundary = uuid.uuid4().hex
    with open(path, "rb") as f:
        payload = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="recording.webm"\r\n'
        f"Content-Type: audio/webm\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{API}/api/stt", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    audio, log = sys.argv[1], sys.argv[2]

    before = os.path.getsize(log) if os.path.exists(log) else 0

    print(f"uploading {os.path.basename(audio)} ({os.path.getsize(audio)//1024} KB)")
    result = upload(audio)
    text = str(result.get("text", "")).strip()
    print(f"  recognized: {text[:70]!r}")
    if not result.get("success"):
        print("FAIL: recognition did not succeed")
        return 1

    with io.open(log, encoding="utf-8", errors="replace") as f:
        f.seek(before)
        tail = f.read()

    found = [n for n in NOISE if n in tail]
    print("\nnoise check on the recognition's own output:")
    for n in NOISE:
        print(f"  {'FOUND  ' if n in found else 'clean  '} {n}")
    if found:
        print(f"\nFAIL: {len(found)} warning(s) still reach the terminal")
        return 1

    if "Recognized:" not in tail:
        print("\nFAIL: no recognition line in the log - did the run get logged?")
        return 1

    print("\nPASS: recognition worked and the terminal stayed clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())