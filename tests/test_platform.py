"""The platform layer: keeping analyses up to date, ML export, plugins, the
agent operations (and their MCP wire), and the ``dataorg`` command."""

import io
import json

import numpy as np
import pandas as pd
import pytest

from pyDataOrg import Organizer, agent, plugins
from pyDataOrg.export import feature_frame, write_table


@pytest.fixture(scope="module")
def alloy(tmp_path_factory):
    from pyDataOrg.demo import build_showcase_project

    root = build_showcase_project(tmp_path_factory.mktemp("p") / "Demo",
                                  with_images=False, with_tomography=False)
    org = Organizer(root / "demo.json")
    for stage in ("Synthesis", "Characterization", "Testing", "Computation"):
        org.ingest(f"MetaData/{stage}_dict.py")
    org.save()
    return org


# The validated recipe of notebook 12 and the Demo page.
WAXS = dict(x_range=(2.5, 3.6), n_peaks=2, shape="pseudo_voigt",
            background="linear")


# ---------------------------------------------------------------------------
# kept results: what is done, what is new
# ---------------------------------------------------------------------------

TARGET = "peak_fit@waxs1d"


def test_analyse_new_runs_exactly_the_new_samples(alloy):
    every = alloy.runnable(TARGET)
    assert len(every) == 8 and len(alloy.runnable("peak_fit")) == 8
    first = every[:3]
    alloy.batch("peak_fit", first, settings=WAXS, link=True, write=False,
               verbose=False, modality="waxs1d")
    assert set(alloy.kept_ids(TARGET)) == set(first)
    assert alloy.kept_ids("peak_fit@uvvis") == []
    assert alloy.kept_analyses() == [TARGET]
    status = alloy.status([TARGET]).iloc[0]
    assert (status["kept"], status["new"]) == (3, 5)

    calls = []
    done = alloy.analyse_new([TARGET],
                            progress=lambda i, key, n: calls.append((key, n)))
    assert calls == [(TARGET, 5)]
    assert set(done[TARGET]["sample_id"]) == set(every) - set(first)
    assert (done[TARGET]["status"] == "ran").all()
    assert alloy.new_samples(TARGET) == []
    # the new ones were analysed the way the kept ones were
    assert alloy.kept_settings("peak_fit", every[-1]) == \
        alloy.kept_settings("peak_fit", first[0])


def test_keep_results_loads_what_was_kept_with_the_same_settings(alloy):
    sample = alloy.runnable(TARGET)[0]
    done = alloy.keep_results(TARGET, sample,
                             settings=alloy.kept_settings("peak_fit",
                                                         modality="waxs1d"))
    assert done["peak_fit"]["status"].tolist() == ["loaded"]


def test_same_settings_fills_in_defaults():
    from pyDataOrg.analysis import same_settings

    assert same_settings("peak_fit", {"n_peaks": 1}, {"n_peaks": 1.0})
    assert not same_settings("peak_fit", {"n_peaks": 1}, {"n_peaks": 2})
    assert same_settings("peak_fit", None, {})


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_feature_frame_keeps_numbers_with_enough_coverage():
    table = pd.DataFrame({
        "sample_id": ["a", "b", "c", "d"],
        "s.x": [0.1, 0.2, 0.3, 0.4],
        "s.half": [1.0, np.nan, np.nan, 2.0],
        "s.text": ["p", "q", "p", None],
        "s.same": [5, 5, 5, 5],
        "t.y": ["1", "2", "3", "4"]})
    out = feature_frame(table, min_coverage=0.75)
    assert list(out.columns) == ["s.x", "t.y"] and out.index.name == "sample_id"
    coded = feature_frame(table, categorical="codes", include=["s"])
    assert coded["s.text"].tolist() == [0.0, 1.0, 0.0, -1.0]
    assert "t.y" not in coded and "s.same" not in coded
    assert "s.x" not in feature_frame(table, exclude=["s.x"])


