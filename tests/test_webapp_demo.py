"""Tests for the Demo page — notebooks 10 → 11 → 12 with buttons, on Cu–Au.

Driven through ``AppTest`` against the showcase campaign generated into
``tmp_path`` (via ``$NANOORGANIZER_DEMO_ROOT``), so nothing is written outside
the test's own folder. One test clicks the whole walk in the order a user
would — simulate, create, ingest, link, save, batch, reload, hand over — and
checks every click for a clean page. The others start from an organizer built
with the same package calls the page makes, which is faster than clicking and
is itself a check that the page and the notebooks agree.
"""

import json

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

from pathlib import Path  # noqa: E402

from NanoOrganizer import Organizer  # noqa: E402
from NanoOrganizer.demo import (  # noqa: E402
    build_showcase_project, showcase_truth,
)

VIEWS = Path(__file__).resolve().parents[1] / "NanoOrganizer" / "web_app" / "views"
DEMO = VIEWS / "demo.py"
HOME = VIEWS.parent / "Home.py"

STAGES = ("Synthesis", "Characterization", "Testing", "Computation")
BY_HAND = {"tem": "TEMData", "sem": "SEMData", "dls": "DLSData",
           "tomo": "TomoData"}
WALK = ("nano_demo_simulate", "nano_demo_create", "nano_demo_ingest",
        "nano_demo_link", "nano_demo_save")


def _why(app) -> str:
    return "; ".join(f"{e.message}" for e in app.exception)


def _clean(app, step: str) -> None:
    assert not app.exception, f"{step}: {_why(app)}"
    assert not app.error, f"{step}: {[e.value for e in app.error]}"
    # The gallery reports a panel it could not draw as a warning.
    assert not app.warning, f"{step}: {[w.value for w in app.warning]}"


def _click(app, key: str):
    app.button(key=key).click().run()
    _clean(app, key)
    return app


def _metrics(app) -> dict:
    return {m.label: m.value for m in app.metric}


def _page():
    app = AppTest.from_file(str(DEMO), default_timeout=300)
    app.run()
    _clean(app, "first run")
    return app


