"""Tests for the analysis layer: frame grammars, series, linear regions, analyses."""

import numpy as np
import pytest

from NanoOrganizer.analysis import (
    analyses_for, batch, batch_report, get_analysis, run,
)
from NanoOrganizer.analysis.frames import (
    KINETIC, STATIC, detect_grammar, load_series,
)
from NanoOrganizer.analysis.linear import linear_fit, linear_region
from NanoOrganizer.analysis.result import AnalysisResult
from NanoOrganizer.analysis.series import FrameSeries
from NanoOrganizer.core.project import Project
from NanoOrganizer.core.schema import Measurement, Sample

AXIS = np.linspace(300.0, 900.0, 601)

PEAK_CENTRE = 520.0
PEAK_WIDTH = 30.0
PEAK_HEIGHT = 1.0
BASELINE = 0.1


def gaussian(x, centre=PEAK_CENTRE, width=PEAK_WIDTH, height=PEAK_HEIGHT):
    return height * np.exp(-0.5 * ((x - centre) / width) ** 2)


# ---------------------------------------------------------------------------
# FrameSeries
# ---------------------------------------------------------------------------

def _series(n_frames=10):
    values = np.vstack([gaussian(AXIS) + BASELINE for _ in range(n_frames)])
    return FrameSeries(x=AXIS, values=values,
                       t_s=np.arange(n_frames, dtype=float) * 60.0)


def test_series_rejects_mismatched_shapes():
    with pytest.raises(ValueError, match="does not match"):
        FrameSeries(x=AXIS, values=np.zeros((3, 10)), t_s=np.zeros(3))


def test_spectroscopy_aliases_point_at_the_same_arrays():
    series = _series()
    assert series.wavelength is series.x
    assert series.absorbance is series.values


def test_crop_restricts_the_axis():
    cropped = _series().crop(400.0, 600.0)
    assert cropped.x.min() >= 400.0 and cropped.x.max() <= 600.0
    assert cropped.values.shape[1] == cropped.x.size


def test_trace_averages_a_band():
    series = _series()
    trace = series.trace(PEAK_CENTRE, width=4.0)
    assert trace.shape == (len(series),)
    assert trace[0] == pytest.approx(PEAK_HEIGHT + BASELINE, rel=0.01)


def test_select_slices_per_frame_metadata_too():
    """Per-frame metadata that is not sliced silently misaligns."""
    series = _series(6)
    series.meta["label"] = np.array(list("abcdef"))
    kept = series.select([True, False, True, False, True, False])

    assert len(kept) == 3
    assert list(kept.meta["label"]) == ["a", "c", "e"]
    assert len(series) == 6          # the original is untouched


def test_cadence_is_the_delivered_spacing():
    series = FrameSeries(x=AXIS, values=np.zeros((4, AXIS.size)),
                         t_s=np.array([0.0, 60.0, 120.0, 600.0]))
    assert series.cadence_s == pytest.approx(60.0)


def test_mean_between_falls_back_to_the_nearest_frame():
    series = _series(5)
    assert series.mean_between(1e6, 2e6).shape == (AXIS.size,)


# ---------------------------------------------------------------------------
# Frame grammars
# ---------------------------------------------------------------------------

def test_batch_time_grammar_reads_batch_time_and_temperature():
    grammar = detect_grammar(["run_b01_t00000s_T94C.npy",
                              "run_b01_t00002s_T93C.npy"])
    assert grammar.key == "batch_time"
    info = grammar.parse("run_b01_t00042s_T94C.npy")
    assert (info.batch, info.t_s, info.T_c, info.kind) == ("b01", 42.0, 94.0,
                                                           KINETIC)


def test_unrecorded_temperature_is_nan_not_zero():
    grammar = detect_grammar(["run_b01_t00000s_TnaC.npy"])
    assert np.isnan(grammar.parse("run_b01_t00000s_TnaC.npy").T_c)


def test_time_only_grammar_matches_without_a_batch():
    grammar = detect_grammar(["scan_t00060s.npy", "scan_t00120s.npy"])
    assert grammar.parse("scan_t00060s.npy").t_s == 60.0


def test_frame_index_grammar_matches_a_bare_counter():
    grammar = detect_grammar(["scan_0001.npy", "scan_0002.npy",
                              "scan_0003.npy"])
    assert grammar is not None
    assert grammar.parse("scan_0042.npy").t_s == 42.0


