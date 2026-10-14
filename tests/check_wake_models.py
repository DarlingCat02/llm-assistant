"""
Why does tiny mishear "ассистент", and what actually fixes it?

The live failure was 'ассистент' -> 'Систент' (0.80 vs a 0.82 threshold).
Two candidate fixes: make the model hear it correctly, or accept a lower
score. Both need evidence, so this degrades the known-good recording into
conditions closer to a real microphone and measures each option.

    python tests/check_wake_models.py [tiny|base]
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SR = 16000
PHRASE = "ассистент"


def degrade(audio: np.ndarray, kind: str, rng: np.random.Generator) -> np.ndarray:
    """Approximate what a real microphone does to the speech."""
    a = audio.astype(np.float32).copy()
    if kind == "clean":
        return a
    if kind == "quiet":
        return a * 0.25
    if kind == "noise":
        noise = rng.standard_normal(len(a)).astype(np.float32) * 0.02
        return a * 0.5 + noise
    if kind == "slow":          # the speaker talks slower/faster
        import scipy.signal as sig

        return sig.resample(a, int(len(a) * 1.15))
    if kind == "lowpass":       # cheap mic / voice pickup
        import scipy.signal as sig

        b, aa = sig.butter(4, 3000 / (SR / 2), btype="low")
        return sig.lfilter(b, aa, a)
    if kind == "far":          # distance + room noise, the failing case
        noise = rng.standard_normal(len(a)).astype(np.float32) * 0.035
        a = a * 0.35 + noise
        import scipy.signal as sig

        b, aa = sig.butter(4, 2600 / (SR / 2), btype="low")
        return sig.lfilter(b, aa, a)
    return a


def main():
    import soundfile as sf
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    import torch

    from src.wake_word import phrase_score

    model_name = sys.argv[1] if len(sys.argv) > 1 else "tiny"
    path = f"models/whisper-{model_name}"
    print(f"model: {path}")
    if not os.path.isdir(path):
        print("not downloaded")
        return 1

    audio, sr = sf.read("debug_tts/wake_ru.wav", dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        import scipy.signal as sig

        audio = sig.resample(audio, int(len(audio) * SR / sr))

    pad = np.zeros(int(0.4 * SR), dtype=np.float32)
    audio = np.concatenate([pad, audio])

    processor = WhisperProcessor.from_pretrained(path, local_files_only=True)
    model = WhisperForConditionalGeneration.from_pretrained(
        path, local_files_only=True, torch_dtype=torch.float32
    ).eval()

    def transcribe(x, **gen_kwargs):
        inputs = processor(x, sampling_rate=SR, return_tensors="pt")
        t0 = time.time()
        with torch.no_grad():
            ids = model.generate(
                inputs.input_features,
                max_new_tokens=16,
                do_sample=False,
                language="ru",
                **gen_kwargs,
            )
        dt = time.time() - t0
        return processor.batch_decode(ids, skip_special_tokens=True)[0].strip(), dt

    rng = np.random.default_rng(7)
    variants = ["clean", "quiet", "noise", "slow", "lowpass", "far"]

    configs = {
        "baseline (beam1)": {},
        "prompt=phrase": {"initial_prompt": f"{PHRASE}, ассистент"},
        "beam5": {"num_beams": 5},
        "prompt+beam5": {"initial_prompt": f"{PHRASE}, ассистент", "num_beams": 5},
    }

    print(f"\n{'condition':<9}", end="")
    for name in configs:
        print(f"{name:>18}", end="")
    print()
    print("-" * (9 + 18 * len(configs)))

    totals = {name: [0.0, 0, 0] for name in configs}  # score, time, hits

    for variant in variants:
        x = degrade(audio, variant, rng)
        print(f"{variant:<9}", end="")
        for name, kwargs in configs.items():
            try:
                text, dt = transcribe(x, **kwargs)
            except Exception as e:
                print(f"{'ERR':>18}", end="")
                continue
            score = phrase_score(text, PHRASE)
            hit = 1 if score >= 0.82 else 0
            totals[name][0] += score
            totals[name][1] += dt
            totals[name][2] += hit
            flag = "" if hit else "!"
            print(f"{score:>13.2f}{flag:<4}", end="")
        print()

    print("-" * (9 + 18 * len(configs)))
    print(f"{'MEAN':<9}", end="")
    for name in configs:
        s, t, h = totals[name]
        n = len(variants)
        print(f"{s/n:>13.2f} {h}/{n} {'':<2}", end="")
    print("\n\nmean inference time:")
    for name in configs:
        _, t, _ = totals[name]
        print(f"  {name:<18} {t / len(variants) * 1000:6.0f} ms")

    print(f"\nPASS needs score >= 0.82; '!' marks a miss.")


if __name__ == "__main__":
    sys.exit(main())