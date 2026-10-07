"""The two plotting rules, enforced (``docs/kernel_adapter_rule.md`` P1, P2).

P1 — every plot takes ``ax=None``, draws only there when given one, and
returns what it drew on (``fig=`` for the Plotly figures).

P2 — nothing both analyses and draws: analyses return results, plots take
them. The reductions that used to hide inside plots are kernels now, tested
here on arrays with a known answer.
"""

import ast
import inspect
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt                                    # noqa: E402

from NanoOrganizer import Organizer                                 # noqa: E402
from NanoOrganizer.analysis import (                                # noqa: E402
    Segmentation, azimuthal_average, fit_peaks, radius_to_q,
    radius_to_two_theta, segment_micrograph, weighted_mean,
)
from NanoOrganizer.analysis.result import AnalysisResult            # noqa: E402
from NanoOrganizer.viz import plots, show                           # noqa: E402

PACKAGE = Path(__file__).resolve().parents[1] / "NanoOrganizer"


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _peak(x, centre=2.0, sigma=0.1):
    return 10 * np.exp(-0.5 * ((x - centre) / sigma) ** 2) + 1.0


def _discs(n=4, size=128, radius=8):
    """A bright field with *n* dark discs on a diagonal."""
    image = np.full((size, size), 200.0)
    yy, xx = np.ogrid[:size, :size]
    for k in range(n):
        c = (k + 1) * size / (n + 1)
        image[(yy - c) ** 2 + (xx - c) ** 2 <= radius ** 2] = 40.0
    return image


# ---------------------------------------------------------------------------
# P1 — every matplotlib kernel draws on the Axes it was given and returns it
# ---------------------------------------------------------------------------

X = np.linspace(0, 4, 200)
CASES = {
    "plot_curves": lambda ax: plots.plot_curves([("a", X, _peak(X))], ax=ax),
    "plot_series": lambda ax: plots.plot_series(
        X, np.vstack([_peak(X), 2 * _peak(X)]), [0, 60], ax=ax),
    "plot_marked_curve": lambda ax: plots.plot_marked_curve(
        X, _peak(X), ax=ax, mark=2.0, width=0.2),
    "plot_distribution": lambda ax: plots.plot_distribution(
        np.random.default_rng(0).normal(10, 1, 200), ax=ax),
    "plot_outlines": lambda ax: plots.plot_outlines(
        _discs(), (_discs() < 100).astype(int), ax=ax),
    "plot_image": lambda ax: plots.plot_image(_discs(), ax=ax),
    "plot_fit without residual": lambda ax: plots.plot_fit(
        X, _peak(X), _peak(X), ax=ax),
}


@pytest.mark.parametrize("name", CASES)
def test_a_plot_draws_on_the_axes_it_is_given_and_returns_it(name):
    fig, ax = plt.subplots()
    before = plt.get_fignums()

    returned = CASES[name](ax)

    assert returned is ax
    assert plt.get_fignums() == before, "made a figure it was not asked for"
    assert ax.has_data() or ax.images


@pytest.mark.parametrize("name", CASES)
def test_a_plot_makes_its_own_figure_when_given_none(name):
    returned = CASES[name](None)
    assert isinstance(returned, matplotlib.axes.Axes)


def test_every_public_plot_function_takes_ax():
    """New plots cannot quietly skip the rule."""
    for name in plots.__all__:
        func = getattr(plots, name)
        if not callable(func) or not name.startswith("plot_"):
            continue
        assert "ax" in inspect.signature(func).parameters, name

    for name in ("curve_figure", "image_figure", "volume_figure",
                 "result_figure", "overlay"):
        assert "ax" in inspect.signature(getattr(show, name)).parameters, name


def test_plot_fit_splits_a_residual_strip_off_one_axes():
    fig, ax = plt.subplots()
    top, bottom = plots.plot_fit(X, _peak(X), _peak(X), np.zeros_like(X),
                                 ax=ax)
    assert top is ax
    assert bottom.figure is fig and bottom is not ax
    assert len(fig.axes) == 2


def test_plot_fit_draws_on_a_given_pair():
    fig, pair = plt.subplots(2, 1)
    top, bottom = plots.plot_fit(X, _peak(X), _peak(X), np.zeros_like(X),
                                 ax=pair)
    assert (top, bottom) == tuple(pair)
    assert len(fig.axes) == 2