def test_grammar_rejects_an_unrelated_name():
    grammar = detect_grammar(["run_b01_t00000s_T94C.npy"])
    assert grammar.parse("wavelength.npy") is None


def test_detect_grammar_refuses_a_coincidental_minority_match():
    names = ["notes.txt", "a.npy", "b.npy", "c.npy", "run_b01_t00000s_T94C.npy"]
    assert detect_grammar(names) is None


def test_a_custom_grammar_can_be_registered():
    """An instrument with its own convention adds one call."""
    import re

    from NanoOrganizer.analysis.frames import FrameGrammar, register_grammar

    grammar = FrameGrammar(
        key="test_custom", label="custom",
        patterns=(re.compile(r"shot(?P<t>\d+)ms"),))
    try:
        register_grammar(grammar)
        assert detect_grammar(["shot0100ms.npy"]).key == "test_custom"
    finally:
        from NanoOrganizer.analysis.frames import GRAMMAR_REGISTRY
        GRAMMAR_REGISTRY.pop("test_custom", None)


# ---------------------------------------------------------------------------
# Linear region detection
# ---------------------------------------------------------------------------

def test_linear_fit_recovers_a_known_slope():
    t = np.linspace(0, 100, 50)
    fit = linear_fit(t, -0.02 * t + 3.0)
    assert fit.slope == pytest.approx(-0.02)
    assert fit.intercept == pytest.approx(3.0)
    assert fit.r2 == pytest.approx(1.0)


def test_slope_error_is_nan_for_two_points():
    """A line through two points has no residual; a zero error would be a lie."""
    fit = linear_fit([0.0, 1.0], [0.0, 1.0])
    assert fit.slope == pytest.approx(1.0)
    assert np.isnan(fit.slope_err)


def test_linear_region_excludes_induction_and_plateau():
    t = np.linspace(0, 300, 301)
    y = np.piecewise(
        t, [t < 100, (t >= 100) & (t <= 200), t > 200],
        [lambda s: 0.0 * s, lambda s: -0.01 * (s - 100), lambda s: -1.0 + 0.0 * s],
    )
    fit = linear_region(t, y, min_points=10)
    assert fit.slope == pytest.approx(-0.01, rel=0.05)
    assert fit.t0 > 50 and fit.t1 < 250


def test_linear_region_handles_a_decay_with_no_plateau():
    """A run stopped before it finished still has a slope."""
    t = np.linspace(0, 7000, 120)
    noise = np.random.default_rng(0).normal(0, 1e-4, t.size)
    fit = linear_region(t, -3e-5 * t + noise, min_points=10)
    assert fit.slope == pytest.approx(-3e-5, rel=0.1)
    assert fit.n > 100


def test_linear_region_reports_when_nothing_is_straight():
    t = np.linspace(0, 100, 60)
    fit = linear_region(t, np.sin(t / 3.0), min_points=10, min_r2=0.99)
    assert fit.note


def test_linear_region_on_a_flat_curve_says_so():
    t = np.linspace(0, 100, 50)
    assert "flat" in linear_region(t, np.zeros_like(t), min_points=10).note


# ---------------------------------------------------------------------------
# A project of curves
# ---------------------------------------------------------------------------

@pytest.fixture
def curves(tmp_path):
    """Two samples, each a short series with one Gaussian band."""
    root = tmp_path / "P"
    run = tmp_path / "mount" / "run"
    run.mkdir(parents=True)
    np.save(run / "axis_wavelength.npy", AXIS)

    for index, centre in enumerate((PEAK_CENTRE, 560.0), start=1):
        for t in range(0, 600, 60):
            np.save(run / f"run_b{index:02d}_t{t:05d}s.npy",
                    gaussian(AXIS, centre=centre) + BASELINE)

    project = Project(root)
    for index, sample_id in enumerate(("S1", "S2"), start=1):
        sample = project.add_sample(sample_id)
        sample.add_measurement(Measurement(
            sample_id=sample_id, modality="uvvis", stage="characterization",
            pattern=f"{run}/run_b{index:02d}_*.npy",
            aux={"wavelength_file": str(run / "axis_wavelength.npy")}))
    return project


def _measurement(project, sample_id="S1"):
    return project.get_sample(sample_id).measurements[0]