def test_write_table_by_suffix(tmp_path):
    frame = pd.DataFrame({"x": [1.0, np.nan]},
                         index=pd.Index(["a", "b"], name="sample_id"))
    back = pd.read_csv(write_table(frame, tmp_path / "f.csv"), index_col=0)
    assert back.index.tolist() == ["a", "b"]
    rows = json.loads(write_table(frame, tmp_path / "f.json").read_text())
    assert rows[0] == {"sample_id": "a", "x": 1.0}
    with pytest.raises(ValueError, match="unknown table format"):
        write_table(frame, tmp_path / "f.xlsx")


def test_feature_table_through_a_campaign(alloy):
    from pyDataOrg.export import feature_table

    X = feature_table(alloy, campaign="AB-library")
    assert {"x_B", "j_P", "FE_P"} <= set(X.columns)
    assert "S05" in X.index


# ---------------------------------------------------------------------------
# plugins
# ---------------------------------------------------------------------------

def test_a_plugin_registers_once_and_lists_its_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(plugins, "PLUGINS", {})
    monkeypatch.setattr(plugins, "ERRORS", {})
    calls = []
    page = tmp_path / "overview.py"
    page.write_text("import streamlit as st\nst.write('hello')\n")
    plugin = plugins.Plugin("demo_plugin", title="Demo plugin",
                            register=lambda: calls.append(1),
                            pages=[plugins.Page(page, "Overview", "⚗️",
                                                default=True)])
    plugins.register_plugin(plugin)
    assert calls == [1]
    assert plugins.get_plugin("demo_plugin") is plugin
    assert "page: ⚗️ Overview" in plugins.describe()
    assert plugin.pages[0].file() == page.resolve()


def test_page_paths_resolve_beside_a_module():
    page = plugins.Page("pyDataOrg.web_app:views/overview.py", "Overview")
    assert page.file().name == "overview.py" and page.file().exists()


def test_entry_points_load_and_a_broken_one_is_reported(monkeypatch):
    monkeypatch.delenv(plugins.ENV, raising=False)
    monkeypatch.setattr(plugins, "PLUGINS", {})
    monkeypatch.setattr(plugins, "ERRORS", {})
    monkeypatch.setattr(plugins, "_LOADED", False)

    class Entry:
        def __init__(self, name, obj):
            self.name, self.value, self._obj = name, f"{name}:PLUGIN", obj

        def load(self):
            if isinstance(self._obj, Exception):
                raise self._obj
            return self._obj

    good = plugins.Plugin("good")
    entries = [Entry("good", lambda: good), Entry("bad", ImportError("boom")),
               Entry("odd", 42)]
    monkeypatch.setattr(plugins, "_entry_points", lambda: entries)
    loaded = plugins.load_plugins()
    assert list(loaded) == ["good"]
    assert set(plugins.ERRORS) == {"bad", "odd"}
    assert "boom" in plugins.describe()
    with pytest.raises(KeyError, match="failed to load"):
        plugins.get_plugin("bad")

    monkeypatch.setattr(plugins, "PLUGINS", {})
    monkeypatch.setenv(plugins.ENV, "none")
    assert plugins.load_plugins(force=True) == {}


# ---------------------------------------------------------------------------
# agent operations
# ---------------------------------------------------------------------------

def test_operations_answer_in_plain_json(alloy):
    info = agent.call(alloy, "describe_project")
    assert info["n_samples"] == 9 and "/home/" not in info["store"]
    hits = agent.call(alloy, "list_samples",
                      query="`synthesis.composition.nominal_x_B` > 0.5")
    assert hits == ["S05", "S06", "S07", "S08"]
    rows = agent.call(alloy, "sample_table", sample_ids=["S05"],
                      columns=["testing.performance.FE_P_pct"])
    assert set(rows[0]) == {"sample_id", "testing.performance.FE_P_pct"}
    json.dumps(agent.call(alloy, "sample_record", sample_id="S05"))
    assert agent.call(alloy, "list_columns", contains="FE_P") == \
        ["testing.performance.FE_P_pct"]
    assert any(op["key"] == "peak_fit"
               for op in agent.call(alloy, "list_analyses"))


