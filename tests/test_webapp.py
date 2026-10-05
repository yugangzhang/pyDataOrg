"""Tests for the web app views.

These drive the real Streamlit pages through ``AppTest`` against a synthetic
project, so they do not depend on any data mount. A page that renders is not
the same as a page that works, so the interactions that matter — filtering,
selecting, running an analysis — are clicked through rather than just drawn.
"""

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

from pathlib import Path  # noqa: E402

from NanoOrganizer.core.schema import Measurement  # noqa: E402
from NanoOrganizer.workbench import open_project  # noqa: E402

VIEWS = Path(__file__).resolve().parents[1] / "NanoOrganizer" / "web_app" / "views"
HOME = VIEWS.parent / "Home.py"
WAVELENGTH = np.linspace(300.0, 900.0, 301)


PEAK_CENTRES = (520.0, 560.0)


@pytest.fixture
def workbench(tmp_path):
    """A two-sample project: a spectral series each, plus one TEM folder."""
    root = tmp_path / "P"
    (root / "MetaData").mkdir(parents=True)

    run = tmp_path / "mount" / "run"
    run.mkdir(parents=True)
    np.save(run / "axis_wavelength.npy", WAVELENGTH)

    for index, centre in enumerate(PEAK_CENTRES, start=1):
        band = np.exp(-0.5 * ((WAVELENGTH - centre) / 30.0) ** 2) + 0.1
        for t in range(0, 600, 60):
            np.save(run / f"run_b{index:02d}_t{t:05d}s.npy", band)

    tem = root / "TEMData" / "Sample000001"
    tem.mkdir(parents=True)
    from PIL import Image
    image = np.full((256, 256), 200.0)
    for row in range(40, 220, 40):
        for column in range(40, 220, 40):
            yy, xx = np.ogrid[:256, :256]
            image[(yy - row) ** 2 + (xx - column) ** 2 <= 100] = 60
    Image.fromarray(image.astype(np.uint8)).save(tem / "a.tif")

    project_wb = open_project(root, ingest=False, attach=True)
    project = project_wb.project

    for index, (sample_id, ratio) in enumerate(
            (("Sample000001", 6.0), ("Sample000002", 2.0)), start=1):
        sample = project.add_sample(sample_id)
        from NanoOrganizer.core.schema import Stage
        sample.add_stage(Stage(
            stage_id="synthesis", run_id="run", batch_tag="b1", status="done",
            params={"conditions": {"temperature_C": ratio}},
        ))
        sample.add_stage(Stage(stage_id="catalysis", run_id="run",
                               batch_tag="auto", status="done", params={}))
        sample.add_measurement(Measurement(
            sample_id=sample_id, modality="uvvis", stage="catalysis",
            pattern=f"{run}/run_b{index:02d}_*.npy",
            aux={"wavelength_file": str(run / "axis_wavelength.npy")}))

    return project_wb


def page(name, workbench, **state):
    app = AppTest.from_file(str(VIEWS / name), default_timeout=300)
    app.session_state["nano_workbench"] = workbench
    for key, value in state.items():
        app.session_state[key] = value
    return app


def _why(app):
    """The first exception's message, for a readable assertion failure.

    ``app.exception`` is an ElementList, which is empty rather than None when
    the page ran cleanly — so it must be tested for truthiness, never against
    None.
    """
    return app.exception[0].value if app.exception else "no exception"


def assert_clean(app, label=""):
    assert not app.exception, f"{label}: {_why(app)}"
    assert not app.error, f"{label}: {[e.value for e in app.error]}"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["overview.py", "project.py", "explore.py",
                                  "visualize.py", "analyze.py", "compare.py"])
def test_view_renders(name, workbench):
    app = page(name, workbench)
    app.run()
    assert not app.exception, f"{name}: {_why(app)}"


@pytest.mark.parametrize("name", ["explore.py", "visualize.py", "analyze.py",
                                  "compare.py"])
def test_view_without_a_project_stops_politely(name):
    """A page with no project must say where to go, not throw."""
    app = AppTest.from_file(str(VIEWS / name), default_timeout=120)
    app.run()
    assert not app.exception, _why(app)
    assert any("Project" in item.value for item in app.info)