def test_load_series_reads_every_frame(curves):
    series = load_series(_measurement(curves), curves.resolver)
    assert len(series) == 10
    assert series.x.size == AXIS.size
    assert series.t_s[0] == 0.0 and series.t_s[-1] == 540.0


def test_load_series_crops_on_request(curves):
    series = load_series(_measurement(curves), curves.resolver, crop=(400, 700))
    assert series.x.min() >= 400 and series.x.max() <= 700


def test_load_series_reports_unmounted_data(curves):
    orphan = Measurement(sample_id="S1", modality="uvvis",
                         pattern="/nowhere/*.npy")
    with pytest.raises(FileNotFoundError, match="path aliases"):
        load_series(orphan, curves.resolver)


def test_load_series_needs_an_axis(tmp_path):
    run = tmp_path / "m"
    run.mkdir()
    for t in (0, 60):
        np.save(run / f"run_b01_t{t:05d}s.npy", gaussian(AXIS))

    project = Project(tmp_path / "P")
    sample = project.add_sample("S1")
    sample.add_measurement(Measurement(sample_id="S1", modality="uvvis",
                                       pattern=f"{run}/run_b01_*.npy"))
    with pytest.raises(FileNotFoundError, match="wavelength axis"):
        load_series(sample.measurements[0], project.resolver)


# ---------------------------------------------------------------------------
# Peak fitting
# ---------------------------------------------------------------------------

def test_peak_fit_recovers_a_known_band(curves):
    result = run("peak_fit", _measurement(curves), curves.resolver)
    assert result.ok, result.message
    assert result.values["peak1_center"] == pytest.approx(PEAK_CENTRE, abs=0.5)
    assert result.values["peak1_width"] == pytest.approx(PEAK_WIDTH, rel=0.05)
    assert result.values["peak1_amplitude"] == pytest.approx(PEAK_HEIGHT, rel=0.05)
    assert result.values["baseline"] == pytest.approx(BASELINE, abs=0.02)
    assert result.values["fit_r2"] > 0.999


def test_peak_fit_reports_an_uncertainty(curves):
    result = run("peak_fit", _measurement(curves), curves.resolver)
    assert "peak1_center" in result.errors
    assert result.errors["peak1_center"] >= 0.0


def test_peak_fit_labels_the_axis_from_the_modality(curves):
    result = run("peak_fit", _measurement(curves), curves.resolver)
    assert result.units["peak1_center"] == "nm"
    assert result.diagnostics["x_unit"] == "nm"


def test_two_peaks_are_not_started_on_the_same_bump(curves):
    """The guess enforces a minimum separation, or both land on one band."""
    measurement = _measurement(curves)
    result = run("peak_fit", measurement, curves.resolver, n_peaks=2,
                 min_r2=0.0)
    centres = [result.values["peak1_center"], result.values["peak2_center"]]
    assert abs(centres[0] - centres[1]) > 1.0


def test_a_poor_fit_is_flagged_rather_than_reported(curves):
    result = run("peak_fit", _measurement(curves), curves.resolver,
                 x_range=(800.0, 900.0), min_r2=0.99)
    assert result.ok is False
    assert "below the" in result.message


def test_peak_fit_rejects_an_unknown_shape(curves):
    result = run("peak_fit", _measurement(curves), curves.resolver,
                 shape="triangle")
    assert result.ok is False and "shape must be" in result.message


@pytest.mark.parametrize("shape", ["gaussian", "lorentzian", "pseudo_voigt"])
def test_every_shape_finds_the_centre(curves, shape):
    result = run("peak_fit", _measurement(curves), curves.resolver, shape=shape)
    assert result.values["peak1_center"] == pytest.approx(PEAK_CENTRE, abs=2.0)


# ---------------------------------------------------------------------------
# Results and write-back
# ---------------------------------------------------------------------------

def test_values_become_derived_records():
    sample = Sample(sample_id="S1")
    result = AnalysisResult(analysis="demo", sample_id="S1",
                            measurement_id="S1:uvvis")
    result.set("peak", 520.0, unit="nm", error=0.4)
    result.diagnostics["x_range"] = (300.0, 900.0)

    assert result.write_to(sample) == ["peak"]
    entry = sample.derived["peak"]
    assert entry.value == pytest.approx(520.0)
    assert entry.unit == "nm"
    assert entry.source == "S1:uvvis"
    assert entry.params["x_range"] == (300.0, 900.0)


