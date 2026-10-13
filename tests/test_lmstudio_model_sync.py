"""
Which LM Studio model does the assistant use at startup?

Regression: the backend took the FIRST loaded model and overrode the configured
one, so a configured qwen-3.5-4b was silently replaced by a 2B that happened to
be loaded - and tool calling stopped working with no visible error.
"""

from backend.main import pick_lmstudio_model


def test_configured_model_is_kept_when_loaded():
    assert pick_lmstudio_model("qwen-3.5-4b", ["qwen-3.5-4b"]) is None
    assert pick_lmstudio_model(
        "qwen-3.5-4b", ["qwen-3.8-2b-uncensored@q8_0", "qwen-3.5-4b"]
    ) is None


def test_the_2b_that_broke_tool_calling_is_not_forced_on_us():
    """The exact situation: 4B configured, 2B listed first."""
    loaded = ["qwen-3.8-2b-uncensored@q8_0", "qwen-3.5-4b"]
    assert pick_lmstudio_model("qwen-3.5-4b", loaded) is None


def test_stale_config_falls_back_to_a_loaded_model():
    """A model in .env that nobody loaded: use what is loaded, not a 2nd load."""
    assert pick_lmstudio_model("old-model", ["some-other-model"]) == "some-other-model"


def test_nothing_loaded_keeps_the_configuration():
    assert pick_lmstudio_model("qwen-3.5-4b", []) is None


def test_configured_id_with_qualifier_is_matched_exactly():
    """LM Studio ids carry @quant suffixes; match the full id, not the family."""
    assert pick_lmstudio_model(
        "qwen-3.8-2b-uncensored@q5_k_m", ["qwen-3.8-2b-uncensored@q8_0"]
    ) == "qwen-3.8-2b-uncensored@q8_0"