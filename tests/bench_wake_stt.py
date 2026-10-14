"""
Benchmark options for always-on wake-word detection.

Every number that matters for the design is measured here: window length,
inference interval, thread count and int8 dynamic quantisation. VAD-gated
detection only pays this cost while the user is actually talking.
"""

import sys
import time

import numpy as np
import torch

sys.path.insert(0, ".")

from transformers import WhisperForConditionalGeneration, WhisperProcessor  # noqa: E402

MODEL = "models/whisper-tiny"
SR = 16000


def make_audio(seconds: float, freq: float = 220.0) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (0.1 * np.sin(2 * np.pi * freq * t)).astype("float32")


def bench(model, proc, audio, repeats: int = 3) -> float:
    inputs = proc(audio, sampling_rate=SR, return_tensors="pt")
    feats = inputs.input_features
    times = []
    for _ in range(repeats):
        t0 = time.time()
        with torch.no_grad():
            model.generate(feats, max_new_tokens=6, num_beams=1, do_sample=False)
        times.append(time.time() - t0)
    return min(times)


def main() -> None:
    proc = WhisperProcessor.from_pretrained(MODEL, local_files_only=True)
    base = WhisperForConditionalGeneration.from_pretrained(
        MODEL, local_files_only=True, torch_dtype=torch.float32
    )
    base.eval()

    quant = torch.ao.quantization.quantize_dynamic(
        base, {torch.nn.Linear}, dtype=torch.qint8
    )

    print(f"{'variant':<34}{'min ms':>9}{'duty @600ms':>14}")
    print("-" * 57)

    for threads in (12, 4, 2):
        torch.set_num_threads(threads)
        for window in (2.0, 1.5):
            audio = make_audio(window)
            for name, m in (("float32", base), ("int8", quant)):
                dt = bench(m, proc, audio)
                duty = dt / 0.6 * 100
                label = f"{name}, {threads} threads, {window}s window"
                print(f"{label:<34}{dt * 1000:>9.0f}{duty:>13.0f}%")


if __name__ == "__main__":
    main()