def test_nan_values_are_not_written():
    """A NaN is the absence of a measurement, not a measurement of nothing."""
    sample = Sample(sample_id="S1")
    result = AnalysisResult(analysis="demo", sample_id="S1")
    result.set("good", 1.0)
    result.set("bad", float("nan"))
    assert result.write_to(sample) == ["good"]
    assert "bad" not in sample.derived


def test_failed_results_write_nothing():
    sample = Sample(sample_id="S1")
    result = AnalysisResult.failure("demo", "no data")
    result.values["x"] = 1.0
    assert result.write_to(sample) == []
    assert sample.derived == {}


# ---------------------------------------------------------------------------
# Registry and batch
# ---------------------------------------------------------------------------

def test_analyses_are_offered_by_group(curves):
    keys = {a.key for a in analyses_for(_measurement(curves))}
    assert "peak_fit" in keys              # a curve
    assert "particle_sizing" not in keys   # declared for image modalities


def test_unknown_analysis_lists_what_exists():
    with pytest.raises(KeyError, match="peak_fit"):
        get_analysis("not_an_analysis")


def test_batch_writes_derived_values(curves):
    """Names are prefixed with the modality, because peak_fit is not specific
    to one: without that, fitting a UV-Vis band and then a diffraction peak
    would put both centres in one column and the second would win silently."""
    frame = batch(curves, "peak_fit")
    assert len(frame) == 2 and int(frame["ok"].sum()) == 2
    assert curves.get_sample("S1").get_derived("uvvis_peak1_center") == \
        pytest.approx(PEAK_CENTRE, abs=0.5)
    assert curves.get_sample("S2").get_derived("uvvis_peak1_center") == \
        pytest.approx(560.0, abs=0.5)


def test_batch_prefix_can_be_overridden(curves):
    batch(curves, "peak_fit", prefix="")
    assert curves.get_sample("S1").get_derived("peak1_center") == \
        pytest.approx(PEAK_CENTRE, abs=0.5)


def test_batch_can_skip_the_write_back(curves):
    batch(curves, "peak_fit", write=False)
    assert curves.get_sample("S1").derived == {}


def test_batch_keeps_going_after_a_failure(curves):
    """One unreadable measurement must not end the batch."""
    curves.get_sample("S2").add_measurement(Measurement(
        sample_id="S2", modality="uvvis", role="broken",
        pattern="/nowhere/*.npy"))

    frame = batch(curves, "peak_fit")
    assert len(frame) == 3 and int(frame["ok"].sum()) == 2
    assert "2/3 succeeded" in batch_report(frame)


def test_batch_restricts_to_a_sample_basket(curves):
    assert len(batch(curves, "peak_fit", sample_ids=["S1"])) == 1
    assert len(batch(curves, "peak_fit", sample_ids=["nope"])) == 0


def test_batch_report_on_an_empty_table():
    import pandas as pd
    assert batch_report(pd.DataFrame()) == "no measurements matched"


# ---------------------------------------------------------------------------
# Imaging
# ---------------------------------------------------------------------------

def _disc_image(size=512, radius=12, spacing=48, background=200, particle=60):
    """Separated dark discs on a light background, with a little noise."""
    image = np.full((size, size), float(background))
    rng = np.random.default_rng(0)
    count = 0
    for row in range(spacing, size - spacing, spacing):
        for column in range(spacing, size - spacing, spacing):
            yy, xx = np.ogrid[:size, :size]
            image[(yy - row) ** 2 + (xx - column) ** 2 <= radius ** 2] = particle
            count += 1
    return image + rng.normal(0, 2.0, image.shape), count


def test_segmentation_finds_separated_discs():
    from NanoOrganizer.analysis.imaging import measure_particles, segment_particles

    image, expected = _disc_image()
    labels, _ = segment_particles(image, dark_particles=True, min_area_px=20)
    diameters, _ = measure_particles(labels, nm_per_pixel=1.0, border_margin_px=2)
    assert len(diameters) == expected
    assert diameters.mean() == pytest.approx(24.0, rel=0.05)   # 2 * radius


def test_calibration_converts_pixels_to_nanometres():
    from NanoOrganizer.analysis.imaging import measure_particles, segment_particles

    image, _ = _disc_image()
    labels, _ = segment_particles(image, dark_particles=True, min_area_px=20)
    in_px, _ = measure_particles(labels, nm_per_pixel=None, border_margin_px=2)
    in_nm, _ = measure_particles(labels, nm_per_pixel=0.5, border_margin_px=2)
    assert in_nm.mean() == pytest.approx(0.5 * in_px.mean(), rel=1e-6)