def test_navigation_entry_point_runs():
    app = AppTest.from_file(str(HOME), default_timeout=300)
    app.run()
    assert not app.exception, _why(app)
    assert [t.value for t in app.title] == ["🔬 NanoOrganizer"]


# ---------------------------------------------------------------------------
# Explore
# ---------------------------------------------------------------------------

RATIO = "synthesis.conditions.temperature_C"


def test_numeric_filter_narrows_and_selects(workbench):
    app = page("explore.py", workbench, nano_filters=[])
    app.run()
    app.selectbox(key="nano_num_col").select(RATIO).run()
    app.slider(key="nano_num_range").set_range(5.0, 6.0).run()
    [b for b in app.button if b.key == "nano_add_num"][0].click().run()
    assert_clean(app, "filter")

    matched = [m for m in app.metric if "Matching" in m.label][0]
    assert matched.value == "1 of 2"

    [b for b in app.button if b.label == "Select these"][0].click().run()
    assert workbench.basket == ["Sample000001"]


def test_expression_filter_applies(workbench):
    app = page("explore.py", workbench, nano_filters=[])
    app.run()
    app.radio(key="nano_filter_kind").set_value("Expression").run()
    app.text_input(key="nano_expr").set_value(f"`{RATIO}` < 3").run()
    [b for b in app.button if b.key == "nano_add_expr"][0].click().run()
    assert_clean(app, "expression")
    assert [m for m in app.metric if "Matching" in m.label][0].value == "1 of 2"


def test_a_bad_expression_is_reported_not_raised(workbench):
    app = page("explore.py", workbench, nano_filters=[])
    app.run()
    app.radio(key="nano_filter_kind").set_value("Expression").run()
    app.text_input(key="nano_expr").set_value("this is not pandas").run()
    [b for b in app.button if b.key == "nano_add_expr"][0].click().run()
    assert not app.exception, _why(app)
    assert app.error                      # shown to the user
    assert app.session_state["nano_filters"] == []   # and not accepted


def test_use_all_samples_clears_the_basket(workbench):
    workbench.select(["Sample000001"])
    app = page("explore.py", workbench, nano_filters=[])
    app.run()
    [b for b in app.button if b.label == "Use all samples"][0].click().run()
    assert workbench.basket == []


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------

def test_analysis_options_are_built_from_the_signature(workbench):
    """A new analysis gets a working form with no page change."""
    app = page("analyze.py", workbench)
    app.run()
    app.selectbox(key="nano_analysis_key").select("peak_fit").run()
    assert_clean(app, "options")
    keys = {w.key for w in app.number_input} | {w.key for w in app.toggle}
    assert "nano_opt_peak_fit_n_peaks" in keys
    assert "nano_opt_peak_fit_min_r2" in keys


def test_single_run_reports_the_fitted_peak(workbench):
    app = page("analyze.py", workbench)
    app.run()
    app.selectbox(key="nano_analysis_key").select("peak_fit").run()
    [b for b in app.button if b.label == "Run"][0].click().run()
    assert_clean(app, "single run")

    result = app.session_state["nano_last_result"]
    assert result.ok, result.message
    assert result.values["peak1_center"] == pytest.approx(PEAK_CENTRES[0], abs=1.0)
    assert app.metric


def test_single_run_does_not_write_by_default(workbench):
    app = page("analyze.py", workbench)
    app.run()
    app.selectbox(key="nano_analysis_key").select("peak_fit").run()
    [b for b in app.button if b.label == "Run"][0].click().run()
    assert workbench.project.get_sample("Sample000001").derived == {}


def test_batch_writes_derived_values(workbench):
    app = page("analyze.py", workbench)
    app.run()
    app.selectbox(key="nano_analysis_key").select("peak_fit").run()
    [b for b in app.button if b.label == "Run batch"][0].click().run()
    assert_clean(app, "batch")

    frame = app.session_state["nano_batch_peak_fit"]
    assert len(frame) == 2 and int(frame["ok"].sum()) == 2
    assert workbench.project.get_sample("Sample000001").get_derived(
        "uvvis_peak1_center") == pytest.approx(PEAK_CENTRES[0], abs=1.0)


