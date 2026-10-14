"""
Diagnostic: does the wake-word microphone actually hear anything?

Distinguishes three failures that look identical from the outside:
  1. the mic is mute / the wrong device is open -> blocks_read grows, level is 0
  2. the mic hears but Silero VAD never fires -> level moves, no transcripts
  3. VAD fires but the phrase does not match    -> transcripts appear, no trigger

Run it and then just talk normally for ~10 seconds.

    python tests/check_wake_audio.py [seconds]
"""

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0


def get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    state = get("/api/wake-word")
    if not state.get("listening"):
        print("Wake word is NOT listening. Enable it in Settings first.")
        print("  enabled =", state.get("enabled"), "| error =", state.get("error"))
        return 1

    print(f"phrase    : {state.get('phrase')!r}")
    print(f"device    : {state.get('active_device') or 'system default'}")
    print(f"mic_open  : {state.get('mic_open')}")
    print(f"listening for {SECONDS:.0f}s - speak normally\n")

    print(f"{'time':>6}  {'level':>9}  {'peak':>9}  {'blocks':>8}  transcript")
    samples = []
    started = time.time()
    while time.time() - started < SECONDS:
        time.sleep(0.5)
        s = get("/api/wake-word")
        row = (
            f"{time.time() - started:6.1f}  "
            f"{s.get('input_level', 0.0):9.5f}  "
            f"{s.get('peak_level', 0.0):9.5f}  "
            f"{s.get('blocks_read', 0):8d}  {s.get('last_transcript', '')!r}"
        )
        print(row)
        samples.append((s.get("input_level", 0.0), s.get("blocks_read", 0)))

    blocks_end = samples[-1][1] if samples else 0
    loudest = max((lvl for lvl, _ in samples), default=0.0)
    transcripts = [s for s in [get("/api/wake-word").get("last_transcript", "")] if s]

    print("\n--- verdict ---")
    if blocks_end == 0:
        print("No audio blocks were read at all: the capture thread is not running.")
        return 1
    if loudest < 0.001:
        print(
            "The microphone is reading audio but it is digital silence.\n"
            "The chosen device is muted, or the real microphone is a different one."
        )
        return 1
    if not transcripts:
        print(
            f"Audio reached the detector (peak {loudest:.4f}) but Whisper never ran.\n"
            "Silero VAD is not reporting speech - check the input gain."
        )
        return 1
    print(
        f"Everything works up to recognition; last transcript: {transcripts[-1]!r}\n"
        "If it does not match the phrase, the model is mishearing it - try model=base."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())