def test_faint_blobs_are_rejected_before_strong_ones():
    """Film texture is blob-shaped but not dark; a particle is both.

    The threshold Otsu picks depends on what is in the frame, so this checks
    the behaviour instead: tightening the contrast floor only removes more, and
    the faint blob goes before any real particle.
    """
    from NanoOrganizer.analysis.imaging import segment_particles

    image, expected = _disc_image(particle=60)
    yy, xx = np.ogrid[:512, :512]
    image[(yy - 24) ** 2 + (xx - 24) ** 2 <= 144] = 110   # faint, same size

    def rejected(fraction):
        labels, info = segment_particles(image, dark_particles=True,
                                         min_area_px=20,
                                         min_contrast_frac=fraction)
        return info.get("n_rejected_contrast", 0), labels

    none, labels_off = rejected(0.0)
    assert none == 0
    assert int(labels_off.max()) == expected + 1

    some, labels_on = rejected(0.4)
    assert some == 1
    assert labels_on[24, 24] == 0

    harsh, _ = rejected(0.99)
    assert harsh == expected + 1


def test_seed_spacing_adapts_to_particle_size():
    """A fixed spacing suiting one magnification bisects particles at another."""
    from NanoOrganizer.analysis.imaging import segment_particles

    big, expected = _disc_image(radius=24, spacing=96)
    labels, info = segment_particles(big, dark_particles=True, min_area_px=50)
    assert info["min_distance_auto"] is True
    assert info["min_distance_px"] > 5
    assert int(labels.max()) == expected


def test_uncalibrated_images_report_pixels_not_nanometres(tmp_path):
    from PIL import Image

    folder = tmp_path / "TEMData" / "S1"
    folder.mkdir(parents=True)
    image, _ = _disc_image()
    Image.fromarray(image.astype(np.uint8)).save(folder / "a.tif")

    project = Project(tmp_path / "P")
    sample = project.add_sample("S1")
    sample.add_measurement(Measurement(sample_id="S1", modality="tem",
                                       paths=[str(folder / "a.tif")]))

    result = run("particle_sizing", sample.measurements[0], project.resolver)
    assert result.diagnostics["calibrated"] is False
    assert result.diagnostics["unit"] == "px"
    assert "PIXELS" in result.message


def test_banner_rows_are_cropped(tmp_path):
    """Some instruments append an info bar, making the frame non-square."""
    from PIL import Image

    from NanoOrganizer.analysis.imaging import read_micrograph

    image, _ = _disc_image(size=256)
    tall = np.vstack([image, np.full((40, 256), 255.0)])
    path = tmp_path / "a.tif"
    Image.fromarray(tall.astype(np.uint8)).save(path)

    array, _, info = read_micrograph(path)
    assert array.shape == (256, 256)
    assert info["banner_rows"] == 40


# ---------------------------------------------------------------------------
# Sloping backgrounds
# ---------------------------------------------------------------------------

@pytest.fixture
def sloping(tmp_path):
    """One band sitting on a background that rises across the window.

    The normal case away from UV-Vis: an XPS inelastic tail, a Raman
    fluorescence ramp, an interband edge under a plasmon.
    """
    root = tmp_path / "P"
    folder = tmp_path / "mount"
    folder.mkdir(parents=True)
    y = gaussian(AXIS) + BASELINE + 0.002 * (AXIS - AXIS[0])
    np.savetxt(folder / "spectrum.dat", np.column_stack([AXIS, y]))

    project = Project(root)
    sample = project.add_sample("S1")
    sample.add_measurement(Measurement(sample_id="S1", modality="raman",
                                       paths=[str(folder / "spectrum.dat")]))
    return project


def test_a_flat_background_biases_the_centre_of_a_tilted_band(sloping):
    """Not merely a worse fit — the peak is dragged up the slope."""
    measurement = sloping.get_sample("S1").measurements[0]
    flat = run("peak_fit", measurement, sloping.resolver, min_r2=0.0)
    assert abs(flat.values["peak1_center"] - PEAK_CENTRE) > 2.0