def test_batch_surfaces_failures(workbench):
    """An unreadable measurement must appear in the table, not vanish."""
    workbench.project.get_sample("Sample000002").add_measurement(Measurement(
        sample_id="Sample000002", modality="uvvis", stage="catalysis",
        role="broken", pattern="/nowhere/*.npy"))

    app = page("analyze.py", workbench)
    app.run()
    app.selectbox(key="nano_analysis_key").select("peak_fit").run()
    [b for b in app.button if b.label == "Run batch"][0].click().run()

    assert not app.exception, _why(app)
    frame = app.session_state["nano_batch_peak_fit"]
    assert len(frame) == 3 and int(frame["ok"].sum()) == 2
    assert app.warning


# ---------------------------------------------------------------------------
# Visualize
# ---------------------------------------------------------------------------

def test_visualize_groups_follow_the_registry(workbench):
    """Tabs come from the data present, not a hard-coded list."""
    app = page("visualize.py", workbench)
    app.run()
    assert_clean(app, "visualize")
    keys = {s.key for s in app.selectbox}
    assert "nano_curve_modality" in keys     # uvvis -> curve group
    assert "nano_image_modality" in keys     # tem   -> image group


def test_curve_detail_mode_draws(workbench):
    app = page("visualize.py", workbench)
    app.run()
    app.radio(key="nano_curve_mode").set_value("One sample in detail").run()
    assert_clean(app, "curve detail")


def test_segmentation_runs_from_the_image_tab(workbench):
    app = page("visualize.py", workbench)
    app.run()
    buttons = [b for b in app.button if b.key == "nano_seg_run"]
    assert buttons, "segmentation control missing for a microscopy modality"
    buttons[0].click().run()
    assert_clean(app, "segmentation")


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

def test_compare_asks_for_an_analysis_first(workbench):
    app = page("compare.py", workbench)
    app.run()
    assert not app.exception, _why(app)
    assert any("Analyze" in item.value for item in app.info)


def test_compare_plots_once_derived_values_exist(workbench):
    from NanoOrganizer import analysis

    analysis.batch(workbench.project, "peak_fit")
    app = page("compare.py", workbench)
    app.run()
    assert_clean(app, "compare")
    assert {s.key for s in app.selectbox} >= {"nano_cmp_x", "nano_cmp_y"}


def test_compare_says_so_when_every_group_has_one_sample(workbench):
    """One sample per group makes the two effects arithmetically inseparable."""
    from NanoOrganizer import analysis

    analysis.batch(workbench.project, "peak_fit")
    for sample_id, tag in (("Sample000001", "batch_a"), ("Sample000002", "batch_b")):
        workbench.project.get_sample(sample_id).stage("synthesis").batch_tag = tag

    app = page("compare.py", workbench)
    app.run()
    assert not app.exception, _why(app)
    assert any("cannot be told apart" in item.value for item in app.info)
    assert not any("confounded" in w.value for w in app.warning)


def test_compare_warns_when_groups_separate_more_than_the_x_axis(tmp_path):
    """Between-group spread beating within-group spread is the confound signal."""
    from NanoOrganizer.core.schema import Sample, Stage

    workbench = open_project(tmp_path / "C", ingest=False, attach=False)
    project = workbench.project

    # Two batches of two. The measured value tracks the batch, not x.
    for sample_id, ratio, tag, k in (
        ("S1", 2.0, "batch_a", 520.0), ("S2", 8.0, "batch_a", 521.0),
        ("S3", 2.0, "batch_b", 560.0), ("S4", 8.0, "batch_b", 561.0),
    ):
        sample = project.add_sample(Sample(sample_id=sample_id))
        sample.add_stage(Stage(
            stage_id="synthesis", batch_tag=tag, status="done",
            params={"conditions": {"temperature_C": ratio}}))
        sample.set_derived("peak1_center", k, unit="nm", analysis="peak_fit")

    app = page("compare.py", workbench)
    app.run()
    assert not app.exception, _why(app)
    assert any("confounded" in w.value for w in app.warning)
