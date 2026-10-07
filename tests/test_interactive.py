"""Tests for the interactive (Plotly) figures.

These check the things that are easy to get wrong and invisible until someone
looks at a figure: that a colorscale name is real, that it runs the same
direction as the matplotlib colormap it stands for, that a log axis range is
in log units, and that a large volume is strided down before it reaches a
browser.
"""

import numpy as np
import pytest

plotly = pytest.importorskip("plotly")
go = pytest.importorskip("plotly.graph_objects")

from NanoOrganizer.viz import interactive as iv   # noqa: E402


@pytest.fixture(scope="module")
def volume():
    rng = np.random.default_rng(0)
    data = np.zeros((40, 40, 40))
    zz, yy, xx = np.ogrid[:40, :40, :40]
    data[(zz - 20) ** 2 + (yy - 20) ** 2 + (xx - 20) ** 2 <= 12 ** 2] = 200.0
    return data + rng.normal(0, 5, data.shape)


# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", iv.VOLUME_MODES)
def test_every_volume_mode_builds(mode, volume):
    figure = iv.volume_figure(volume, mode=mode, voxel_size=2.0, unit="nm")
    assert len(figure.data) >= 1
    assert figure.layout.scene.aspectmode == "data", \
        "a cube of voxels must be drawn as a cube"


def test_an_unknown_volume_mode_is_refused(volume):
    with pytest.raises(ValueError, match="mode must be one of"):
        iv.volume_figure(volume, mode="hologram")


def test_a_2d_array_is_refused():
    with pytest.raises(ValueError, match="3D"):
        iv.volume_figure(np.zeros((8, 8)))


def test_a_large_volume_is_strided_down():
    """A browser does not slow down gracefully on a 128³ volume; it locks up."""
    small, step = iv.downsample(np.zeros((128, 128, 128)), iv.MAX_VOXELS)
    assert step > 1
    assert small.size <= iv.MAX_VOXELS


def test_the_subsampling_is_reported_not_hidden():
    figure = iv.volume_figure(np.random.rand(128, 128, 128), mode="points")
    assert "subsampled 1:" in figure.layout.title.text
    assert "128×128×128" in figure.layout.title.text


def test_a_calibrated_volume_title_counts_voxels_not_nanometres():
    figure = iv.volume_figure(np.zeros((8, 8, 8)) + np.arange(8),
                              voxel_size=2.0, unit="nm")
    assert "8×8×8 voxels of 2 nm" in figure.layout.title.text


def test_isosurface_has_no_colour_bar(volume):
    """One surface is one colour; a colour bar would imply a variation."""
    figure = iv.volume_figure(volume, mode="isosurface")
    assert figure.data[0].showscale is False


def test_slice_planes_can_be_moved(volume):
    """A plane fixed at the centre answers only one question."""
    centred = iv.volume_figure(volume, mode="slices")
    moved = iv.volume_figure(volume, mode="slices",
                             slice_fractions=(0.1, 0.9, 0.5))
    assert len(moved.data) == 3
    assert float(moved.data[0].z[0][0]) != float(centred.data[0].z[0][0])


def test_point_cloud_is_capped_and_deterministic(volume):
    """A slider must not reshuffle the cloud on every rerun."""
    first = iv.volume_figure(volume, mode="points", max_points=200)
    second = iv.volume_figure(volume, mode="points", max_points=200)
    assert len(first.data[0].x) <= 200
    assert np.array_equal(first.data[0].x, second.data[0].x)


# ---------------------------------------------------------------------------
# Colourscales
# ---------------------------------------------------------------------------

def test_every_offered_colorscale_actually_exists():
    """Plotly raises on an unknown scale, so an unchecked name is a crash
    waiting for whoever picks it from the menu."""
    from NanoOrganizer.web_app.components.plot_controls import COLORMAPS

    for name in list(COLORMAPS.values()) + list(iv.COLORSCALES):
        go.Figure(go.Heatmap(z=[[0, 1]], colorscale=name))


def test_grey_and_diverging_scales_run_the_same_way_as_matplotlib():
    """Plotly's Greys runs white→black and RdBu red→blue — both the opposite
    way from the matplotlib colormaps of the same name. Getting this wrong
    turns dark TEM particles bright when you switch renderer."""
    import matplotlib
    from plotly.colors import sample_colorscale

    from NanoOrganizer.web_app.components.plot_controls import COLORMAPS

    for mpl_name in ("gray", "viridis", "coolwarm", "hot"):
        cmap = matplotlib.colormaps[mpl_name]
        expected = np.array([cmap(0.0)[:3], cmap(1.0)[:3]]) * 255
        low, high = sample_colorscale(COLORMAPS[mpl_name], [0.0, 1.0])
        got = np.array([[int(v) for v in s[4:-1].split(",")]
                        for s in (low, high)])
        assert np.abs(expected - got).mean() < 60, \
            f"{mpl_name} maps to a scale running the wrong way"


# ---------------------------------------------------------------------------
# Curves and images
# ---------------------------------------------------------------------------

def _curves(n=3):
    x = np.linspace(1.0, 100.0, 50)
    return [(f"s{i}", x, np.exp(-x / (10 * (i + 1))) + 0.01) for i in range(n)]


def test_curves_carry_one_trace_each():
    figure = iv.curves_figure(_curves(4))
    assert len(figure.data) == 4
    assert [t.name for t in figure.data] == ["s0", "s1", "s2", "s3"]


def test_log_limits_are_converted_to_log_units():
    """Plotly ranges on a log axis are exponents. Passing data units there is
    a classic way to get an empty plot."""
    figure = iv.curves_figure(_curves(), logy=True, ylim=(0.01, 10.0))
    assert figure.layout.yaxis.type == "log"
    assert figure.layout.yaxis.range == pytest.approx((-2.0, 1.0))


def test_a_nonpositive_log_limit_is_ignored_rather_than_crashing():
    figure = iv.curves_figure(_curves(), logx=True, xlim=(0.0, 10.0))
    assert figure.layout.xaxis.range is None


def test_a_colour_ramp_replaces_the_legend():
    """Ordered curves get a colour bar; a legend of forty frame names is
    not a legend."""
    figure = iv.curves_figure(_curves(3), colorbar_values=[0.0, 1.0, 2.0],
                              colorbar_label="time (s)")
    assert figure.layout.showlegend is False
    assert any(getattr(t.marker, "showscale", False) for t in figure.data)


def test_image_keeps_square_pixels_square():
    figure = iv.image_figure(np.random.rand(16, 32))
    assert figure.layout.yaxis.scaleanchor == "x"
    assert figure.layout.yaxis.autorange == "reversed"


def test_image_extent_puts_the_axes_in_data_units():
    figure = iv.image_figure(np.random.rand(10, 10), extent=(0.0, 50.0, 50.0, 0.0))
    assert float(figure.data[0].x[-1]) == pytest.approx(50.0)


def test_surface_figure_is_three_dimensional():
    figure = iv.surface_figure(np.random.rand(12, 12))
    assert figure.data[0].type == "surface"
    assert figure.layout.scene.zaxis.title.text == "value"
