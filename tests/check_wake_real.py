"""
Benchmark the wake-word models on a real recording.

The synthetic degradation used so far disagreed with reality twice, so this
scores each candidate on an actual microphone recording instead.

    python tests/check_wake_real.py [wav] [phrase]
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SR = 16000


def load(path):
    import soundfile as sf

    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        import scipy.signal as sig

        audio = sig.resample(audio, int(len(audio) * SR / sr))
    return audio.astype(np.float32)


def main():
    from src.wake_word import phrase_score

    wav = sys.argv[1] if len(sys.argv) > 1 else "myVoice/assistant_open_note.wav"
    phrase = sys.argv[2] if len(sys.argv) > 2 else "ассистент"
    audio = load(wav)

    print(f"file   : {wav}")
    print(f"audio  : {len(audio) / SR:.2f}s @ {SR} Hz")
    print(f"phrase : {phrase!r}")
    print(f"peak   : {float(np.max(np.abs(audio))):.4f}\n")

    # --- 1. What the live pipeline actually decides -----------------------
    print("=" * 68)
    print("1. REAL PIPELINE (VAD + WakeWordStream), as the listener runs it")
    print("=" * 68)
    fired = []
    d = None
    try:
        from silero_vad import load_silero_vad

        from src.wake_word import WakeWordDetector, WakeWordStream

        model = sys.argv[3] if len(sys.argv) > 3 else "large-v3-turbo"
        d = WakeWordDetector(
            phrase=phrase,
            model_path=f"models/whisper-{model}",
            on_detect=fired.append,
            cooldown=0.0,
        )
        if d._load_models():
            stream = WakeWordStream(d, load_silero_vad())
            blocks = [
                audio[i : i + 512] for i in range(0, len(audio), 512)
            ]
            if blocks[-1].size < 512:
                blocks[-1] = np.pad(blocks[-1], (0, 512 - blocks[-1].size))
            for b in blocks:
                stream.push(b)
            text = stream.finish(stream.elapsed)
            if text:
                print(
                    f"  model        : {model} on {d.model_device}\n"
                    f"  whisper runs : {stream.runs}\n"
                    f"  final text   : {text!r}\n"
                    f"  score        : {phrase_score(text, phrase):.2f}"
                )
            print(f"  TRIGGERS     : {len(fired)}  {fired!r}")
            print(
                "  verdict      : "
                + ("WOULD WAKE" if fired else "WOULD NOT WAKE")
            )
        else:
            print("  models unavailable:", d.error)
    except Exception as e:
        print(f"  pipeline failed: {type(e).__name__}: {e}")
    del d

    # --- 2. Model comparison on the same audio ---------------------------
    print("\n" + "=" * 68)
    print("2. MODEL COMPARISON on the same audio")
    print("=" * 68)
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    pad = np.zeros(int(0.4 * SR), dtype=np.float32)
    padded = np.concatenate([pad, audio])

    print(f"{'model':<14}{'score':>7}{'ms':>8}  transcript")
    print("-" * 68)
    for name in ("tiny", "base", "large-v3-turbo"):
        path = f"models/whisper-{name}"
        if not os.path.isdir(path):
            print(f"{name:<14}{'--':>7}{'--':>8}  (not downloaded)")
            continue
        try:
            t0 = time.time()
            p = WhisperProcessor.from_pretrained(path, local_files_only=True)
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            m = WhisperForConditionalGeneration.from_pretrained(
                path, local_files_only=True, torch_dtype=dtype
            )
            if torch.cuda.is_available():
                m = m.to("cuda")
            m.eval()

            inputs = p(padded, sampling_rate=SR, return_tensors="pt")
            feats = inputs.input_features.to(m.device, dtype=dtype)
            with torch.no_grad():
                ids = m.generate(
                    feats,
                    max_new_tokens=24,
                    do_sample=False,
                    language="ru",
                )
            text = p.batch_decode(ids, skip_special_tokens=True)[0].strip()
            dt = (time.time() - t0) * 1000
            score = phrase_score(text, phrase)
            hit = "PASS" if score >= 0.70 else "miss"
            print(f"{name:<14}{score:>7.2f}{dt:>8.0f}  {text!r}  [{hit}]")
            del m
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception as e:
            print(f"{name:<14}{'ERR':>7}{'':>8}  {type(e).__name__}: {str(e)[:70]}")
    print("\nPASS needs score >= 0.70 (the shipped threshold).")


if __name__ == "__main__":
    sys.exit(main())