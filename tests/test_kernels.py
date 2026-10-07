"""Tests for the analysis and plotting kernels.

The point of the kernel/adapter split (``docs/kernel_adapter_rule.md``) is that
the science can be tested on arrays with a **known answer** and no IO at all.
So these tests build their data, call the kernel, and check the number it was
given back — no project, no files, no registry.

If one of these needs a fixture that touches the disk, the split has leaked.
"""

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt                                    # noqa: E402

from NanoOrganizer.analysis import CurveMetrics, PeakFitResult      # noqa: E402
from NanoOrganizer.analysis import fit_peaks, measure_curve         # noqa: E402
from NanoOrganizer.analysis.imaging import (                        # noqa: E402
    size_from_image, size_statistics,
)
from NanoOrganizer.viz.plots import (                               # noqa: E402
    plot_distribution, plot_fit, plot_marked_curve, plot_outlines, plot_series,
)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def gaussian(x, amplitude, centre, sigma):
    return amplitude * np.exp(-0.5 * ((x - centre) / sigma) ** 2)


# ---------------------------------------------------------------------------
# fit_peaks
# ---------------------------------------------------------------------------

def test_fit_peaks_recovers_what_was_put_in():
    x = np.linspace(400.0, 700.0, 601)
    y = gaussian(x, 2.0, 540.0, 18.0) + 0.3

    fit = fit_peaks(x, y, n_peaks=1)

    assert isinstance(fit, PeakFitResult)
    assert fit.params["peak1_center"] == pytest.approx(540.0, abs=0.1)
    assert fit.params["peak1_width"] == pytest.approx(18.0, abs=0.1)
    assert fit.params["peak1_amplitude"] == pytest.approx(2.0, abs=0.02)
    assert fit.params["baseline"] == pytest.approx(0.3, abs=0.02)
    assert fit.r2 > 0.999


def test_fit_peaks_takes_two_arrays_and_nothing_else():
    """The whole test of a kernel: made-up arrays, fresh interpreter."""
    x = np.linspace(0, 10, 300)
    y = gaussian(x, 5.0, 4.0, 0.6) + gaussian(x, 2.0, 7.0, 0.4) + 1.0

    fit = fit_peaks(x, y, n_peaks=2)
    assert [round(c, 2) for c in fit.centers] == [4.0, 7.0]


def test_fit_peaks_reports_uncertainties_not_zeros():
    rng = np.random.default_rng(0)
    x = np.linspace(0, 10, 400)
    y = gaussian(x, 5.0, 5.0, 0.8) + rng.normal(0, 0.02, x.size)

    fit = fit_peaks(x, y, n_peaks=1)
    assert fit.errors["peak1_center"] > 0
    assert set(fit.errors).issubset(set(fit.params))


def test_fit_peaks_returns_the_model_and_the_residual():
    """A caller that recomputes the model to draw it will get it wrong."""
    x = np.linspace(0, 10, 200)
    y = gaussian(x, 3.0, 5.0, 1.0)

    fit = fit_peaks(x, y, n_peaks=1)
    assert fit.y_fit.shape == fit.x.shape
    np.testing.assert_allclose(fit.residual, fit.y - fit.y_fit)
    assert abs(fit.residual).max() < 0.01


def test_fit_peaks_records_what_it_actually_used():
    x = np.linspace(0, 10, 200)
    y = gaussian(x, 3.0, 5.0, 1.0)

    fit = fit_peaks(x, y, n_peaks=1, shape="lorentzian", background="linear",
                    x_range=(3.0, 7.0))
    assert fit.settings["shape"] == "lorentzian"
    assert fit.settings["background"] == "linear"
    assert fit.settings["x_range"][0] >= 3.0
    assert fit.settings["n_points"] == fit.x.size


def test_a_sloping_background_is_fitted_when_asked_for():
    x = np.linspace(0, 10, 400)
    y = gaussian(x, 4.0, 5.0, 0.8) + 1.0 + 0.5 * x

    flat = fit_peaks(x, y, n_peaks=1, background="constant")
    sloped = fit_peaks(x, y, n_peaks=1, background="linear")

    assert sloped.r2 > flat.r2
    assert sloped.params["baseline_slope"] == pytest.approx(0.5, abs=0.02)
    # The documented failure mode: a flat background drags the centre.
    assert abs(sloped.params["peak1_center"] - 5.0) < \
        abs(flat.params["peak1_center"] - 5.0)