def test_a_linear_background_recovers_it(sloping):
    measurement = sloping.get_sample("S1").measurements[0]
    fit = run("peak_fit", measurement, sloping.resolver, background="linear")
    assert fit.ok, fit.message
    assert fit.values["peak1_center"] == pytest.approx(PEAK_CENTRE, abs=0.5)
    assert fit.values["baseline_slope"] == pytest.approx(0.002, rel=0.05)
    assert fit.diagnostics["background"] == "linear"


def test_peak_fit_rejects_an_unknown_background(sloping):
    result = run("peak_fit", sloping.get_sample("S1").measurements[0],
                 sloping.resolver, background="cubic")
    assert result.ok is False and "background must be" in result.message


# ---------------------------------------------------------------------------
# Curve metrics
# ---------------------------------------------------------------------------

def test_curve_metrics_finds_the_band(sloping):
    measurement = sloping.get_sample("S1").measurements[0]
    result = run("curve_metrics", measurement, sloping.resolver,
                 x_min=420.0, x_max=620.0)
    assert result.ok, result.message
    assert result.values["x_at_max"] == pytest.approx(PEAK_CENTRE, abs=2.0)
    assert result.values["y_max"] == pytest.approx(PEAK_HEIGHT, rel=0.05)
    # A symmetric band has its centre of mass at its centre.
    assert result.values["x_centroid"] == pytest.approx(PEAK_CENTRE, abs=2.0)


def test_curve_metrics_area_matches_the_analytic_gaussian(sloping):
    result = run("curve_metrics", sloping.get_sample("S1").measurements[0],
                 sloping.resolver, x_min=400.0, x_max=640.0)
    expected = PEAK_HEIGHT * PEAK_WIDTH * np.sqrt(2.0 * np.pi)
    assert result.values["area"] == pytest.approx(expected, rel=0.05)


def test_curve_metrics_finds_a_threshold_crossing(sloping):
    """The same operation as 'the potential at 10 mA/cm²'."""
    result = run("curve_metrics", sloping.get_sample("S1").measurements[0],
                 sloping.resolver, x_min=300.0, x_max=500.0, threshold=0.5,
                 subtract_baseline=False)
    crossing = result.values["x_at_threshold"]
    assert 440.0 < crossing < 500.0


def test_a_threshold_that_is_never_reached_says_so(sloping):
    result = run("curve_metrics", sloping.get_sample("S1").measurements[0],
                 sloping.resolver, x_min=300.0, x_max=400.0, threshold=99.0)
    assert "never reaches" in result.message
    assert "x_at_threshold" not in result.values


def test_curve_metrics_refuses_an_empty_window(sloping):
    result = run("curve_metrics", sloping.get_sample("S1").measurements[0],
                 sloping.resolver, x_min=1000.0, x_max=1100.0)
    assert result.ok is False and "nothing to summarise" in result.message


# ---------------------------------------------------------------------------
# Contrast polarity
# ---------------------------------------------------------------------------

def _disc_field(value, background):
    image = np.full((200, 200), float(background))
    yy, xx = np.ogrid[:200, :200]
    for row in (50, 150):
        for column in (50, 150):
            image[(yy - row) ** 2 + (xx - column) ** 2 <= 20 ** 2] = float(value)
    return image


@pytest.mark.parametrize("value,background,expect_dark", [
    (40, 200, True),     # TEM: metal absorbs
    (220, 60, False),    # SEM: particles glow
])
def test_segmentation_reads_the_polarity_off_the_image(value, background,
                                                       expect_dark):
    """Getting this backwards segments the support and reports its size with
    the same confidence, which is the worst possible failure mode."""
    from NanoOrganizer.analysis.imaging import segment_particles

    labels, info = segment_particles(_disc_field(value, background))
    assert info["dark_particles"] is expect_dark
    assert info["dark_particles_auto"] is True
    assert int(labels.max()) == 4


def test_an_explicit_polarity_still_wins():
    from NanoOrganizer.analysis.imaging import segment_particles

    _, info = segment_particles(_disc_field(40, 200), dark_particles=False)
    assert info["dark_particles"] is False
    assert "dark_particles_auto" not in info


# ---------------------------------------------------------------------------
# Reading curves that are one file per frame
# ---------------------------------------------------------------------------

