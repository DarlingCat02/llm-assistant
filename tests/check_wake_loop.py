"""
Run a wav file through the REAL wake-word pipeline.

This drives WakeWordStream - the same class the live listener uses - instead of
re-implementing the loop, which is how the previous version of this check
ended up testing stale logic.

    python tests/check_wake_loop.py [wav] [phrase]
"""

import os
import sys

import numpy as np

# Run from the repo root regardless of the cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WAV = sys.argv[1] if len(sys.argv) > 1 else "debug_tts/wake_ru.wav"
PHRASE = sys.argv[2] if len(sys.argv) > 2 else "ассистент"


def main():
    import soundfile as sf
    from silero_vad import load_silero_vad

    from src.wake_word import (
        BLOCK_SIZE,
        SAMPLE_RATE,
        WakeWordDetector,
        WakeWordStream,
        phrase_score,
    )

    audio, sr = sf.read(WAV, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        import scipy.signal as sig

        audio = sig.resample(audio, int(len(audio) * SAMPLE_RATE / sr))

    print(f"file  : {WAV}")
    print(f"audio : {len(audio) / SAMPLE_RATE:.2f}s")
    print(f"phrase: {PHRASE!r}\n")

    fired = []
    d = WakeWordDetector(
        phrase=PHRASE,
        model_path="models/whisper-tiny",
        on_detect=fired.append,
        cooldown=0.0,
    )
    if not d._load_models():
        print("could not load models:", d.error)
        return 1
    print(f"decode language: {d.language}\n")

    stream = WakeWordStream(d, load_silero_vad())

    blocks = [
        audio[i : i + BLOCK_SIZE] for i in range(0, len(audio), BLOCK_SIZE)
    ]
    if blocks and blocks[-1].size < BLOCK_SIZE:
        blocks[-1] = np.pad(blocks[-1], (0, BLOCK_SIZE - blocks[-1].size))

    print(f"{'t':>6}  {'speaking':>8}  transcript")
    for block in blocks:
        before = stream.runs
        text = stream.push(block)
        if stream.runs > before:
            speaking = "yes" if stream.speech else "final"
            mark = "  <== MATCH" if fired else ""
            print(
                f"{stream.elapsed:6.2f}  {speaking:>8}  {text!r} "
                f"score={phrase_score(text, PHRASE):.2f}{mark}"
            )

    # The decisive run: the live listener reaches this after SPEECH_HANG_SECONDS
    # of quiet, so a file-based check has to ask for it explicitly.
    final = stream.finish(stream.elapsed)
    if final:
        print(
            f"{stream.elapsed:6.2f}  {'final':>8}  {final!r} "
            f"score={phrase_score(final, PHRASE):.2f}"
            f"{'  <== MATCH' if fired else ''}"
        )

    print("\n--- verdict ---")
    print(f"whisper runs : {stream.runs}")
    print(f"triggers     : {len(fired)}")
    if fired:
        print(f"PASS -> {fired[0]!r}")
        return 0
    print(f"last heard   : {d.last_transcript!r}")
    print("FAIL -> the phrase never triggered inside the live loop")
    return 1


if __name__ == "__main__":
    sys.exit(main())