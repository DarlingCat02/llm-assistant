"""
How much room is there below the threshold before false wake-ups start?

The live failure was 'ассистент' -> 'Систент' (0.80 vs a 0.82 threshold). Lowering
the threshold would fix that, so this measures what ordinary speech scores to
find out whether it would also start firing on things that are not the phrase.

    python tests/check_wake_threshold.py
"""

import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SR = 16000
PHRASE = "ассистент"
THRESHOLD = 0.70


def main():
    import soundfile as sf
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    import torch

    from src.wake_word import phrase_score

    model_name = sys.argv[1] if len(sys.argv) > 1 else "tiny"
    path = f"models/whisper-{model_name}"
    if not os.path.isdir(path):
        print(f"model not present: {path}")
        return 1

    processor = WhisperProcessor.from_pretrained(path, local_files_only=True)
    model = WhisperForConditionalGeneration.from_pretrained(
        path, local_files_only=True, torch_dtype=torch.float32
    ).eval()

    # Recordings of ordinary speech: anything that is NOT the wake phrase.
    files = sorted(glob.glob("debug_tts/tts_*.wav"))
    if not files:
        print("no debug_tts/tts_*.wav to measure against")
        return 1
    files = files[:25]

    print(f"model     : {model_name}")
    print(f"phrase    : {PHRASE!r}")
    print(f"threshold : {THRESHOLD}")
    print(f"negatives : {len(files)} ordinary utterances\n")

    rows = []
    for f in files:
        audio, sr = sf.read(f, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != SR:
            import scipy.signal as sig

            audio = sig.resample(audio, int(len(audio) * SR / sr))
        if len(audio) < SR // 2:
            continue
        audio = np.concatenate([np.zeros(int(0.4 * SR), dtype=np.float32), audio])

        inputs = processor(audio, sampling_rate=SR, return_tensors="pt")
        with torch.no_grad():
            ids = model.generate(
                inputs.input_features, max_new_tokens=16, do_sample=False, language="ru"
            )
        text = processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
        rows.append((phrase_score(text, PHRASE), text, os.path.basename(f)))

    rows.sort(reverse=True)
    print(f"{'score':>6}  file")
    for score, text, name in rows:
        mark = "  <-- WOULD FIRE" if score >= THRESHOLD else ""
        print(f"{score:6.2f}  {name:<18} {text[:52]!r}{mark}")

    scores = [r[0] for r in rows]
    print(f"\nhighest negative score : {max(scores):.2f}")
    print(f"mean                   : {np.mean(scores):.2f}")
    print(f"how many >= {THRESHOLD}       : {sum(1 for s in scores if s >= THRESHOLD)}/{len(scores)}")
    print(
        "\nFor reference the live mis-hearing scored 0.80. A threshold between\n"
        "the highest negative and 0.80 would accept it without opening the door\n"
        "to these utterances."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())