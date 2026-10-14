"""
Does whisper-tiny actually recognise the wake phrase, in Russian mode?

Feeds a rendered wav straight into the detector's transcription + matching path,
skipping the microphone. This isolates the risky part - can the small model
hear the phrase at all - from the part already verified live (capture + VAD).

Usage:
  python tests/make_wake_wav.py "ассистент, открой блокнот"   # render speech
  python tests/check_wake_phrase.py debug_tts/wake_ru.wav "ассистент"
"""

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, ".")

from src.wake_word import WakeWordDetector, phrase_score  # noqa: E402


def load_16k(path: Path) -> np.ndarray:
    data, sr = sf.read(str(path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        # linear resample is enough for a functional check
        n = int(round(len(data) * 16000 / sr))
        data = np.interp(
            np.linspace(0, len(data) - 1, n),
            np.arange(len(data)),
            data,
        ).astype("float32")
    return data


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        return
    wav = Path(sys.argv[1])
    phrase = sys.argv[2]

    audio = load_16k(wav)
    print(f"audio    : {len(audio) / 16000:.1f}s @16 kHz")
    print(f"phrase   : {phrase!r}")

    fired = []
    d = WakeWordDetector(
        phrase=phrase,
        model_path="models/whisper-tiny",
        on_detect=fired.append,
        cooldown=0.0,
    )
    print(f"language : {d.language}")
    if not d._load_models():
        print("could not load models:", d.error)
        return

    # whole clip, then sliding 2.5 s windows like the live loop does
    attempts = [("full clip", audio)]
    win = int(2.5 * 16000)
    for start in range(0, max(1, len(audio) - win + 1), win // 2):
        attempts.append((f"window @{start / 16000:.1f}s", audio[start:start + win]))

    best = 0.0
    best_label = ""
    report = []
    print()
    for label, chunk in attempts:
        text = d._transcribe(chunk)
        score = phrase_score(text, phrase)
        mark = "MATCH " if score >= 0.82 else "      "
        print(f"  {mark}{label:<18} score={score:.2f}")
        report.append(f"{label:<18} score={score:.2f}  {text}")
        if score > best:
            best, best_label = score, text
        d._maybe_trigger(text, 1000.0)

    print()
    print(f"best: {best:.2f}  {best_label!r}")
    print("triggered:", len(fired))
    # Write the result to a file: the Windows console mangles Cyrillic
    try:
        with open(r"F:\TEMP\Temp\wake_phrase_report.txt", "w", encoding="utf-8") as f:
            f.write(f"phrase: {phrase}\nbest score: {best:.2f}\n")
            f.write(f"best transcript: {best_label}\n")
            f.write(f"triggered: {len(fired)}\n\n")
            f.write("\n".join(report) + "\n")
    except Exception:
        pass
    print("VERDICT:", "PASS" if best >= 0.82 else "FAIL - tiny does not hear the phrase")


if __name__ == "__main__":
    main()