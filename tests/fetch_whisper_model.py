"""
One-off helper: download a speech or embedding model into ./models/.

Both models live inside the project so that a copied folder keeps working.
Nothing here needs the offline flags cleared any more - the app itself refuses
to download only when you ask it to, via HF_HUB_OFFLINE=1.

Usage:
    python tests/fetch_whisper_model.py tiny          # a speech model
    python tests/fetch_whisper_model.py large-v3-turbo
    python tests/fetch_whisper_model.py --embedding   # the memory embeddings
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _report(path, already, started):
    files = [f for f in Path(path).rglob("*") if f.is_file()]
    size = sum(f.stat().st_size for f in files)
    print(f"model: {path}")
    print(f"files: {len(files)}  size: {size / 1024 / 1024:.0f} MB")
    print(f"took: {time.time() - started:.1f}s{' (already present)' if already else ''}")


def fetch_embedding():
    from src.memory_manager import embedding_model_path, ensure_embedding_model

    started = time.time()
    target = embedding_model_path()
    already = target.is_dir()
    try:
        path = ensure_embedding_model()
    except Exception as exc:
        print(f"download failed: {type(exc).__name__}: {exc}")
        return 1
    _report(path, already, started)
    return 0


def fetch_whisper(spec):
    from src.stt_engine import resolve_whisper_model

    started = time.time()
    target = Path(__file__).parent.parent / "models" / f"whisper-{spec}"
    already = target.exists()
    try:
        path = resolve_whisper_model(spec)
    except Exception as exc:
        print(f"download failed: {type(exc).__name__}: {exc}")
        return 1
    _report(path, already, started)
    return 0


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "tiny"
    if arg in ("--embedding", "embedding"):
        return fetch_embedding()
    return fetch_whisper(arg)


if __name__ == "__main__":
    sys.exit(main())