def test_operations_report_errors_instead_of_raising(alloy):
    assert "error" in agent.call(alloy, "nope")
    assert "needs sample_id" in agent.call(alloy, "sample_record")["error"]
    assert "takes no" in agent.call(alloy, "list_samples", bogus=1)["error"]
    assert "KeyError" in agent.call(alloy, "list_measurements",
                                    sample_id="Missing")["error"]


def test_writing_needs_permission(alloy):
    assert "write access" in agent.call(alloy, "save")["error"]
    assert "write access" in agent.call(
        alloy, "run_analysis", key="peak_fit", sample_id="S05",
        settings=WAXS, keep=True)["error"]
    assert "saved" in agent.call(alloy, "save", allow_writes=True)
    names = {spec["name"] for spec in agent.tool_specs()}
    assert "save" not in names and "list_samples" in names
    assert "save" in {s["name"] for s in agent.tool_specs(allow_writes=True)}


def test_tool_specs_in_three_shapes():
    anthropic = agent.tool_specs("anthropic")[0]
    assert set(anthropic) == {"name", "description", "input_schema"}
    openai = agent.tool_specs("openai")[0]
    assert openai["type"] == "function" and "parameters" in openai["function"]
    assert "inputSchema" in agent.tool_specs("mcp")[0]
    with pytest.raises(ValueError):
        agent.tool_specs("other")


def test_run_analysis_returns_its_values(alloy):
    out = agent.call(alloy, "run_analysis", key="peak_fit", sample_id="S05",
                     settings={k: list(v) if isinstance(v, tuple) else v
                               for k, v in WAXS.items()},
                     modality="waxs1d")
    assert out["ok"] and "peak1_center" in out["values"]


def test_propose_next_over_the_demo_campaign(alloy):
    pytest.importorskip("sklearn")
    out = agent.call(alloy, "propose_next", name="AB-library", goals=["j_P"],
                     n=2)
    assert len(out["proposals"]) == 2 and len(out["trained_on"]) == 8


def test_the_mcp_wire(alloy):
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "list_samples", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "save", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 5, "method": "resources/list"},
    ]
    out = io.StringIO()
    agent.serve_mcp(alloy, stdin=io.StringIO(
        "\n".join(json.dumps(m) for m in lines) + "\nnot json\n"), stdout=out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3, 4, 5, None]
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert any(t["name"] == "describe_project"
               for t in replies[1]["result"]["tools"])
    assert json.loads(replies[2]["result"]["content"][0]["text"])[0] == "S01"
    assert replies[3]["result"]["isError"] is True
    assert replies[4]["error"]["code"] == -32601
    assert replies[5]["error"]["code"] == -32700


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------

def test_dataorg_command(alloy, tmp_path, capsys):
    from pyDataOrg.cli import main

    assert main(["--help"]) == 0
    assert "dataorg gui" in capsys.readouterr().out
    assert main(["ops"]) == 0 and "describe_project" in capsys.readouterr().out
    assert main(["ops", "list_samples"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "list_samples"
    assert main(["ops", "list_samples", "--store", str(alloy.path)]) == 0
    assert "S05" in capsys.readouterr().out
    assert main(["ops", "save", "--store", str(alloy.path)]) == 1
    capsys.readouterr()
    assert main(["features", str(alloy.path), str(tmp_path / "X.csv"),
                 "--campaign", "AB-library"]) == 0
    assert pd.read_csv(tmp_path / "X.csv", index_col=0).shape[0] == 9
    assert main(["tree", str(alloy.path.parent), "--depth", "1"]) == 0
    assert "MetaData" in capsys.readouterr().out
    assert main(["plugins"]) == 0
    assert main(["nonsense"]) == 2
