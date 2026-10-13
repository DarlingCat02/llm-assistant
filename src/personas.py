"""
Personas: switchable behaviour presets for the assistant.

Storage: personas.json next to apps.json (git-ignored).
Design rules:
- A missing or broken file must never break the app -> fall back to "no persona"
  (active = None), which means the standard system prompt.
- Never overwrite a file we could not parse (user data safety).
- A persona is a LAYER over the base prompt, not a replacement, so switching
  back to "none" always restores the default behaviour.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

PERSONAS_PATH = Path(__file__).parent.parent / "personas.json"

MAX_PERSONAS = 20
MAX_PROMPT_LEN = 8000
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


@dataclass
class Persona:
    """A single persona preset."""

    id: str
    name: str = ""
    avatar: str | None = None
    prompt_ru: str = ""
    prompt_en: str = ""
    temperature: float | None = None

    def __post_init__(self):
        self.id = str(self.id or "").strip().lower()
        self.name = (self.name or self.id).strip()
        self.prompt_ru = (self.prompt_ru or "")[:MAX_PROMPT_LEN]
        self.prompt_en = (self.prompt_en or "")[:MAX_PROMPT_LEN]
        if self.avatar is not None:
            self.avatar = str(self.avatar) or None
        if self.temperature is not None:
            try:
                self.temperature = max(0.0, min(2.0, float(self.temperature)))
            except (TypeError, ValueError):
                self.temperature = None

    @property
    def is_valid(self) -> bool:
        return bool(_ID_RE.match(self.id))

    def prompt_for(self, lang: str) -> str:
        """Prompt for a UI language ('' means: use the base prompt)."""
        return (self.prompt_ru if lang == "ru" else self.prompt_en).strip()


@dataclass
class PersonasFile:
    personas: list[Persona] = field(default_factory=list)
    active_id: str | None = None
    exists: bool = False
    parse_error: str | None = None


def load(path: Path | str | None = None) -> PersonasFile:
    """
    Read personas.json. Never raises.

    Returns:
        PersonasFile: `active_id` is None when no persona is selected.
    """
    p = Path(path) if path else PERSONAS_PATH
    if not p.exists():
        return PersonasFile(exists=False)

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"personas.json is unreadable ({e}); using the default prompt")
        return PersonasFile(exists=True, parse_error=str(e))

    if not isinstance(raw, dict):
        logger.warning("personas.json has an unexpected format; using the default prompt")
        return PersonasFile(exists=True, parse_error="root is not an object")

    items = raw.get("personas")
    personas: list[Persona] = []
    seen: set[str] = set()
    if isinstance(items, list):
        for item in items[:MAX_PERSONAS]:
            if not isinstance(item, dict):
                continue
            try:
                p = Persona(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    avatar=item.get("avatar"),
                    prompt_ru=item.get("prompt_ru", "") or "",
                    prompt_en=item.get("prompt_en", "") or "",
                    temperature=item.get("temperature"),
                )
            except Exception:
                continue
            if not p.is_valid or p.id in seen:
                continue
            seen.add(p.id)
            personas.append(p)

    active = raw.get("active")
    active_id = str(active).strip().lower() if isinstance(active, str) and active else None
    if active_id and active_id not in seen:
        logger.warning(f"Active persona '{active_id}' is missing from the catalog; using the default prompt")
        active_id = None

    return PersonasFile(personas=personas, active_id=active_id, exists=True)


def save(data: PersonasFile, path: Path | str | None = None) -> bool:
    """Write personas.json atomically. Returns False on failure."""
    p = Path(path) if path else PERSONAS_PATH
    payload = {
        "active": data.active_id,
        "personas": [asdict(x) for x in data.personas[:MAX_PERSONAS]],
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
        return True
    except Exception as e:
        logger.error(f"Cannot save personas.json: {e}")
        return False


def resolve_active(data: PersonasFile) -> Persona | None:
    """Return the active persona, or None when the default prompt is used."""
    if not data.active_id:
        return None
    for p in data.personas:
        if p.id == data.active_id:
            return p
    return None


def validate(personas: list[Persona], active_id: str | None) -> tuple[list[Persona], str | None, list[str]]:
    """
    Validate a catalog coming from the API.

    Returns:
        tuple: (clean_personas, clean_active_id, error_messages)
    """
    errors: list[str] = []
    clean: list[Persona] = []
    seen: set[str] = set()

    if len(personas) > MAX_PERSONAS:
        errors.append(f"Too many personas (max {MAX_PERSONAS})")
        personas = personas[:MAX_PERSONAS]

    for item in personas:
        if not isinstance(item, Persona):
            item = Persona(**item) if isinstance(item, dict) else None
            if item is None:
                errors.append("Skipped a malformed persona entry")
                continue
        if not item.is_valid:
            errors.append(f"Invalid persona id: '{item.id}'")
            continue
        if item.id in seen:
            errors.append(f"Duplicate persona id: '{item.id}'")
            continue
        if not item.name:
            errors.append(f"Persona '{item.id}' has no name")
            continue
        seen.add(item.id)
        clean.append(item)

    active = (active_id or "").strip().lower() or None if isinstance(active_id, str) else None
    if active and active not in seen:
        errors.append(f"Active persona '{active}' is not in the catalog")
        active = None

    return clean, active, errors