"""
Does switching the wake-word model actually release the old one?

Turning "always listening" off must give the memory back, and switching from
tiny to base must not leave both resident. This measures GPU allocation (and
RSS on CPU-only machines) around each step, so the claim is a number rather
than an intention.

    python tests/check_wake_unload.py
"""

import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def probe():
    """Bytes currently held by the process, on the accelerator if there is one."""
    import torch

    if torch.cuda.is_available():
        torch.cuda.synchronize()
        return ("gpu", torch.cuda.memory_allocated())
    try:
        import psutil

        return ("rss", psutil.Process().memory_info().rss)
    except Exception:
        # No psutil: fall back to the object graph being empty, which is still
        # a meaningful check.
        return ("refs", sum(1 for _ in gc.get_objects()))


def mb(kind, value):
    if kind == "refs":
        return f"{value} live objects"
    return f"{value / 1024 ** 2:7.1f} MB"


def main():
    from src.wake_word import WakeWordDetector

    kind, _ = probe()
    print(f"tracking: {kind}\n")

    # Start from a clean slate so the baseline is honest.
    gc.collect()
    if kind == "gpu":
        import torch

        torch.cuda.empty_cache()
    baseline_kind, baseline = probe()
    print(f"baseline                    {mb(kind, baseline)}")

    models = []
    for name in ("tiny", "base"):
        path = f"models/whisper-{name}"
        if not os.path.isdir(path):
            print(f"\n{name}: not downloaded, skipping")
            continue

        d = WakeWordDetector(
            phrase="ассистент",
            model_path=path,
            on_detect=lambda t: None,
            cooldown=0.0,
        )
        if not d._load_models():
            print(f"\n{name}: could not load ({d.error})")
            continue

        _, after_load = probe()
        print(
            f"loaded {name:<20}{mb(kind, after_load)}"
            f"   (+{(after_load - baseline) / 1024 ** 2:.1f} MB over baseline)"
        )
        assert d.is_model_loaded, "model should report as loaded"
        models.append((name, d))

        d.unload()
        _, after_unload = probe()
        print(f"unloaded {name:<18}{mb(kind, after_unload)}")
        assert not d.is_model_loaded, "model should report as unloaded"

        leak = after_unload - baseline
        verdict = "OK" if leak < (after_load - baseline) * 0.25 else "NOT RELEASED"
        print(f"  -> {verdict} (residual {leak / 1024 ** 2:+.1f} MB)\n")

    print("=" * 52)
    leftovers = [n for n, d in models if d.is_model_loaded]
    print("still holding a model:", leftovers or "none")
    return 0 if not leftovers else 1


if __name__ == "__main__":
    sys.exit(main())