def test_fit_peaks_raises_rather_than_returning_a_sentinel():
    x = np.linspace(0, 10, 100)
    y = gaussian(x, 1.0, 5.0, 1.0)

    with pytest.raises(ValueError, match="shape must be"):
        fit_peaks(x, y, shape="triangle")
    with pytest.raises(ValueError, match="background must be"):
        fit_peaks(x, y, background="polynomial")
    with pytest.raises(ValueError, match="n_peaks"):
        fit_peaks(x, y, n_peaks=0)
    with pytest.raises(ValueError, match="must match"):
        fit_peaks(x, y[:-1])


def test_too_few_points_says_so_and_names_the_window():
    x = np.linspace(0, 10, 100)
    y = gaussian(x, 1.0, 5.0, 1.0)

    with pytest.raises(ValueError, match="x_range"):
        fit_peaks(x, y, x_range=(4.99, 5.01))


def test_the_kernel_takes_no_view_on_quality():
    """min_r2 is the adapter's policy; the kernel only reports R²."""
    rng = np.random.default_rng(1)
    x = np.linspace(0, 10, 200)
    y = rng.normal(0, 1, x.size)            # no peak at all

    fit = fit_peaks(x, y, n_peaks=1)
    assert fit.r2 < 0.5                     # bad, and returned anyway
    assert isinstance(fit, PeakFitResult)


# ---------------------------------------------------------------------------
# measure_curve
# ---------------------------------------------------------------------------

def test_measure_curve_finds_the_maximum_and_the_area():
    x = np.linspace(0.0, 10.0, 1001)
    y = gaussian(x, 4.0, 5.0, 0.5)

    metrics = measure_curve(x, y, subtract_baseline=False)

    assert isinstance(metrics, CurveMetrics)
    assert metrics.values["x_at_max"] == pytest.approx(5.0, abs=0.01)
    assert metrics.values["y_max"] == pytest.approx(4.0, abs=0.01)
    # A Gaussian's area is amplitude * sigma * sqrt(2 pi).
    assert metrics.values["area"] == pytest.approx(
        4.0 * 0.5 * np.sqrt(2 * np.pi), rel=0.01)
    assert metrics.values["x_centroid"] == pytest.approx(5.0, abs=0.01)


def test_measure_curve_finds_a_threshold_crossing():
    """The same operation as the potential at 10 mA/cm2."""
    x = np.linspace(0.0, 10.0, 1001)
    y = 2.0 * x                              # crosses 10 at x = 5

    metrics = measure_curve(x, y, threshold=10.0, subtract_baseline=False)
    assert metrics.values["x_at_threshold"] == pytest.approx(5.0, abs=0.02)
    assert metrics.settings["n_crossings"] == 1


def test_an_unreached_threshold_is_a_note_not_a_failure():
    x = np.linspace(0.0, 10.0, 101)
    y = np.full_like(x, 1.0)

    metrics = measure_curve(x, y, threshold=99.0, subtract_baseline=False)
    assert "x_at_threshold" not in metrics.values
    assert "never reaches" in metrics.note
    assert metrics.values["y_mean"] == pytest.approx(1.0)


def test_measure_curve_windows_before_measuring():
    x = np.linspace(0.0, 10.0, 1001)
    y = gaussian(x, 4.0, 2.0, 0.3) + gaussian(x, 9.0, 8.0, 0.3)

    whole = measure_curve(x, y, subtract_baseline=False)
    windowed = measure_curve(x, y, x_min=0.0, x_max=5.0,
                             subtract_baseline=False)

    assert whole.values["x_at_max"] == pytest.approx(8.0, abs=0.05)
    assert windowed.values["x_at_max"] == pytest.approx(2.0, abs=0.05)


def test_measure_curve_raises_on_an_empty_window():
    x = np.linspace(0.0, 10.0, 101)
    with pytest.raises(ValueError, match="nothing to summarise"):
        measure_curve(x, x, x_min=4.0, x_max=4.001)


# ---------------------------------------------------------------------------
# imaging kernels
# ---------------------------------------------------------------------------

def disc_image(diameter_px, n=9, size=256, seed=0):
    rng = np.random.default_rng(seed)
    field = np.full((size, size), 200.0)
    radius = diameter_px / 2
    step = size // (int(np.sqrt(n)) + 1)
    yy, xx = np.ogrid[:size, :size]
    for row in range(step, size - step + 1, step):
        for col in range(step, size - step + 1, step):
            field[(yy - row) ** 2 + (xx - col) ** 2 <= radius ** 2] = 40.0
    return field + rng.normal(0, 2, (size, size))