def _two_column_series(folder, centres, *, header=""):
    """A growth series written the common way: one two-column file per frame."""
    import numpy as np

    folder.mkdir(parents=True, exist_ok=True)
    x = np.linspace(400.0, 700.0, 301)
    for index, centre in enumerate(centres):
        y = np.exp(-0.5 * ((x - centre) / 25.0) ** 2) + 0.05
        np.savetxt(folder / f"run_t{index * 60:04d}s.csv",
                   np.column_stack([x, y]), delimiter=",",
                   header=header, comments="" if header else "# ")
    return x


def test_peak_fit_on_per_file_frames_honours_reduce(tmp_path):
    """The endpoint of a series must not quietly become its first frame.

    A folder of two-column files is a time series as surely as a stack of
    single-column frames is. Reading ``paths[0]`` and reporting
    ``reduce='last_decile'`` answers a different question from the one asked,
    and says it did the right thing while doing so.
    """
    from NanoOrganizer.analysis import peaks
    from NanoOrganizer.core.pathmap import PathResolver
    from NanoOrganizer.core.schema import Measurement

    folder = tmp_path / "spectra"
    _two_column_series(folder, [500.0, 520.0, 540.0, 560.0])
    measurement = Measurement(sample_id="S1", modality="uvvis",
                              pattern=f"{folder}/run_t*.csv")
    resolver = PathResolver()

    x, y, info = peaks.load_curve(measurement, resolver, reduce="last_decile")
    assert float(x[y.argmax()]) == pytest.approx(560.0, abs=2.0)
    assert "last 1 of 4" in info["source"]

    x, y, info = peaks.load_curve(measurement, resolver, reduce="frame",
                                  index=0)
    assert float(x[y.argmax()]) == pytest.approx(500.0, abs=2.0)
    assert "file 0 of 4" in info["source"]

    x, y, info = peaks.load_curve(measurement, resolver, reduce="mean")
    assert "mean of 4 files" in info["source"]


def test_peak_fit_reports_which_curve_it_actually_read(tmp_path):
    """The diagnostic has to describe what happened, not what was requested."""
    from NanoOrganizer.analysis import peaks
    from NanoOrganizer.core.pathmap import PathResolver
    from NanoOrganizer.core.schema import Measurement

    folder = tmp_path / "spectra"
    _two_column_series(folder, [500.0, 530.0, 560.0])
    measurement = Measurement(sample_id="S1", modality="uvvis",
                              pattern=f"{folder}/run_t*.csv")

    result = peaks.peak_fit(measurement, PathResolver(), x_range=(450, 650),
                            n_peaks=1)
    assert result.ok, result.message
    assert result.values["peak1_center"] == pytest.approx(560.0, abs=3.0)
    assert "of 3" in result.diagnostics["curve_source"]


def test_a_single_file_is_unaffected_by_the_reduce_path(tmp_path):
    import numpy as np

    from NanoOrganizer.analysis import peaks
    from NanoOrganizer.core.pathmap import PathResolver
    from NanoOrganizer.core.schema import Measurement

    x = np.linspace(2.0, 4.0, 400)
    y = 100 * np.exp(-0.5 * ((x - 3.0) / 0.05) ** 2) + 5.0
    path = tmp_path / "one.dat"
    np.savetxt(path, np.column_stack([x, y]))

    measurement = Measurement(sample_id="S1", modality="waxs1d",
                              paths=[str(path)])
    result = peaks.peak_fit(measurement, PathResolver(), x_range=(2.5, 3.5),
                            n_peaks=1)
    assert result.ok
    assert result.values["peak1_center"] == pytest.approx(3.0, abs=0.01)


def test_a_bare_csv_header_row_is_not_a_corrupt_file(tmp_path):
    """Instruments export ``wavelength,absorbance`` on line one constantly."""
    from NanoOrganizer.analysis.reading import read_array

    folder = tmp_path / "spectra"
    _two_column_series(folder, [520.0], header="wavelength_nm,absorbance")
    path = next(folder.glob("*.csv"))
    assert "wavelength_nm" in path.read_text().splitlines()[0]

    array = read_array(path)
    assert array.shape == (301, 2)


def test_two_header_rows_are_reported_not_guessed_at(tmp_path):
    from NanoOrganizer.analysis.reading import read_array

    path = tmp_path / "odd.csv"
    path.write_text("instrument,LabSpec\nwavelength,absorbance\n400,0.1\n")
    with pytest.raises(ValueError, match="header row"):
        read_array(path)
