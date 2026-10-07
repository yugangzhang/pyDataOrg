"""Tests for the Demo page — notebooks 10 → 11 → 12 with buttons.

Driven through ``AppTest`` against a lab simulated into ``tmp_path`` (via
``$NANOORGANIZER_DEMO_ROOT``), so nothing is written outside the test's own
folder. The buttons are clicked in the order a user would: simulate, create,
ingest, link, save, batch, reload — and every click is checked for a clean
page, not just the last one.
"""

import json

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

from pathlib import Path  # noqa: E402

from NanoOrganizer import Organizer  # noqa: E402

VIEWS = Path(__file__).resolve().parents[1] / "NanoOrganizer" / "web_app" / "views"
DEMO = VIEWS / "demo.py"
HOME = VIEWS.parent / "Home.py"

ORDER = ("nano_demo_simulate", "nano_demo_create", "nano_demo_ingest",
         "nano_demo_link", "nano_demo_save")


def _why(app) -> str:
    return "; ".join(f"{e.message}" for e in app.exception)


def _clean(app, step: str) -> None:
    assert not app.exception, f"{step}: {_why(app)}"
    assert not app.error, f"{step}: {[e.value for e in app.error]}"


def _click(app, key: str):
    app.button(key=key).click().run()
    _clean(app, key)
    return app


@pytest.fixture
def lab_root(tmp_path, monkeypatch):
    """Point demo_root() at the test's own folder, and keep security off."""
    monkeypatch.setenv("NANOORGANIZER_DEMO_ROOT", str(tmp_path))
    for name in ("NANOORGANIZER_SECURE_MODE", "NANOORGANIZER_USER_MODE",
                 "NANOORGANIZER_ALLOWED_ROOTS", "NANOORGANIZER_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)             # no stray ./.config/pyViz.conf
    return tmp_path / "Lab"


@pytest.fixture
def built(lab_root):
    """The page after simulate → create → ingest → link → save."""
    app = AppTest.from_file(str(DEMO), default_timeout=120)
    app.run()
    _clean(app, "first run")
    for key in ORDER:
        _click(app, key)
    return app, lab_root


def test_every_tab_waits_for_its_prerequisite(lab_root):
    """Nothing built yet: each tab points back to the step it needs."""
    app = AppTest.from_file(str(DEMO), default_timeout=120)
    app.run()
    _clean(app, "empty")

    messages = " | ".join(item.value for item in app.info)
    assert "simulate the data first" in messages
    assert "Build the organizer first" in messages
    assert "Link the diffraction first" in messages
    assert "Run the batch first" in messages
    assert not lab_root.exists(), "rendering must not write anything"


def test_simulate_writes_the_lab_under_the_demo_root(lab_root):
    app = AppTest.from_file(str(DEMO), default_timeout=120)
    app.run()
    assert app.text_input(key="nano_demo_root").value == str(lab_root)

    _click(app, "nano_demo_simulate")
    assert (lab_root / "Meta" / "synthesis_dict.json").is_file()
    assert len(list((lab_root / "RawData" / "spectrometer").rglob("*.csv"))) == 84
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Micrographs"] == "18" and metrics["Patterns"] == "6"
    # The tree and the answer key are shown, not just written.
    assert any("microscope_share" in block.value for block in app.code)


def test_build_ingests_links_and_saves(built):
    app, lab_root = built
    store = lab_root / "lab.json"
    assert store.is_file()

    org = Organizer(store)
    catalog = org.catalog(counts=True)
    assert list(org.project.sample_ids()) == [f"S0{i}" for i in range(1, 7)]
    assert set(catalog.columns) >= {"uvvis", "tem", "waxs1d"}
    assert (catalog["tem"] == 3).all(), "session.txt must not be linked"
    assert (catalog["waxs1d"] == 1).all()

    # Paths are recorded exactly as linked, not rewritten.
    text = store.read_text()
    assert str(lab_root / "RawData" / "xrd_rig" / "S01_waxs.dat") in text
    assert json.loads(text), "lab.json is plain JSON"

    # Every later tab can now render its content instead of an info box.
    remaining = " | ".join(item.value for item in app.info)
    assert "Build the organizer first" not in remaining
    assert "Link the diffraction first" not in remaining


def test_fit_batch_compare_and_reload(built):
    app, lab_root = built

    # The kernel ran on the default window and reported a good fit.
    metrics = {m.label: m.value for m in app.metric}
    assert float(metrics["R²"]) > 0.99

    _click(app, "nano_demo_batch")
    assert any("12/12" in item.value for item in app.success)
    results = list((lab_root / "results").glob("*.result.npz"))
    assert len(results) == 12

    # Compare recovers the hidden numbers.
    metrics = {m.label: m.value for m in app.metric}
    assert float(metrics["Band recovered within"].split()[0]) < 3.0
    slope = next(v for k, v in metrics.items() if k.startswith("Scherrer"))
    assert abs(float(slope) - 0.565) < 0.05

    # F: a fresh Organizer off disk, no refitting.
    before = sorted(p.stat().st_mtime for p in results)
    _click(app, "nano_demo_reload")
    after = sorted(p.stat().st_mtime for p in results)
    assert before == after, "reloading must not rewrite the stored fits"


def test_a_saved_organizer_reopens_in_a_new_session(built):
    _, lab_root = built
    app = AppTest.from_file(str(DEMO), default_timeout=120)
    app.run()
    button = app.button(key="nano_demo_create")
    assert button.label == "Reopen lab.json"
    button.click().run()
    _clean(app, "reopen")
    org = app.session_state["nano_demo_org"]
    assert len(org.project.measurements(modality="tem")) == 6


def test_start_over_removes_only_the_organizer(built):
    app, lab_root = built
    _click(app, "nano_demo_batch")
    assert (lab_root / "results").is_dir()

    app.checkbox(key="nano_demo_sure").check().run()
    _click(app, "nano_demo_reset")
    assert not (lab_root / "lab.json").exists()
    assert not (lab_root / "results").exists()
    # The raw data and the dict are untouched.
    assert (lab_root / "Meta" / "synthesis_dict.json").is_file()
    assert len(list((lab_root / "RawData").rglob("*.tif"))) == 18
    assert "nano_demo_org" not in app.session_state


def test_handover_puts_the_organizer_in_the_workflow(built):
    app, _ = built
    _click(app, "nano_demo_handover")
    assert app.session_state["nano_workbench"] is app.session_state["nano_demo_org"]


def test_restricted_mode_refuses_a_root_outside_the_fence(lab_root, tmp_path,
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


def test_navigation_reaches_the_demo_page(lab_root):
    app = AppTest.from_file(str(HOME), default_timeout=300)
    app.run()
    assert not app.exception, _why(app)
    app.switch_page("views/demo.py").run()
    assert not app.exception, _why(app)
    assert [t.value for t in app.title] == ["🎓 Demo"]


def test_every_technique_and_both_engines_draw(built):
    app, _ = built
    for modality in ("uvvis", "tem", "waxs1d"):
        app.selectbox(key="nano_demo_vis_m").select(modality).run()
        _clean(app, f"static {modality}")
    app.radio(key="nano_demo_vis_engine").set_value("interactive").run()
    _clean(app, "interactive")


def test_a_wider_window_is_visibly_worse(built):
    """The lesson of part D: a window reaching the next reflection drops R²."""
    app, _ = built
    good = float(next(m.value for m in app.metric if m.label == "R²"))
    app.slider(key="nano_demo_fit_window").set_range(2.3, 4.5).run()
    _clean(app, "wide window")
    bad = float(next(m.value for m in app.metric if m.label == "R²"))
    assert bad < good - 0.1
