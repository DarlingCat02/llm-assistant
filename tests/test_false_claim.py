import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _claims():
    from backend.main import claims_an_action_was_done
    return claims_an_action_was_done


def test_detects_the_false_claim_that_started_the_bug():
    """'Блокнот открыт.' with no tool call is the exact case that misled us."""
    f = _claims()
    for text in (
        "Блокнот открыт.",
        "Блокнот открыт",
        "Готово, файл создан.",
        "Приложение запущено.",
        "Notepad opened.",
        "File created.",
    ):
        assert f(text), text


def test_ignores_ordinary_answers():
    f = _claims()
    for text in (
        "Привет!",
        "Какая сегодня погода?",
        "Я не знаю, что это",
        "",
        None,
    ):
        assert not f(text), text


def test_only_suspicion_not_verdict():
    """
    The marker alone is not proof of anything - it is used together with
    'no tool ran', which is the real signal. A sentence containing 'открыт'
    while a tool did run must not be treated as a lie.
    """
    f = _claims()
    # Documented behaviour: this returns True for any completion wording, and
    # the caller pairs it with actions == [] before acting on it.
    assert f("Файл открыт и прочитан") is True