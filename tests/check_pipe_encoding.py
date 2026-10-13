"""
Diagnostic: does the backend emit bytes that are not valid UTF-8?

Rust's old log pump used BufRead::lines(), which fails with InvalidData on the
first non-UTF-8 line and silently ended the stream -> the in-app terminal froze
after a couple of lines. This script captures the backend's raw pipe output and
reports the first line that cannot be decoded strictly.

Usage: python tests/check_pipe_encoding.py
"""

import os
import subprocess
import sys
import time

PORT = "8011"
WAIT_SECONDS = 35


def analyse(name: str, data: bytes) -> None:
    lines = data.split(b"\n")
    first_bad = None
    for i, line in enumerate(lines):
        try:
            line.decode("utf-8")
        except UnicodeDecodeError:
            first_bad = (i, line[:70])
            break

    print(f"{name}: {len(data)} bytes, {len(lines)} lines")
    if first_bad is None:
        print(f"  every line decodes as UTF-8")
    else:
        print(f"  first non-UTF-8 line at index {first_bad[0]}: {first_bad[1]!r}")
    for line in lines[:3]:
        if line.strip():
            print(f"  sample: {line[:80]!r}")
            break


def main() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", PORT, "--log-level", "info"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(os.environ),
    )
    time.sleep(WAIT_SECONDS)
    proc.terminate()
    try:
        out, err = proc.communicate(timeout=15)
    except Exception:
        proc.kill()
        out, err = proc.communicate()

    analyse("stdout", out)
    analyse("stderr", err)

    # A few requests so the chat/LLM paths log too
    import json
    import urllib.request
    try:
        body = json.dumps({"message": "Привет, напиши абзац про Python"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/chat", data=body,
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=120).read()
        print("chat request: ok")
    except Exception as e:
        print("chat request failed:", type(e).__name__)


if __name__ == "__main__":
    main()