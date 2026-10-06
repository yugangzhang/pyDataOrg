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


# ---------------------------------------------------------------------------
# Linking data from anywhere
# ---------------------------------------------------------------------------

def test_link_section_attaches_a_folder_outside_the_project(workbench, tmp_path):
    """The whole point: the data is not under the root and does not move."""
    elsewhere = tmp_path / "elsewhere" / "scope"
    elsewhere.mkdir(parents=True)
    for name in ("a.dat", "b.dat"):
        (elsewhere / name).write_text("1 2\n3 4\n")

    app = page("project.py", workbench)
    app.run()
    assert not app.exception, _why(app)

    app.selectbox(key="nano_link_sample").select("Sample000002").run()
    app.selectbox(key="nano_link_modality").select("waxs1d").run()
    app.text_input(key="nano_link_folder_path").set_value(str(elsewhere)).run()
    [b for b in app.button if b.label == "🔗 Link"][0].click().run()
    assert_clean(app, "link")

    measurement = workbench.measurement("Sample000002", modality="waxs1d")
    assert len(measurement.paths) == 2
    assert measurement.paths[0].startswith(str(elsewhere))
    # Recorded as given, with the mount named rather than the record rewritten.
    assert workbench.project.config.path_aliases


def test_link_section_refuses_an_empty_folder_without_crashing(workbench,
                                                               tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    app = page("project.py", workbench)
    app.run()
    app.text_input(key="nano_link_folder_path").set_value(str(empty)).run()
    [b for b in app.button if b.label == "🔗 Link"][0].click().run()
    assert not app.exception, _why(app)
    assert app.error


# ---------------------------------------------------------------------------
# Creating, revising and exporting an organizer from the GUI
# ---------------------------------------------------------------------------

def _editor_state(edited=None, added=None, deleted=None):
    """The payload Streamlit's data editor keeps in session state."""
    return {"edited_rows": edited or {}, "added_rows": added or [],
            "deleted_rows": deleted or []}


def test_an_organizer_saved_by_a_notebook_opens_in_the_gui(tmp_path):
    """The two halves are one object, so this has to hold or nothing does."""
    from NanoOrganizer import new_organizer

    source = tmp_path / "data"
    source.mkdir()
    (source / "scan.dat").write_text("1 2\n3 4\n")

    made = new_organizer(tmp_path / "FromNotebook", name="from a notebook")
    made.link("CuAu01", "waxs1d", str(source / "scan.dat"))
    made.set_params("CuAu01", au_fraction=0.55)
    made.save()

    app = AppTest.from_file(str(VIEWS / "project.py"), default_timeout=300)
    app.run()
    app.text_input(key="nano_project_root_path").set_value(
        str(tmp_path / "FromNotebook")).run()
    [b for b in app.button if b.label == "Open project"][0].click().run()
    assert not app.exception, _why(app)

    reopened = app.session_state["nano_workbench"]
    assert reopened.project.config.name == "from a notebook"
    assert reopened.project.sample_ids() == ["CuAu01"]
    assert reopened["CuAu01"].stage("synthesis").params["au_fraction"] == 0.55
    assert len(reopened.measurement("CuAu01", modality="waxs1d").resolve(
        reopened.resolver)) == 1


def test_create_makes_an_empty_organizer_to_link_into(tmp_path):
    app = AppTest.from_file(str(VIEWS / "project.py"), default_timeout=300)
    app.run()
    app.radio(key="nano_open_mode").set_value("Nothing yet").run()
    app.text_input(key="nano_project_root_path").set_value(
        str(tmp_path / "Fresh")).run()
    app.text_input(key="nano_new_name").set_value("fresh study").run()
    [b for b in app.button if b.label == "Create organizer"][0].click().run()
    assert not app.exception, _why(app)

    made = app.session_state["nano_workbench"]
    assert made.project.config.name == "fresh study"
    assert len(made.project) == 0


def test_create_refuses_to_overwrite_an_existing_organizer(tmp_path, workbench):
    workbench.save()
    app = AppTest.from_file(str(VIEWS / "project.py"), default_timeout=300)
    app.run()
    app.radio(key="nano_open_mode").set_value("Nothing yet").run()
    app.text_input(key="nano_project_root_path").set_value(
        str(workbench.project.root)).run()
    [b for b in app.button if b.label == "Create organizer"][0].click().run()
    assert not app.exception, _why(app)
    assert any("already holds" in e.value for e in app.error)


def test_parameter_grid_edits_adds_and_removes_samples(workbench):
    app = page("project.py", workbench)
    app.run()
    assert not app.exception, _why(app)
    app.selectbox(key="nano_param_stage").select("synthesis").run()

    app.session_state["nano_param_editor"] = _editor_state(
        edited={0: {"conditions.temperature_C": 11.0}},
        added=[{"sample_id": "Sample000003", "conditions.temperature_C": 3.0}],
    )
    [b for b in app.button if b.label == "Apply changes"][0].click().run()
    assert_clean(app, "parameter grid")

    project = workbench.project
    assert project.sample_ids() == ["Sample000001", "Sample000002",
                                    "Sample000003"]
    assert project.get_sample("Sample000001").stage(
        "synthesis").params["conditions"]["temperature_C"] == 11.0
    # A new sample has parameters and no data, which is a valid state: a
    # synthesis that failed is a result.
    assert project.get_sample("Sample000003").measurements == []
    assert "synthesis.conditions.temperature_C" in workbench.table().columns


def test_deleting_a_grid_row_forgets_the_sample_and_its_links(workbench):
    app = page("project.py", workbench)
    app.run()
    app.session_state["nano_param_editor"] = _editor_state(deleted=[1])
    [b for b in app.button if b.label == "Apply changes"][0].click().run()
    assert_clean(app, "delete row")
    assert workbench.project.sample_ids() == ["Sample000001"]


def test_a_new_parameter_column_can_be_added_and_filled(workbench):
    app = page("project.py", workbench)
    app.run()
    app.selectbox(key="nano_param_stage").select("synthesis").run()
    app.text_input(key="nano_param_newcol").set_value("au_fraction").run()
    app.session_state["nano_param_editor"] = _editor_state(
        edited={0: {"au_fraction": 0.55}})
    [b for b in app.button if b.label == "Apply changes"][0].click().run()
    assert_clean(app, "new column")
    assert workbench.project.get_sample("Sample000001").stage(
        "synthesis").params["au_fraction"] == 0.55


def test_the_page_offers_the_three_exports(workbench, tmp_path):
    """Downloads cannot be clicked in AppTest, so check they are offered."""
    elsewhere = tmp_path / "scope"
    elsewhere.mkdir()
    (elsewhere / "a.dat").write_text("1 2\n")
    workbench.link("Sample000001", "waxs1d", str(elsewhere / "a.dat"))

    app = page("project.py", workbench)
    app.run()
    assert not app.exception, _why(app)

    labels = [str(getattr(b, "label", "")) for b in app.get("download_button")]
    assert any("Links (CSV)" in label for label in labels)
    assert any("Sample table (CSV)" in label for label in labels)
    assert any("Store (JSON)" in label for label in labels)


def test_the_default_stage_is_the_one_carrying_parameters(workbench):
    """A project whose stages sort badly must not open on a blank grid."""
    app = page("project.py", workbench)
    app.run()
    assert app.selectbox(key="nano_param_stage").value == "synthesis"


def test_the_gui_alone_can_build_what_the_notebook_builds(tmp_path):
    """Notebook 06 in buttons: create, link, describe, save, reopen.

    The claim is that the GUI is not a viewer bolted onto a notebook API —
    someone who never opens Python can produce the same organizer. If this
    passes, that is true end to end.
    """
    data = tmp_path / "mount" / "beamline"
    data.mkdir(parents=True)
    for sample in ("CuAu01", "CuAu02"):
        folder = data / sample
        folder.mkdir()
        for name in ("scan_a.dat", "scan_b.dat"):
            (folder / name).write_text("1 2\n3 4\n")

    root = tmp_path / "Study"

    # 1. Create an empty organizer.
    app = AppTest.from_file(str(VIEWS / "project.py"), default_timeout=300)
    app.run()
    app.radio(key="nano_open_mode").set_value("Nothing yet").run()
    app.text_input(key="nano_project_root_path").set_value(str(root)).run()
    app.text_input(key="nano_new_name").set_value("gui study").run()
    [b for b in app.button if b.label == "Create organizer"][0].click().run()
    built = app.session_state["nano_workbench"]

    # 2. Link data that lives on another mount, one sample at a time.
    for sample in ("CuAu01", "CuAu02"):
        app = page("project.py", built)
        app.run()
        app.selectbox(key="nano_link_sample").select("➕ new sample…").run()
        app.text_input(key="nano_link_new_id").set_value(sample).run()
        app.selectbox(key="nano_link_modality").select("waxs1d").run()
        app.text_input(key="nano_link_folder_path").set_value(
            str(data / sample)).run()
        [b for b in app.button if b.label == "🔗 Link"][0].click().run()
        assert_clean(app, f"link {sample}")

    assert sorted(built.project.sample_ids()) == ["CuAu01", "CuAu02"]
    assert len(built.measurement("CuAu01", modality="waxs1d").paths) == 2

    # 3. Give the samples something to filter on.
    app = page("project.py", built)
    app.run()
    app.text_input(key="nano_param_newcol").set_value("au_fraction").run()
    app.session_state["nano_param_editor"] = _editor_state(
        edited={0: {"au_fraction": 0.0}, 1: {"au_fraction": 1.0}})
    [b for b in app.button if b.label == "Apply changes"][0].click().run()
    assert_clean(app, "parameters")
    assert built.filter("`synthesis.au_fraction` > 0.5") == ["CuAu02"]
    built.clear()

    # 4. Save, and reopen it from scratch.
    app = page("project.py", built)
    app.run()
    [b for b in app.button if b.label == "💾 Save project"][0].click().run()
    assert_clean(app, "save")

    app = AppTest.from_file(str(VIEWS / "project.py"), default_timeout=300)
    app.run()
    app.text_input(key="nano_project_root_path").set_value(str(root)).run()
    [b for b in app.button if b.label == "Open project"][0].click().run()
    reopened = app.session_state["nano_workbench"]

    assert reopened.project.config.name == "gui study"
    assert sorted(reopened.project.sample_ids()) == ["CuAu01", "CuAu02"]
    assert reopened["CuAu02"].stage("synthesis").params["au_fraction"] == 1.0
    assert reopened.project.availability()["n_unresolved"] == 0
    # The data never moved into the project.
    assert not (root / "WAXSData").exists()