def test_plot_fit_in_a_grid_keeps_every_residual():
    fig, axes = plt.subplots(1, 3)
    for ax in axes:
        plots.plot_fit(X, _peak(X), _peak(X), np.zeros_like(X), ax=ax)
    assert len(fig.axes) == 6


def test_plot_kinetics_takes_a_pair_and_refuses_one_axes():
    result = AnalysisResult(analysis="uvvis_kinetics", sample_id="S1")
    t = np.linspace(0, 600, 20)
    result.curves.update(t_s=t, a_band=np.exp(-t / 300), a_product=1 - np.exp(-t / 300),
                         ln_ratio=-t / 300, fit_t_s=t, fit_ln_ratio=-t / 300)
    fig, pair = plt.subplots(1, 2)
    assert plots.plot_kinetics(result, ax=pair) == tuple(pair)
    with pytest.raises(ValueError, match="two panels"):
        plots.plot_kinetics(result, ax=pair[0])


def test_no_plotting_module_shows_or_saves():
    """Showing and saving belong to the caller."""
    banned = {"show", "savefig", "close"}
    for path in [PACKAGE / "viz" / "plots.py", PACKAGE / "viz" / "show.py",
                 PACKAGE / "viz" / "interactive.py"]:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in banned
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "plt"):
                pytest.fail(f"{path.name}:{node.lineno} calls plt.{node.func.attr}")


# ---------------------------------------------------------------------------
# P1, interactive — fig= instead of ax=
# ---------------------------------------------------------------------------

def test_interactive_figures_draw_into_a_subplot_grid():
    pytest.importorskip("plotly")
    from plotly.subplots import make_subplots

    from NanoOrganizer.viz import interactive as iv

    grid = make_subplots(rows=1, cols=3,
                         specs=[[{}, {}, {"type": "scene"}]])
    grid.update_layout(title_text="mine")

    assert iv.curves_figure([("a", X, _peak(X))], fig=grid, row=1, col=1,
                            logy=True) is grid
    assert iv.image_figure(_discs(), fig=grid, row=1, col=2) is grid
    assert iv.volume_figure(np.random.default_rng(0).random((8, 8, 8)),
                            mode="points", level=0.5, fig=grid, row=1,
                            col=3) is grid

    assert len(grid.data) == 3
    assert grid.layout.title.text == "mine", "overwrote the caller's title"
    assert grid.layout.yaxis.type == "log"            # only cell (1, 1) …
    assert grid.layout.yaxis2.type != "log"           # … not its neighbour
    assert grid.layout.yaxis2.scaleanchor == "x2"     # square pixels, own cell


def test_interactive_figures_still_make_their_own():
    pytest.importorskip("plotly")
    from NanoOrganizer.viz import interactive as iv

    fig = iv.volume_figure(np.random.default_rng(0).random((8, 8, 8)),
                           mode="slices")
    assert len(fig.data) == 3
    assert fig.layout.scene.aspectmode == "data"


# ---------------------------------------------------------------------------
# P2 — analysis and drawing are separate calls
# ---------------------------------------------------------------------------

