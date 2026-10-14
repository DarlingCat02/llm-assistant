"""Compare the RMS of the wake-word mic candidates. Speak while it runs."""

import sys
import time

import numpy as np
import sounddevice as sd

CANDIDATES = ["fifine", "SteelSeries Sonar - Microphone"]
SECONDS = 6.0


def main():
    devices = sd.query_devices()
    default_in = sd.default.device[0]

    picks = []
    for idx, d in enumerate(devices):
        if d.get("max_input_channels", 0) < 1:
            continue
        name = d.get("name", "")
        if any(c.lower() in name.lower() for c in CANDIDATES):
            picks.append((idx, name.strip(), idx == default_in))

    print(f"system default input: {default_in}")
    print(f"candidates: {[(i, n) for i, n, _ in picks]}\n")
    print("Говорите в микрофон сейчас!\n")

    for idx, name, is_def in picks:
        levels = []
        try:
            with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                                blocksize=512, device=idx) as st:
                end = time.time() + SECONDS
                while time.time() < end:
                    data, _ = st.read(512)
                    b = np.asarray(data, dtype=np.float32).flatten()
                    if b.size:
                        levels.append(float(np.sqrt(np.mean(np.square(b)))))
        except Exception as e:
            print(f"[{idx}] {name}: FAILED {e}")
            continue

        if not levels:
            print(f"[{idx}] {name}: no audio read")
            continue

        loudest = max(levels)
        print(
            f"[{idx}] {name}{'  <-- system default' if is_def else ''}\n"
            f"      peak={loudest:.5f}  median={np.median(levels):.5f}  "
            f"{'HEARS YOU' if loudest > 0.01 else 'SILENT'}"
        )


if __name__ == "__main__":
    main()