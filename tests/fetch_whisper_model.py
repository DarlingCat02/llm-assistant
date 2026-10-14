"""
One-off helper: download a Whisper model into ./models/.

src/memory_manager.py hard-sets HF_HUB_OFFLINE=1 at import time (plain
assignment, not setdefault), which makes the lazy download inside
resolve_whisper_model() impossible inside the app. This script imports src
first, then clears the flags, so the existing download path can be reused.

Usage: python tests/fetch_whisper_model.py tiny
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

import src  # noqa: E402  (side effect: forces HF offline)

# Undo the hard-coded offline flags so the snapshot can be fetched
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ.pop("TRANSFORMERS_OFFLINE", None)

from src.stt_engine import resolve_whisper_model  # noqa: E402


def main() -> None:
    spec = sys.argv[1] if len(sys.argv) > 1 else "tiny"
    target = Path(__file__).parent.parent / "models" / f"whisper-{spec}"
    already = target.exists()

    t = time.time()
    try:
        path = resolve_whisper_model(spec)
    except Exception as e:
        print(f"download failed: {type(e).__name__}: {e}")
        return

    files = list(Path(path).rglob("*"))
    size = sum(f.stat().st_size for f in files if f.is_file())
    print(f"model: {path}")
    print(f"files: {sum(1 for f in files if f.is_file())}  size: {size / 1024 / 1024:.0f} MB")
    print(f"took: {time.time() - t:.1f}s{' (already present)' if already else ''}")


if __name__ == "__main__":
    main()