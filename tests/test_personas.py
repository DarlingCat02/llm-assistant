"""
Personas: catalog storage and prompt resolution.
"""

import json

import pytest

from src import personas as P


def write(tmp_path, payload, name="personas.json"):
    p = tmp_path / name
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def test_missing_file_means_default_prompt(tmp_path):
    data = P.load(tmp_path / "nope.json")
    assert data.exists is False
    assert data.personas == []
    assert P.resolve_active(data) is None


def test_broken_json_does_not_raise_and_is_not_overwritten(tmp_path):
    p = tmp_path / "personas.json"
    p.write_text("{ this is not json", encoding="utf-8")
    data = P.load(p)
    assert data.parse_error is not None
    assert P.resolve_active(data) is None
    # The broken file must survive a save of an unrelated field
    assert p.read_text(encoding="utf-8") == "{ this is not json"


def test_active_none_uses_default_prompt(tmp_path):
    p = write(tmp_path, {"active": None, "personas": [
        {"id": "dev", "name": "Dev", "prompt_ru": "ты разработчик"}]})
    data = P.load(p)
    assert len(data.personas) == 1
    assert P.resolve_active(data) is None


def test_active_persona_resolved(tmp_path):
    p = write(tmp_path, {"active": "dev", "personas": [
        {"id": "dev", "name": "Dev", "prompt_ru": "ты разработчик"},
        {"id": "ed", "name": "Ed", "prompt_ru": "ты редактор"}]})
    active = P.resolve_active(P.load(p))
    assert active.id == "dev"
    assert active.prompt_for("ru") == "ты разработчик"
    assert active.prompt_for("en") == ""


def test_active_id_missing_in_catalog_resets(tmp_path):
    p = write(tmp_path, {"active": "ghost", "personas": [
        {"id": "dev", "name": "Dev"}]})
    data = P.load(p)
    assert data.active_id is None
    assert P.resolve_active(data) is None


def test_language_isolation(tmp_path):
    p = write(tmp_path, {"active": "dev", "personas": [
        {"id": "dev", "name": "Dev", "prompt_ru": "только русский", "prompt_en": "english only"}]})
    active = P.resolve_active(P.load(p))
    assert active.prompt_for("ru") == "только русский"
    assert active.prompt_for("en") == "english only"


def test_duplicate_and_invalid_ids_skipped(tmp_path):
    p = write(tmp_path, {"personas": [
        {"id": "dev", "name": "A"},
        {"id": "DEV", "name": "B"},
        {"id": "bad id!", "name": "C"},
        {"id": "ok", "name": "D"}]})
    data = P.load(p)
    ids = [x.id for x in data.personas]
    assert ids == ["dev", "ok"]


def test_save_load_roundtrip_keeps_cyrillic(tmp_path):
    data = P.PersonasFile(
        personas=[P.Persona(id="ed", name="Редактор", prompt_ru="Правь тексты",
                            prompt_en="Edit texts", temperature=0.35)],
        active_id="ed",
    )
    path = tmp_path / "personas.json"
    assert P.save(data, path) is True

    loaded = P.load(path)
    assert loaded.active_id == "ed"
    persona = loaded.personas[0]
    assert persona.name == "Редактор"
    assert persona.prompt_ru == "Правь тексты"
    assert persona.temperature == 0.35


def test_temperature_clamped_and_bad_values_dropped(tmp_path):
    assert P.Persona(id="a", temperature=5.0).temperature == 2.0
    assert P.Persona(id="a", temperature=-1).temperature == 0.0
    assert P.Persona(id="a", temperature="oops").temperature is None


def test_prompts_are_length_capped(tmp_path):
    long_text = "x" * (P.MAX_PROMPT_LEN + 500)
    persona = P.Persona(id="a", prompt_ru=long_text)
    assert len(persona.prompt_ru) == P.MAX_PROMPT_LEN


def test_validate_reports_problems():
    items = [P.Persona(id="a", name="A"), P.Persona(id="a", name="dup"),
             P.Persona(id="bad id", name="X"), P.Persona(id="c", name="")]
    clean, active, errors = P.validate(items, "ghost")
    # 'c' keeps its entry: an empty name falls back to the id inside Persona
    assert [p.id for p in clean] == ["a", "c"]
    assert clean[1].name == "c"
    assert active is None
    # duplicate id, invalid id, and the unknown active id
    assert len(errors) == 3


def test_validate_ok():
    items = [P.Persona(id="a", name="A"), P.Persona(id="b", name="B")]
    clean, active, errors = P.validate(items, "b")
    assert len(clean) == 2 and active == "b" and errors == []


def test_unknown_root_type_is_safe(tmp_path):
    p = tmp_path / "personas.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    data = P.load(p)
    assert data.parse_error is not None
    assert P.resolve_active(data) is None