"""
Live check: is the detector listening, and does it stay quiet in silence?

Usage: python tests/check_wake_live.py [seconds]
"""

import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8000/api/wake-word"


def get() -> dict:
    return json.loads(urllib.request.urlopen(URL, timeout=10).read())


def main() -> None:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    s = get()
    print(f"enabled={s['enabled']}  listening={s['listening']}  error={s['error']}")
    print(f"phrase={s['phrase']!r}")
    if not s["listening"]:
        print("NOT LISTENING - nothing to observe")
        return

    print(f"--- observing {seconds}s ---")
    triggers = 0
    prev = ""
    for i in range(seconds // 5):
        time.sleep(5)
        st = get()
        cur = st["last_transcript"]
        changed = "" if cur == prev else f"  <- new: {cur[:60]!r}"
        print(
            f"  t+{(i + 1) * 5:>3}s  score={st['phrase_score']:.2f}"
            f"  transcript={cur[:60]!r}{changed}"
        )
        prev = cur
    print("done")


if __name__ == "__main__":
    main()