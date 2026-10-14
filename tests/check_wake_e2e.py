"""
End-to-end check: does the wake phrase actually trigger detection?

Plays a rendered wav through the default output device and watches
/api/wake-word for a trigger. Needs the microphone to be able to hear the
speakers (turn the volume up, or use a headset).

Usage: python tests/check_wake_e2e.py <wav> [seconds]
"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8000/api/wake-word"


def get() -> dict:
    return json.loads(urllib.request.urlopen(URL, timeout=10).read())


def play(wav: Path) -> None:
    """Play a wav with the default Windows audio output."""
    ps = (
        "Add-Type -AssemblyName System.Media; "
        f"(New-Object System.Media.SoundPlayer '{wav}').PlaySync()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: check_wake_e2e.py <wav> [seconds]")
        return
    wav = Path(sys.argv[1])
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    state = get()
    if not state["listening"]:
        print("wake word is not listening - nothing to test")
        return

    acoustic(wav, seconds)


def acoustic(wav: Path, seconds: int = 12) -> None:
    """Play the wav through the default output and watch for a trigger."""
    import winsound

    print(f"listening for {get()['phrase']!r}")
    print(f"playing {wav.name} for {seconds}s...")
    best, best_text, fired = 0.0, "", []
    t0 = time.time()
    winsound.PlaySound(
        str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC
    )
    while time.time() - t0 < seconds:
        time.sleep(0.5)
        s = get()
        score = s["phrase_score"]
        if score > best:
            best, best_text = score, s["last_transcript"]
        if score >= 0.82 and s["last_transcript"] and s["last_transcript"] not in fired:
            fired.append(s["last_transcript"])
            print(f"  t+{time.time() - t0:5.1f}s  TRIGGER score={score:.2f}")
    print(f"\nbest score : {best:.2f}")
    print(f"triggers   : {len(fired)}")
    try:
        with open(r"F:\TEMP\Temp\wake_acoustic.txt", "w", encoding="utf-8") as f:
            f.write(f"best score: {best:.2f}\ntriggers: {len(fired)}\nbest: {best_text}\n")
            for x in fired:
                f.write(f"  {x}\n")
    except Exception:
        pass
    if best < 0.82:
        print("\nNo trigger. If the microphone cannot hear the speakers that is an")
        print("audio-routing matter, not a detection problem - the phrase itself was")
        print("verified by tests/check_wake_phrase.py.")


if __name__ == "__main__":
    main()