def test_size_from_image_measures_discs_in_nanometres():
    pytest.importorskip("skimage")
    image = disc_image(20)

    diameters, info = size_from_image(image, 0.5, min_diameter=2.0,
                                      max_diameter=100.0)
    assert diameters.size >= 4
    # 20 px at 0.5 nm/px is 10 nm.
    assert float(np.median(diameters)) == pytest.approx(10.0, rel=0.1)
    assert info["calibrated"] is True


def test_an_uncalibrated_image_comes_back_in_pixels():
    """Filtering in the wrong units would discard the wrong particles."""
    pytest.importorskip("skimage")
    image = disc_image(20)

    diameters, info = size_from_image(image, None)
    assert info["calibrated"] is False
    assert float(np.median(diameters)) == pytest.approx(20.0, rel=0.15)


def test_size_statistics_computes_the_pooled_numbers():
    values = np.array([8.0, 10.0, 12.0, 10.0])
    stats = size_statistics(values)

    assert stats["d_mean"] == pytest.approx(10.0)
    assert stats["d_median"] == pytest.approx(10.0)
    assert stats["n_particles"] == 4
    assert stats["d_std"] == pytest.approx(np.std(values, ddof=1))
    assert stats["d_cv"] == pytest.approx(stats["d_std"] / 10.0)


def test_no_particles_is_an_empty_result_not_a_row_of_nans():
    assert size_statistics([]) == {}
    assert size_statistics([np.nan, np.nan]) == {}


# ---------------------------------------------------------------------------
# plotting kernels
# ---------------------------------------------------------------------------

def test_plot_fit_draws_from_arrays_alone():
    x = np.linspace(0, 10, 100)
    y = gaussian(x, 2.0, 5.0, 1.0)
    fit = fit_peaks(x, y, n_peaks=1)

    axes = plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, xlabel="q (1/Å)")
    assert len(axes) == 2
    assert axes[1].get_xlabel() == "q (1/Å)"
    # data + model on the top panel, residual on the bottom.
    assert len(axes[0].get_lines()) == 2
    assert len(axes[1].get_lines()) >= 1


def test_plot_fit_without_a_residual_is_one_panel():
    x = np.linspace(0, 10, 50)
    axes = plot_fit(x, x, x * 1.01)
    assert not isinstance(axes, (list, np.ndarray))
    assert axes.get_xlabel() == "x"


def test_plot_fit_refuses_mismatched_arrays():
    x = np.linspace(0, 10, 50)
    with pytest.raises(ValueError, match="must match"):
        plot_fit(x, x, x[:-1])


def test_plot_distribution_marks_mean_and_median():
    axes = plot_distribution([1.0, 2.0, 3.0, 10.0], unit="nm")
    labels = [t.get_text() for t in axes.get_legend().get_texts()]
    assert any("mean" in label for label in labels)
    assert any("median" in label for label in labels)


def test_plot_distribution_refuses_nothing_to_plot():
    with pytest.raises(ValueError, match="no finite values"):
        plot_distribution([np.nan, np.inf])


def test_plot_series_strides_rather_than_truncating():
    x = np.linspace(0, 1, 50)
    matrix = np.vstack([x * k for k in range(100)])

    axes = plot_series(x, matrix, values=np.arange(100), max_curves=10)
    drawn = len(axes.get_lines())
    assert 9 <= drawn <= 11
    # The last curve must be represented, or the figure shows only the start.
    final = max(line.get_ydata().max() for line in axes.get_lines())
    assert final > matrix[50].max()


def test_plot_series_needs_one_value_per_curve():
    x = np.linspace(0, 1, 10)
    matrix = np.vstack([x, x * 2])
    with pytest.raises(ValueError, match="one value per curve"):
        plot_series(x, matrix, values=[1.0])


def test_plot_marked_curve_marks_a_position_and_a_width():
    x = np.linspace(400, 700, 300)
    y = gaussian(x, 1.0, 540.0, 20.0)

    axes = plot_marked_curve(x, y, mark=540.0, width=47.0, unit="nm",
                             label="spectrum")
    labels = [t.get_text() for t in axes.get_legend().get_texts()]
    assert any("540" in label for label in labels)
    assert any("FWHM" in label for label in labels)


def test_plot_outlines_draws_any_label_map():
    pytest.importorskip("skimage")
    image = np.zeros((32, 32))
    labels = np.zeros((32, 32), dtype=int)
    labels[8:16, 8:16] = 1

    axes = plot_outlines(image, labels, title="two squares")
    assert axes.get_title(loc="left") == "two squares"


def test_plot_outlines_refuses_a_mismatched_label_map():
    with pytest.raises(ValueError, match="must match"):
        plot_outlines(np.zeros((8, 8)), np.zeros((4, 4), dtype=int))