def test_plots_module_imports_no_analysis():
    """A drawing module that imports analysis is one call away from running it."""
    tree = ast.parse((PACKAGE / "viz" / "plots.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            names = [a.name for a in node.names]
            assert not module.startswith("NanoOrganizer.analysis"), module
            assert not any(n.startswith("NanoOrganizer.analysis") for n in names)


@pytest.fixture()
def micrograph_org(tmp_path):
    from PIL import Image

    folder = tmp_path / "scope" / "S1"
    folder.mkdir(parents=True)
    Image.fromarray(_discs().astype(np.uint8)).save(folder / "a.tif")
    org = Organizer(tmp_path / "o.json")
    org.link("S1", "tem", str(folder), nm_per_pixel=0.5)
    return org


def test_segmentation_is_an_analysis_that_returns_a_result(micrograph_org):
    org = micrograph_org
    seg = segment_micrograph(org.measurement("S1", modality="tem"),
                             org.resolver, min_diameter_nm=1.0)
    assert isinstance(seg, Segmentation)
    assert seg.n_particles == 4
    assert seg.labels.shape == seg.image.shape
    assert seg.file == "a.tif"


def test_plot_segmentation_draws_without_segmenting(micrograph_org, monkeypatch):
    from NanoOrganizer.analysis import imaging

    seg = micrograph_org.segment("S1", "tem", min_diameter_nm=1.0)

    def refuse(*args, **kwargs):
        raise AssertionError("the plot segmented")

    monkeypatch.setattr(imaging, "segment_particles", refuse)
    fig, ax = plt.subplots()
    assert micrograph_org.plot_segmentation(seg, ax=ax) is ax
    assert "4 particles" in ax.get_title(loc="left")


@pytest.mark.parametrize("method", ["plot_sizes", "plot_kinetics",
                                    "plot_spectra", "plot_endpoint",
                                    "plot_segmentation"])
def test_a_plot_handed_a_sample_id_refuses_to_run_the_analysis(
        micrograph_org, method):
    with pytest.raises(TypeError, match="runs nothing"):
        getattr(micrograph_org, method)("S1")


def test_result_figure_keeps_the_fit_layout_on_a_given_axes():
    fit = fit_peaks(X, _peak(X), n_peaks=1)
    result = AnalysisResult(analysis="peak_fit", sample_id="S1")
    result.curves.update(x=fit.x, y=fit.y, y_fit=fit.y_fit,
                         residual=fit.residual)
    fig, ax = plt.subplots()
    drawn = show.result_figure(result, ax=ax)
    assert drawn[0] is ax and len(fig.axes) == 2


# ---------------------------------------------------------------------------
# The reductions that used to live inside plots — kernels with known answers
# ---------------------------------------------------------------------------

def test_azimuthal_average_recovers_a_radial_function():
    yy, xx = np.indices((101, 101))
    r = np.hypot(xx - 50.5, yy - 50.5)
    image = 3.0 * r + 1.0
    radius, profile = azimuthal_average(image, n_bins=25)
    # Away from the centre, where an annulus' mean radius is its bin centre
    # to within a percent, and inside the inscribed circle.
    ring = (radius > 8) & (radius < 45)
    assert np.allclose(profile[ring], 3.0 * radius[ring] + 1.0, rtol=0.02)

    flat, = azimuthal_average(np.full((40, 40), 7.0))[1:]
    assert np.allclose(flat[flat > 0], 7.0)


def test_azimuthal_average_refuses_a_curve():
    with pytest.raises(ValueError, match="2D"):
        azimuthal_average(np.arange(10.0))


def test_radius_conversions_follow_their_formulas():
    q = radius_to_q([100.0], pixel_size_mm=0.172, sdd_mm=5000.0,
                    wavelength_A=1.0)
    assert q[0] == pytest.approx(2 * np.pi * 100 * 0.172 / 5000.0)
    tth = radius_to_two_theta([100.0], pixel_size_mm=1.0, sdd_mm=100.0)
    assert tth[0] == pytest.approx(45.0)


def test_weighted_mean_is_one_mean_per_row_and_nan_for_no_weight():
    x = np.array([1.0, 2.0, 3.0])
    means = weighted_mean(x, [[1, 1, 1], [0, 0, 1], [0, 0, 0]])
    assert means[:2] == pytest.approx([2.0, 3.0])
    assert np.isnan(means[2])


def test_image_display_clips_to_a_percentile_and_logs_without_inf():
    array = np.arange(100.0).reshape(10, 10)
    array[0, 0] = 0.0
    display, low, high = show.image_display(array, percentile=90.0)
    assert (low, high) == pytest.approx((np.percentile(array, 10),
                                         np.percentile(array, 90)))
    logged, low, _ = show.image_display(array, log_intensity=True)
    assert np.isfinite(logged).all()


def test_project_volume_says_what_it_did():
    volume = np.zeros((10, 4, 4))
    volume[7, 1, 2] = 5.0
    plane, detail = show.project_volume(volume, projection="max projection")
    assert plane[1, 2] == 5.0 and "all 10 planes" in detail
    plane, detail = show.project_volume(volume, projection="single slice",
                                        centre=3)
    assert plane.max() == 0.0 and detail == "plane 3 of 10"


def test_legacy_plot_types_that_computed_warn_but_still_draw():
    from NanoOrganizer.viz import DLSPlotter, SAXS2DPlotter

    images = np.stack([_discs(size=64)] * 2)
    data = {"times": np.array([0.0, 10.0]), "images": images}
    with pytest.warns(DeprecationWarning, match="computes while it draws"):
        ax = SAXS2DPlotter().plot(data, plot_type="azimuthal")
    assert ax.has_data()

    d = np.linspace(1, 100, 50)
    dls = {"times": np.array([0.0, 10.0]), "diameters": d,
           "intensity": np.vstack([np.ones(50), np.ones(50)])}
    with pytest.warns(DeprecationWarning):
        DLSPlotter().plot(dls, plot_type="kinetics")
