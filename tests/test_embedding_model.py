"""
The embedding model has to be found, not hoped for.

It used to be loaded by bare name with local_files_only=True, which made
sentence_transformers look in the per-user HuggingFace cache. That cache travels
with the person, not with the project: on a machine without it the load raised,
Assistant.initialize() failed and every request came back 503. These tests pin
the behaviour that replaced it.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src import memory_manager as mm

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def restore_offline_state():
    """_go_offline() flips a process-wide switch, and huggingface_hub keeps a
    copy of it in a constant. Both are restored, or the first test that takes
    the offline path decides the outcome of every later one."""
    from huggingface_hub import constants as hf_constants

    env_before = os.environ.get("HF_HUB_OFFLINE")
    constant_before = hf_constants.HF_HUB_OFFLINE
    try:
        yield
    finally:
        if env_before is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = env_before
        hf_constants.HF_HUB_OFFLINE = constant_before


def test_import_does_not_force_offline_mode():
    """HF_HUB_OFFLINE is a process-wide switch. Set at import time it also killed
    the download that stt_engine triggers on demand, so a machine without
    models/ could never fetch anything."""
    code = ("import os, sys; sys.path.insert(0, %r); import src.memory_manager; "
            "print(os.environ.get('HF_HUB_OFFLINE', 'unset'))" % str(REPO_ROOT))
    env = {k: v for k, v in os.environ.items() if k != "HF_HUB_OFFLINE"}
    env["PYTHONPATH"] = str(REPO_ROOT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, env=env, timeout=300, cwd=str(REPO_ROOT))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "unset"


def test_model_already_in_the_project_is_used_as_is(tmp_path, monkeypatch):
    target = tmp_path / "models" / mm.EMBEDDING_DIRNAME
    target.mkdir(parents=True)
    (target / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)

    def explode(*args, **kwargs):
        raise AssertionError("must not download when the model is already there")

    monkeypatch.setattr("huggingface_hub.snapshot_download", explode)
    assert mm.ensure_embedding_model(tmp_path) == target


def test_missing_model_downloads_into_the_project(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    calls = {}

    def fake_download(repo_id=None, local_dir=None, allow_patterns=None, **kw):
        calls["repo_id"] = repo_id
        calls["allow_patterns"] = allow_patterns
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        (Path(local_dir) / "model.safetensors").write_bytes(b"x")
        return local_dir

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)
    result = mm.ensure_embedding_model(tmp_path)

    assert result == tmp_path / "models" / mm.EMBEDDING_DIRNAME
    assert calls["repo_id"] == mm.EMBEDDING_REPO
    # ONNX, OpenVINO, TensorFlow and Rust copies are 930 MB of the same weights.
    # Only the PyTorch files this app loads are fetched.
    assert "model.safetensors" in calls["allow_patterns"]
    assert not any(word in pattern
                   for pattern in calls["allow_patterns"]
                   for word in ("onnx", "openvino", "tf_model", "rust_model"))


def test_offline_user_gets_an_explainable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    with pytest.raises(RuntimeError) as err:
        mm.ensure_embedding_model(tmp_path)
    message = str(err.value)
    assert str(tmp_path) in message
    assert "fetch_whisper_model.py" in message


def test_offline_requested_also_sees_the_import_time_flag(tmp_path, monkeypatch):
    """huggingface_hub copies the variable into a constant at import, so the
    environment alone is not the whole truth."""
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    from huggingface_hub import constants as hf_constants
    monkeypatch.setattr(hf_constants, "HF_HUB_OFFLINE", True, raising=False)
    assert mm._offline_requested() is True