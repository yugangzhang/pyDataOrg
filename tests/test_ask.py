"""Asking the records: which models, when asking is on, what the model is
given, and that a run never raises. No real model is called — a fake tool
(this Python, reading the prompt on stdin) stands in for one."""

import json
import sys

import pytest

from pyDataOrg import Organizer
from pyDataOrg import ask
from pyDataOrg.analysis.result import AnalysisResult


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for name in (ask.ASK_ENV, ask.DEFAULT_ENV, ask.MODEL_ENV, ask.PASSWORD_ENV,
                 ask.SECURE_ENV, ask.USERS_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(ask.CONFIG_ENV, str(tmp_path / "none.json"))


@pytest.fixture
def org(tmp_path):
    org = Organizer(tmp_path / "org.json")
    org.ingest(synthesis={
        "S01": {"temperature_C": 90.0, "data_path": "/somewhere/S01"},
        "S02": {"temperature_C": 95.0},
        "S10": {"temperature_C": 100.0},
    })
    result = AnalysisResult("peak_fit", sample_id="S02",
                            values={"centre_nm": 523.5, "fwhm_nm": 61.0})
    org.link_result(result, folder=tmp_path / "Results", write=False)
    return org


def _fake(code: str, title: str = "fake") -> ask.Backend:
    return ask.Backend(f"command:{title}", title, (sys.executable, "-c", code))


# ---------------------------------------------------------------------------
# When asking is on
# ---------------------------------------------------------------------------

def test_a_local_gui_asks_a_shared_one_does_not(monkeypatch):
    assert ask.enabled()
    monkeypatch.setenv(ask.PASSWORD_ENV, "abc123")
    assert not ask.enabled()
    monkeypatch.setenv(ask.ASK_ENV, "1")              # its owner turns it on
    assert ask.enabled()
    monkeypatch.setenv(ask.ASK_ENV, "off")
    monkeypatch.delenv(ask.PASSWORD_ENV)
    assert not ask.enabled()


def test_secure_mode_counts_as_shared(monkeypatch):
    monkeypatch.setenv(ask.SECURE_ENV, "1")
    assert not ask.enabled()


# ---------------------------------------------------------------------------
# Which models
# ---------------------------------------------------------------------------

def test_the_users_models_come_first(monkeypatch, tmp_path):
    config = tmp_path / "ask.json"
    config.write_text(json.dumps({
        "models": [{"tool": "command", "title": "mine", "argv": [sys.executable, "-c", ""]},
                   {"tool": "nonsense"}],
        "env": {"SOME_KEY": "$NOT_SET_ANYWHERE", "PLAIN": "x"}}))
    monkeypatch.setenv(ask.CONFIG_ENV, str(config))
    found = ask.backends()
    assert found[0].key == "command:mine"
    assert found[0].env == {"PLAIN": "x"}           # an unset variable is left out
    assert all(b.available for b in found)
    every = ask.backends(include_missing=True)
    assert {"codex", "claude", "gemini"} <= {b.title for b in every}


def test_a_default_can_be_named(monkeypatch, tmp_path):
    config = tmp_path / "ask.json"
    config.write_text(json.dumps({"models": [
        {"tool": "command", "title": "one", "argv": [sys.executable]},
        {"tool": "command", "title": "two", "argv": [sys.executable]}]}))
    monkeypatch.setenv(ask.CONFIG_ENV, str(config))
    monkeypatch.setenv(ask.DEFAULT_ENV, "two")
    assert ask.backends()[0].title == "two"


# ---------------------------------------------------------------------------
# What the model is given
# ---------------------------------------------------------------------------

IDS = ["Sample000001", "Sample000002", "Sample000055", "S7"]


@pytest.mark.parametrize("question, named", [
    ("What is Sample000055?", ["Sample000055"]),
    ("compare sample000002 and SAMPLE000001", ["Sample000002", "Sample000001"]),
    ("samples 1, 2 and 55", ["Sample000001", "Sample000002", "Sample000055"]),
    ("what about #55 and S7", ["Sample000055", "S7"]),
    ("Sample 12345 is not there", []),
    ("nothing named", []),
])
def test_the_samples_a_question_names(question, named):
    assert ask.mentioned(question, IDS) == named


def test_a_number_two_ids_end_in_names_neither():
    assert ask.mentioned("sample 1", ["A1", "B1"]) == []


def test_the_context_holds_the_named_samples_records(org):
    text = ask.organizer_context(org, question="Why is S02 different?",
                                 sections=[("Goals", ["- the narrowest band"]),
                                           ("Empty", [])])
    assert "## Goals" in text and "Empty" not in text
    assert "## Full records of S02" in text
    assert '"centre_nm":523.5' in text                 # its kept result
    assert "## Full records of S01" not in text
    samples = text.split("one line each")[1]
    assert "S10" in samples and "100" in samples
    assert "/somewhere" not in samples                 # where files are: left out


def test_the_context_is_cut_to_length(org):
    assert len(ask.organizer_context(org, max_chars=200)) <= 200


def test_a_table_and_its_columns_can_be_given(org):
    import pandas as pd

    table = pd.DataFrame({"sample": ["S01", "S02"], "goal": [0.5, float("nan")],
                          "other": ["a", "b"]})
    text = ask.organizer_context(org, table=table, columns=["sample", "goal"])
    lines = text.split("one line each\n")[1].splitlines()
    assert lines == ["sample | goal", "S01 | 0.5", "S02"]


def test_the_prompt_says_the_rules_then_the_records():
    text = ask.prompt("How many?", "RECORDS HERE", [("q1", "a1")],
                      project="the demo", rules=["Speak plainly."])
    assert text.index("Answer only from the records") < text.index("RECORDS HERE")
    assert "- Speak plainly." in text and "the demo" in text
    assert "Q: q1" in text and text.rstrip().endswith("Question: How many?")


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------

def test_an_answer_comes_from_the_tool(org):
    tool = _fake("import sys; t = sys.stdin.read(); "
                 "print('saw S02' if 'Full records of S02' in t else 'no')")
    text = ask.organizer_context(org, question="S02?")
    answer = ask.ask("S02?", text, backend=tool, samples=["S02"])
    assert answer.error == ""
    assert answer.text == "saw S02"
    assert answer.samples == ["S02"] and answer.context == text
    assert answer.as_dict()["backend"] == "command:fake"


def test_a_failed_run_is_an_error_not_an_exception():
    answer = ask.ask("?", "", backend=_fake("import sys; sys.exit(3)"))
    assert "exit 3" in answer.error


def test_a_missing_tool_is_an_error():
    gone = ask.Backend("gone", "gone", ("no-such-ai-tool-here",))
    assert "not installed" in ask.ask("?", "", backend=gone).error


def test_no_model_at_all_is_an_error(monkeypatch):
    monkeypatch.setattr(ask, "backends", lambda **_: [])
    answer = ask.ask("?", "records")
    assert answer.error and answer.context == "records"


def test_a_slow_tool_times_out():
    answer = ask.ask("?", "", backend=_fake("import time; time.sleep(5)"), timeout=0.5)
    assert "longer than" in answer.error