@pytest.fixture
def demo_root(tmp_path, monkeypatch):
    """Point demo_root() at the test's own folder, and keep security off."""
    monkeypatch.setenv("NANOORGANIZER_DEMO_ROOT", str(tmp_path))
    for name in ("NANOORGANIZER_SECURE_MODE", "NANOORGANIZER_USER_MODE",
                 "NANOORGANIZER_ALLOWED_ROOTS", "NANOORGANIZER_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)             # no stray ./.config/pyViz.conf
    return tmp_path / "CuAu"


@pytest.fixture
def saved(demo_root):
    """cuau.json built with the calls notebooks 10 and 11 make."""
    campaign = demo_root / "Campaign"
    build_showcase_project(campaign)
    showcase_truth().to_csv(demo_root / "truth.csv", index=False)
    org = Organizer(demo_root / "cuau.json", name="Cu-Au CO2RR library")
    for stage in STAGES:
        org.ingest(campaign / "MetaData" / f"{stage}_dict.py")
    for sample in org.ids():
        for modality, folder in BY_HAND.items():
            source = campaign / folder / sample
            if source.is_dir():
                org.link(sample, modality, str(source),
                         stage="characterization")
    org.save()
    return demo_root


@pytest.fixture
def reopened(saved):
    """The page with the saved organizer reopened."""
    app = _page()
    _click(app, "nano_demo_create")
    return app, saved


def test_every_tab_waits_for_its_prerequisite(demo_root):
    """Nothing built yet: each tab points back to the step it needs."""
    app = _page()

    messages = " | ".join(item.value for item in app.info)
    assert "simulate the data first" in messages
    assert "Build the organizer first" in messages
    assert "Run the campaign's analyses first" in messages
    assert not demo_root.exists(), "rendering must not write anything"
    # The model is drawn before anything is written: it is the point.
    assert _metrics(app)["Techniques"] == "15"


def test_simulate_writes_the_campaign_and_the_answer_key(demo_root):
    app = _page()
    assert app.text_input(key="nano_demo_root").value == str(demo_root)

    _click(app, "nano_demo_simulate")
    campaign = demo_root / "Campaign"
    assert sorted(p.name for p in (campaign / "MetaData").glob("*_dict.py")) \
        == [f"{s}_dict.py" for s in sorted(STAGES)]
    assert (demo_root / "truth.csv").is_file()
    assert len(list((campaign / "TEMData").rglob("*.tif"))) == 24

    metrics = _metrics(app)
    assert metrics["Metadata modules"] == "4"
    assert metrics["Folders with no record"] == "4"
    # The tree and a peek into one metadata module are shown, not just written.
    shown = " ".join(block.value for block in app.code)
    assert "TEMData" in shown and "UVVis" in shown


def test_the_whole_walk_recovers_the_hidden_number(demo_root):
    """Simulate → build → batch → compare → reload → hand over, by clicking."""
    app = _page()
    for key in WALK:
        _click(app, key)

    store = demo_root / "cuau.json"
    org = Organizer(store)
    catalog = org.catalog(counts=True)
    assert len(org.project) == 9 and len(org.project.measurements()) == 144
    assert (catalog.loc["CuAu09"] == 0).all(), "the failed run has no data"
    assert (catalog.loc["CuAu05", ["tem", "sem"]] == 3).all(), \
        "note.txt must not be linked as a micrograph"
    assert catalog["tomo"].sum() == 2, "tomography is on two samples only"
    # Paths are recorded exactly as linked, not rewritten.
    text = store.read_text()
    assert str(demo_root / "Campaign" / "TEMData" / "CuAu05") in text
    assert json.loads(text), "cuau.json is plain JSON"

    # The kernel ran on the default window: Vegard gives CuAu05's x back.
    metrics = _metrics(app)
    assert float(metrics["R²"]) > 0.999
    assert abs(float(metrics["x(Au) from Vegard"]) - 0.55) < 0.01
    assert int(metrics["Particles"]) > 20

    _click(app, "nano_demo_batch")
    assert any("72/72" in item.value for item in app.success)
    results = sorted((demo_root / "results").glob("*.result.npz"))
    assert len(results) == 16, "two peak fits per sample, linked"

    # E: three techniques recover the composition; the volcano peaks mid-way.
    metrics = _metrics(app)
    assert float(metrics["EDS composition within"].split()[-1]) < 0.03
    assert float(metrics["WAXS composition within"].split()[-1]) < 0.01
    assert float(metrics["Plasmon band within"].split()[0]) < 2.0
    assert metrics["Most CO"] == "CuAu05"

    # F: a fresh Organizer off disk, no refitting.
    before = [p.stat().st_mtime for p in results]
    _click(app, "nano_demo_reload")
    assert [p.stat().st_mtime for p in results] == before, \
        "reloading must not rewrite the stored fits"

    _click(app, "nano_demo_handover")
    assert app.session_state["nano_workbench"] is \
        app.session_state["nano_demo_org"]


def test_a_saved_organizer_reopens_in_a_new_session(saved):
    app = _page()
    button = app.button(key="nano_demo_create")
    assert button.label == "Reopen cuau.json"
    button.click().run()
    _clean(app, "reopen")
    org = app.session_state["nano_demo_org"]
    assert len(org.project.measurements(modality="tem")) == 8
    assert "Build the organizer first" not in " ".join(i.value for i in app.info)


def test_start_over_removes_only_the_organizer(reopened):
    app, root = reopened
    (root / "results").mkdir()
    (root / "results" / "x.result.npz").write_bytes(b"")
    app.run()

    app.checkbox(key="nano_demo_sure").check().run()
    _click(app, "nano_demo_reset")
    assert not (root / "cuau.json").exists()
    assert not (root / "results").exists()
    # The campaign and the answer key are untouched.
    assert (root / "Campaign" / "MetaData" / "Synthesis_dict.py").is_file()
    assert (root / "truth.csv").is_file()
    assert len(list((root / "Campaign").rglob("*.tif"))) == 48
    assert "nano_demo_org" not in app.session_state


def test_restricted_mode_refuses_a_root_outside_the_fence(demo_root, tmp_path,
                                                         monkeypatch):
    fence = tmp_path / "allowed"
    fence.mkdir()
    monkeypatch.setenv("NANOORGANIZER_USER_MODE", "1")
    monkeypatch.setenv("NANOORGANIZER_ALLOWED_ROOTS", str(fence))

    app = AppTest.from_file(str(DEMO), default_timeout=120)
    app.run()
    assert not app.exception, _why(app)
    assert any("outside the folders" in e.value for e in app.error)
    assert not app.button, "nothing may be clickable outside the fence"


def test_navigation_reaches_the_demo_page(demo_root):
    app = AppTest.from_file(str(HOME), default_timeout=300)
    app.run()
    assert not app.exception, _why(app)
    app.switch_page("views/demo.py").run()
    assert not app.exception, _why(app)
    assert [t.value for t in app.title] == ["🎓 Demo"]


def test_each_group_draws_and_the_tomogram_turns(reopened):
    """The gallery draws all four groups statically on every run (a panel
    that fails is a warning, which ``_clean`` refuses); here the free picker
    shows the volume interactive in two modes, and a log-scaled 2D image."""
    app, _ = reopened
    assert app.selectbox(key="nano_demo_vis_s").value == "CuAu01"
    assert app.selectbox(key="nano_demo_vis_m").value == "tomo"

    app.radio(key="nano_demo_vis_engine").set_value("interactive").run()
    _clean(app, "interactive tomo")
    app.selectbox(key="nano_demo_vis_mode").select("slices").run()
    _clean(app, "interactive slices")
    app.selectbox(key="nano_demo_vis_m").select("saxs2d").run()
    _clean(app, "interactive saxs2d")


def test_a_worse_model_shows_in_the_residual_not_the_headline(reopened):
    """The lesson of part D: one peak across two reflections drops R², while
    the sharp (111) still pins the centre — the residual is the tell."""
    app, _ = reopened
    good = _metrics(app)
    app.number_input(key="nano_demo_fit_n").set_value(1).run()
    _clean(app, "one peak")
    bad = _metrics(app)
    assert float(bad["R²"]) < float(good["R²"]) - 0.1
    assert abs(float(bad["x(Au) from Vegard"])
               - float(good["x(Au) from Vegard"])) < 0.02
