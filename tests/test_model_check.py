"""
models/ has to be checked, not assumed.

The resolvers ask only whether a folder exists. An empty folder, a clone without
weights or a renamed folder all pass that test and then fail inside
transformers - with a message about missing files rather than about the folder
the user actually got wrong.
"""

import json
from pathlib import Path

import pytest

from src import model_check


class _Cfg:
    def __init__(self, model):
        self.stt = type("S", (), {"model": model})()


def _fake_stt_folder(tmp_path, monkeypatch, folder_name):
    """Point the checker at a folder inside tmp_path."""
    target = tmp_path / "models" / folder_name
    target.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(model_check, "_stt_folder", lambda config: target)
    return target


def _make_usable(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "config.json").write_text("{}", encoding="utf-8")
    (folder / "model.safetensors").write_bytes(b"weights")
    return folder


def test_missing_folder_names_the_path_and_the_way_out(tmp_path, monkeypatch):
    folder = _fake_stt_folder(tmp_path, monkeypatch, "whisper-tiny")
    problems = model_check.check_models(_Cfg("tiny"))
    stt_problems = [p for p in problems if "Распознавание" in p]
    assert stt_problems, problems
    assert str(folder) in stt_problems[0]
    assert "fetch_whisper_model.py" in stt_problems[0]


def test_empty_folder_is_reported(tmp_path, monkeypatch):
    _fake_stt_folder(tmp_path, monkeypatch, "whisper-tiny")
    problems = [p for p in model_check.check_models(_Cfg("tiny"))
                if "Распознавание" in p]
    assert any("пустая" in p for p in problems), problems


def test_folder_without_weights_is_reported(tmp_path, monkeypatch):
    folder = _fake_stt_folder(tmp_path, monkeypatch, "whisper-tiny")
    (folder / "config.json").write_text("{}", encoding="utf-8")   # config only
    problems = [p for p in model_check.check_models(_Cfg("tiny"))
                if "Распознавание" in p]
    assert any("весов" in p for p in problems), problems


def test_usable_folder_produces_no_complaint(tmp_path, monkeypatch):
    _make_usable(_fake_stt_folder(tmp_path, monkeypatch, "whisper-tiny"))
    problems = [p for p in model_check.check_models(_Cfg("tiny"))
                if "Распознавание" in p]
    assert problems == []


def test_alias_large_maps_to_v3():
    """STT_MODEL=large means the whisper-large-v3 folder, not whisper-large -
    the difference between 'it downloads it' and 'it is already there'."""
    cfg = _Cfg("large")
    assert model_check._stt_folder(cfg).name == "whisper-large-v3"


def test_explicit_folder_path_is_taken_as_is(tmp_path):
    folder = tmp_path / "my-own-whisper"
    folder.mkdir()
    assert model_check._stt_folder(_Cfg(str(folder))) == folder


def test_tts_folder_is_checked_too(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "models").mkdir(parents=True)
    monkeypatch.setattr(model_check, "__file__", str(root / "src" / "model_check.py"))
    _fake_stt_folder(root, monkeypatch, "whisper-tiny")
    _make_usable(root / "models" / "whisper-tiny")

    problems = model_check.check_models(_Cfg("tiny"))
    assert any("Озвучка" in p for p in problems), problems
    assert "omnivoice" in " ".join(problems)


def test_no_complaints_when_both_are_present(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "models").mkdir(parents=True)
    monkeypatch.setattr(model_check, "__file__", str(root / "src" / "model_check.py"))
    _make_usable(_fake_stt_folder(root, monkeypatch, "whisper-tiny"))
    _make_usable(root / "models" / "omnivoice")

    assert model_check.check_models(_Cfg("tiny")) == []