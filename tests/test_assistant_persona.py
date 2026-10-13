"""
Assistant persona application (layer on top of the system prompt).
"""

import pytest

from src.personas import Persona


class FakeLLM:
    def __init__(self):
        self.persona_ru = ""
        self.persona_en = ""
        self.temperature = 0.7

    def set_persona_prompt(self, ru="", en=""):
        self.persona_ru = ru
        self.persona_en = en

    def refresh_system_prompt(self):
        pass

    def get_system_prompt(self):
        base = "BASE"
        layer = self.persona_ru if self.persona_ru else self.persona_en
        return f"{base}\n\n{layer}" if layer else base

    def _get_base_system_prompt(self):
        return "BASE"

    _config = type("C", (), {"temperature": 0.7})()


@pytest.fixture
def assistant(monkeypatch):
    from src.main import Assistant
    a = Assistant.__new__(Assistant)
    a._llm = FakeLLM()
    a._persona = None
    a._logger = type("L", (), {"info": lambda *a, **k: None, "warning": lambda *a, **k: None})()
    return a


def test_no_persona_uses_default_prompt(assistant):
    assistant.apply_persona(None)
    assert assistant.persona is None
    assert assistant._llm.get_system_prompt() == "BASE"


def test_apply_persona_sets_prompt_and_temperature(assistant):
    p = Persona(id="ed", name="Editor", prompt_ru="Ты редактор", prompt_en="You are an editor",
                temperature=0.3)
    assistant.apply_persona(p)
    assert assistant.persona is p
    assert assistant._llm.persona_ru == "Ты редактор"
    assert assistant._llm.get_system_prompt().endswith("Ты редактор")
    assert assistant._llm._config.temperature == 0.3


def test_switch_back_and_forth(assistant):
    a = Persona(id="a", name="A", prompt_ru="A-layer")
    b = Persona(id="b", name="B", prompt_ru="B-layer")

    assistant.apply_persona(a)
    assert assistant._llm.get_system_prompt().endswith("A-layer")

    assistant.apply_persona(b)
    assert assistant._llm.get_system_prompt().endswith("B-layer")

    assistant.apply_persona(None)
    assert assistant._llm.get_system_prompt() == "BASE"


def test_no_argument_loads_from_file(assistant, tmp_path, monkeypatch):
    """apply_persona() without args reads personas.json."""
    from src import personas as P
    monkeypatch.setattr(P, "PERSONAS_PATH", tmp_path / "personas.json")
    P.save(P.PersonasFile(personas=[Persona(id="t", name="T", prompt_ru="Из файла")],
                         active_id="t"), tmp_path / "personas.json")

    assistant.apply_persona()
    assert assistant.persona.id == "t"
    assert assistant._llm.get_system_prompt().endswith("Из файла")


def test_missing_file_keeps_default_prompt(assistant, tmp_path, monkeypatch):
    from src import personas as P
    monkeypatch.setattr(P, "PERSONAS_PATH", tmp_path / "missing.json")
    assistant.apply_persona()
    assert assistant.persona is None
    assert assistant._llm.get_system_prompt() == "BASE"