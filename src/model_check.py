"""
Say what is wrong with models/ before a feature needs it.

The resolvers only ask whether a folder exists. A half-finished copy - a clone
without the weights, a snapshot cut short, a folder someone renamed - passes
that check and fails much later, inside transformers, with a message about
missing files rather than about the folder. This walks the folders and reports
what it found, in the vocabulary of "which feature is affected".
"""

import logging
from pathlib import Path

from src.stt_engine import WHISPER_ALIASES, resolve_model_dir

logger = logging.getLogger(__name__)

TTS_DIRNAME = "omnivoice"
WEIGHT_SUFFIXES = (".safetensors", ".bin")

# A transformers snapshot always carries at least a config; weights are what
# distinguishes a real model from a folder of metadata.
REQUIRED = ("config.json",)


def _inspect(folder: Path, label: str, hint: str) -> list[str]:
    """Problems with one model folder, or nothing if it looks usable."""
    if not folder.is_dir():
        return [f"{label}: папки {folder} нет — {hint}"]
    if not any(folder.iterdir()):
        return [f"{label}: папка {folder} пустая — {hint}"]
    missing = [name for name in REQUIRED if not (folder / name).is_file()]
    if missing:
        return [f"{label}: в {folder} нет {', '.join(missing)} — похоже на недокачанную копию. {hint}"]
    has_weights = any(
        p.suffix in WEIGHT_SUFFIXES and p.stat().st_size > 0
        for p in folder.rglob("*")
        if p.is_file()
    )
    if not has_weights:
        return [f"{label}: в {folder} нет весов (*.safetensors / *.bin) — {hint}"]
    return []


def _stt_folder(config) -> Path:
    """The folder the speech recognition model must be in - without downloading."""
    spec = str(getattr(config.stt, "model", "") or "").strip()
    if Path(spec).is_dir():
        return Path(spec)
    alias = spec.lower()
    if alias in WHISPER_ALIASES:
        repo_id = WHISPER_ALIASES[alias]
    elif "/" in alias:
        repo_id = spec
    else:
        repo_id = WHISPER_ALIASES["large-v3-turbo"]
    name = repo_id.split("/")[-1]
    return Path(resolve_model_dir(name, f"openai_{name}"))


def check_models(config) -> list[str]:
    """Return a list of warnings; empty means every model looks usable."""
    root = Path(__file__).resolve().parent.parent

    problems = _inspect(
        _stt_folder(config), "Распознавание речи",
        "скачайте install.bat пункт 3 или "
        "venv\\Scripts\\python tests\\fetch_whisper_model.py <алиас>",
    )
    problems += _inspect(
        root / "models" / TTS_DIRNAME, "Озвучка",
        "скачайте install.bat пункт 4",
    )
    return problems


def warn_about_models(config) -> None:
    for problem in check_models(config):
        logger.warning("%s", problem)