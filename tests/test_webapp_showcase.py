"""The web app, driven against the multimodal demo project.

``test_webapp.py`` checks the interactions on a two-technique project. This
file checks the thing that project cannot: that the pages still work when the
selection holds fifteen techniques, four visualisation groups, three stages
and a sample with no data at all.

That is the case the generalisation was for, so it is the case worth testing.
"""

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

from pathlib import Path  # noqa: E402

from NanoOrganizer.demo import build_showcase_project  # noqa: E402
from NanoOrganizer.workbench import open_project  # noqa: E402

VIEWS = Path(__file__).resolve().parents[1] / "NanoOrganizer" / "web_app" / "views"


@pytest.fixture(scope="module")
def showcase_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("gui") / "CuAuDemo"
    build_showcase_project(root, fractions=(0.0, 0.5, 1.0), n_frames=4,
                           n_micrographs=1, image_size=256, tomo_size=40)
    return root


@pytest.fixture()
def workbench(showcase_root):
    return open_project(showcase_root)


def page(name, workbench, **state):
    app = AppTest.from_file(str(VIEWS / name), default_timeout=300)
    app.session_state["nano_workbench"] = workbench
    for key, value in state.items():
        app.session_state[key] = value
    return app


def _why(app):
    return app.exception[0].value if app.exception else "no exception"


@pytest.mark.parametrize("name", ["overview.py", "project.py", "explore.py",
                                  "visualize.py", "analyze.py", "compare.py"])
def test_every_view_survives_a_fifteen_technique_project(name, workbench):
    app = page(name, workbench)
    app.run()
    assert not app.exception, f"{name}: {_why(app)}"


def test_visualize_offers_every_group_present(workbench):
    """The tabs are the groups in the data, so all four should be there."""
    app = page("visualize.py", workbench)
    app.run()
    assert not app.exception, _why(app)

    labels = {tab.label for tab in app.tabs}
    assert {"Curves (1D)", "Images & Maps (2D)", "Volumes (3D)",
            "Correlation"} <= labels


def test_a_sample_with_no_data_does_not_break_visualize(workbench):
    """The failed synthesis has a row and no measurements at all."""
    failed = "CuAu04"
    assert workbench.project.get_sample(failed).measurements == []

    workbench.select([failed])
    app = page("visualize.py", workbench)
    app.run()
    assert not app.exception, _why(app)


def test_analyze_lists_the_generic_analyses(workbench):
    app = page("analyze.py", workbench)
    app.run()
    assert not app.exception, _why(app)

    # AppTest reports a selectbox's options already run through format_func,
    # so these are the labels; select() still takes the raw key.
    options = set(app.selectbox(key="nano_analysis_key").options)
    assert {"1D peak fitting", "Curve metrics in a window",
            "Particle sizing from micrographs"} <= options
    assert {"peak_fit", "curve_metrics",
            "particle_sizing"} <= set(workbench.analyses())


def test_compare_can_plot_an_authored_performance_number(workbench):
    """The electrochemistry summary is in the metadata, so Compare has
    something to show before any analysis has been run."""
    app = page("compare.py", workbench)
    app.run()
    assert not app.exception, _why(app)

    columns = workbench.table().columns
    assert "testing.performance.FE_CO_pct" in columns
    assert "synthesis.composition.nominal_x_Au" in columns


def test_project_page_offers_to_generate_one_when_empty():
    """The first thing a new user sees must not be a dead end."""
    app = AppTest.from_file(str(VIEWS / "project.py"), default_timeout=300)
    app.run()
    assert not app.exception, _why(app)

    labels = [b.label for b in app.button]
    assert "Generate and open" in labels
    assert any("example" in str(i.value).lower() for i in app.info)


# ---------------------------------------------------------------------------
# Plot controls and the interactive engine
# ---------------------------------------------------------------------------

INTERACTIVE_KEYS = ("nano_curve_cmp", "nano_curve_one_style",
                    "nano_image_style", "nano_vol", "nano_corr_curve")


def test_volumes_are_interactive_by_default(workbench):
    """A projection answers 'what is in there'; only rotation answers
    'what shape is it'."""
    app = page("visualize.py", workbench)
    app.run()
    assert not app.exception, _why(app)
    assert len(app.get("plotly_chart")) >= 1


def test_every_group_can_be_drawn_interactively(workbench):
    from NanoOrganizer.web_app.components.plot_controls import INTERACTIVE

    state = {f"{key}_engine": INTERACTIVE for key in INTERACTIVE_KEYS}
    app = page("visualize.py", workbench, **state)
    app.run()
    assert not app.exception, _why(app)
    # curves, image, volume and correlation tabs all render at once.
    assert len(app.get("plotly_chart")) >= 4


@pytest.mark.parametrize("mode", ["isosurface", "volume", "points", "slices"])
def test_each_volume_render_mode_works_through_the_page(workbench, mode):
    app = page("visualize.py", workbench, nano_vol_mode=mode)
    app.run()
    assert not app.exception, f"{mode}: {_why(app)}"


def test_static_engine_draws_no_plotly_at_all(workbench):
    """The engine switch has to actually switch. (`st.pyplot` surfaces as an
    UnknownElement in AppTest, so the absence of Plotly is what to assert.)"""
    from NanoOrganizer.web_app.components.plot_controls import STATIC

    state = {f"{key}_engine": STATIC for key in INTERACTIVE_KEYS}
    app = page("visualize.py", workbench, **state)
    app.run()
    assert not app.exception, _why(app)
    assert len(app.get("plotly_chart")) == 0


def test_axis_limits_and_log_scales_are_offered(workbench):
    app = page("visualize.py", workbench, nano_curve_cmp_logy=True)
    app.run()
    assert not app.exception, _why(app)
    assert app.session_state["nano_curve_cmp_logy"] is True


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_structure_page_opens_empty(workbench):
    app = page("structure.py", workbench)
    app.run()
    assert not app.exception, _why(app)
    assert any("Choose a folder" in str(i.value) for i in app.info)


def test_structure_lists_the_project_root(workbench, showcase_root):
    app = page("structure.py", workbench,
               nano_structure_address=str(showcase_root))
    app.run()
    assert not app.exception, _why(app)

    labels = [b.label for b in app.button]
    assert any("MetaData" in label for label in labels)
    assert any("Electrochemistry" in label for label in labels)


def test_structure_drills_into_a_metadata_module(workbench, showcase_root):
    module = showcase_root / "MetaData" / "Characterization_dict.py"
    app = page("structure.py", workbench, nano_structure_address=str(module))
    app.run()
    assert not app.exception, _why(app)

    # Reading a .py metadata module executes it; the page must say so.
    assert any("runs the code" in str(w.value) for w in app.warning)
    assert any("Characterization_dict" in b.label for b in app.button)


def test_structure_reports_a_bad_path_without_crashing(workbench):
    app = page("structure.py", workbench,
               nano_structure_address="/no/such/place/at/all")
    app.run()
    assert not app.exception, _why(app)
    assert any("does not exist" in str(e.value) for e in app.error)
