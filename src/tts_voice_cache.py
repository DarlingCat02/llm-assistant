"""
Permanent store for voice-sample transcriptions.

Transcribing a sample is what the extra Whisper inside OmniVoice exists for.
Once done, the text is worth keeping: it never changes for an unchanged file,
and it saves a 1.5 GB model load plus a few seconds on every later start.

The engine only ever cached this in memory, which vanished whenever speech
synthesis was switched off - the same sample was transcribed again on every
switch-on (measured twice in a row in the user's own log).

Entries are keyed by normalised path and guarded by the file's size and mtime,
so replacing a voice sample invalidates its transcription automatically. The
file is plain JSON on purpose: if the transcription is wrong, the user should be
able to open it and fix the text, and the fix has to survive restarts.

    storage/tts_voices.json
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STORE = Path(__file__).parent.parent / "storage" / "tts_voices.json"


def normalize(path: str | os.PathLike) -> str:
    """
    One canonical form for a path.

    The same file arrived as 'voices/x.mp3' and as an absolute path with
    backslashes, which the engine counted as two different samples and
    transcribed twice in a row. normcase folds the case and separators on
    Windows; abspath makes the key independent of the working directory.
    """
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))


def load() -> dict:
    """All known entries. A missing or damaged file reads as empty."""
    try:
        if not STORE.exists():
            return {}
        with open(STORE, encoding="utf-8") as f:
            data = json.load(f)
        voices = data.get("voices")
        return voices if isinstance(voices, dict) else {}
    except Exception as e:
        # Never let a cache problem break speech synthesis.
        logger.warning(f"Voice transcription cache unreadable ({e}); starting empty")
        return {}


def _write(data: dict) -> None:
    """
    Write the store, replacing it only once the new file is complete.

    A half-written JSON would lose every transcription at once, so the new
    content goes to a temporary file first and then takes the place of the old
    one in a single step.
    """
    STORE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "voices": data,
               "updated": datetime.now().isoformat(timespec="seconds")}
    fd, tmp = tempfile.mkstemp(dir=str(STORE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STORE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def lookup(sample: str) -> str | None:
    """
    The saved transcription for a sample, if it is still trustworthy.

    Returns None when there is no entry, or when the audio file changed since
    it was transcribed - in which case the text would be describing the wrong
    words.
    """
    key = normalize(sample)
    entry = load().get(key)
    if not isinstance(entry, dict):
        return None
    text = entry.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    try:
        st = Path(key).stat()
        if st.st_size != entry.get("size"):
            logger.info("Voice sample changed (size) - transcription will be redone")
            return None
        if abs(st.st_mtime - float(entry.get("mtime", 0))) > 0.01:
            logger.info("Voice sample changed (mtime) - transcription will be redone")
            return None
    except (OSError, TypeError, ValueError):
        # The sample is not readable right now. Returning what we saved is
        # still better than transcribing it again.
        logger.debug("Voice sample not readable; using the saved transcription")
    return text


def remember(sample: str, text: str) -> bool:
    """
    Save a transcription, unless one is already there.

    Never overwrites: if the user corrected the text by hand, that correction
    is the point of keeping this in a readable file, and it must not be undone
    by the next switch-on.
    """
    if not (text or "").strip():
        return False
    key = normalize(sample)
    data = load()
    if key in data:
        return False
    try:
        st = Path(key).stat()
        mtime, size = st.st_mtime, st.st_size
    except OSError:
        mtime, size = 0.0, 0
    data[key] = {
        "text": text,
        "mtime": mtime,
        "size": size,
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        _write(data)
        logger.info(f"Saved the transcription for {Path(key).name}")
        return True
    except Exception as e:
        logger.warning(f"Could not save the transcription: {e}")
        return False


def summary(sample: str = "") -> dict:
    """What the settings panel shows: known samples and whether one is cached."""
    data = load()
    if not sample:
        # No sample chosen right now. Saying "not transcribed yet" here would
        # read as if nothing had ever been transcribed, which is not what the
        # count says.
        return {"file": str(STORE), "count": len(data), "has_sample": False,
                "cached": False, "text": ""}
    text = lookup(sample)
    return {"file": str(STORE), "count": len(data), "has_sample": True,
            "cached": bool(text), "text": text or "",
            "sample": str(sample)}