"""Tests for the single-file Organizer, dict ingest, and stored results.

These cover the three things that make an organiser usable from a notebook
rather than only from a project directory: it is **one named file**, metadata
goes in as a **live dict** you can keep editing, and an analysis result can be
**linked back** so it is readable again without being recomputed.
"""

from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt                                    # noqa: E402

from NanoOrganizer import Organizer, open_project                   # noqa: E402
from NanoOrganizer.analysis import store as result_store            # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture()
def data(tmp_path):
    """A rig's output: spectra in one tree, diffraction in another."""
    spectra = tmp_path / "rig" / "spectrometer"
    xrd = tmp_path / "rig" / "diffractometer"
    spectra.mkdir(parents=True)
    xrd.mkdir(parents=True)

    wavelength = np.linspace(400.0, 700.0, 301)
    q = np.linspace(2.0, 4.0, 400)

    for index, sample in enumerate(("S01", "S02"), start=1):
        centre = 520.0 + 10.0 * index
        for frame in range(4):
            grown = 0.3 + 0.7 * (frame + 1) / 4
            band = grown * np.exp(-0.5 * ((wavelength - centre) / 25.0) ** 2)
            np.savetxt(spectra / f"{sample}_t{frame * 60:04d}s.csv",
                       np.column_stack([wavelength, band + 0.05]),
                       delimiter=",", header="wavelength_nm,absorbance",
                       comments="")
        pattern = 100 * np.exp(-0.5 * ((q - 3.0) / 0.05) ** 2) + 5.0
        np.savetxt(xrd / f"{sample}.dat", np.column_stack([q, pattern]))

    return {"spectra": spectra, "xrd": xrd}


@pytest.fixture()
def records(data):
    """The dict an operator keeps — spectra only; the XRD is not in it."""
    return {
        sample: {
            "sample_id": sample,
            "synthesis_batch": {"run_id": f"run_{index}", "status": "done"},
            "conditions": {"temperature_C": 60.0 + 20.0 * index},
            "uvvis_growth": {
                "modality": "uvvis",
                "spectrum_glob": f"{data['spectra']}/{sample}_t*.csv",
            },
        }
        for index, sample in enumerate(("S01", "S02"), start=1)
    }


@pytest.fixture()
def org(tmp_path, records):
    organizer = Organizer(tmp_path / "lab.json", name="lab")
    organizer.ingest(synthesis=records)
    return organizer


# ---------------------------------------------------------------------------
# One named file
# ---------------------------------------------------------------------------

def test_the_organizer_is_the_file_you_named(tmp_path):
    organizer = Organizer(tmp_path / "study.json", name="my study")
    assert organizer.path == tmp_path / "study.json"
    assert organizer.project.single_file

    organizer.add_sample("S01", temperature_C=90)
    organizer.save()

    assert (tmp_path / "study.json").exists()
    # No hidden directory: the document is the whole store.
    assert not (tmp_path / ".nanoorganizer").exists()


def test_reopening_restores_everything(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    org.set_params("S01", stage="synthesis", operator="RH")
    org.save()

    again = Organizer(org.path)
    assert again.project.config.name == "lab"
    assert again.project.sample_ids() == ["S01", "S02"]
    assert again["S01"].stage("synthesis").params["operator"] == "RH"
    assert again.measurement("S01", modality="waxs1d").resolve(again.resolver)


def test_metadata_is_the_record_that_was_ingested(org, records):
    every = org.metadata("S01")
    assert list(every) == ["synthesis"]
    assert every["synthesis"]["conditions"] == {"temperature_C": 80.0}

    synthesis = org.metadata("S01", "synthesis")
    assert synthesis["synthesis_batch"]["run_id"] == "run_1"

    synthesis["conditions"]["temperature_C"] = 0.0      # a copy, not the store
    assert org.metadata("S01", "synthesis")["conditions"]["temperature_C"] == 80.0

    with pytest.raises(KeyError, match="no stage 'catalysis'.*synthesis"):
        org.metadata("S01", "catalysis")


def test_a_directory_gets_a_default_filename(tmp_path):
    organizer = Organizer(tmp_path / "somewhere")
    assert organizer.path.name == "organizer.json"


def test_open_project_routes_a_json_path_to_an_organizer(org):
    """One call for both shapes, so the GUI needs no special case."""
    org.save()
    reopened = open_project(org.path)
    assert isinstance(reopened, Organizer)
    assert reopened.project.sample_ids() == ["S01", "S02"]


# ---------------------------------------------------------------------------
# Ingesting a live dict
# ---------------------------------------------------------------------------

def test_a_dict_ingests_without_being_written_to_a_file(org):
    assert org.project.sample_ids() == ["S01", "S02"]
    assert org["S01"].stage("synthesis").params["conditions"]["temperature_C"] == 80.0
    assert org["S01"].modalities == ["uvvis"]


def test_the_keyword_names_the_stage(tmp_path, records):
    organizer = Organizer(tmp_path / "lab.json")
    organizer.ingest(reaction=records)
    assert "reaction" in organizer["S01"].stages
    assert "synthesis" not in organizer["S01"].stages


def test_a_positional_dict_needs_a_stage_and_takes_one(tmp_path, records):
    organizer = Organizer(tmp_path / "lab.json")
    organizer.ingest(records, stage="synthesis")
    assert "synthesis" in organizer["S01"].stages


def test_a_path_and_a_dict_together_are_refused(tmp_path, records):
    organizer = Organizer(tmp_path / "lab.json")
    with pytest.raises(TypeError, match="not both"):
        organizer.ingest("some_file.py", synthesis=records)


def test_re_ingesting_merges_by_default(org, records):
    records["S01"]["conditions"]["stir_rate_rpm"] = 400
    org.ingest(synthesis=records)
    params = org["S01"].stage("synthesis").params["conditions"]
    assert params["stir_rate_rpm"] == 400
    assert params["temperature_C"] == 80.0


def test_replace_makes_the_dict_the_whole_truth(org, records):
    """Edit-and-re-ingest has to be able to *remove*, not only add."""
    records["S01"]["conditions"].pop("temperature_C")
    records["S01"]["conditions"]["temperature_K"] = 353.0
    org.ingest(synthesis=records, replace=True)

    params = org["S01"].stage("synthesis").params["conditions"]
    assert "temperature_C" not in params
    assert params["temperature_K"] == 353.0


def test_replace_drops_a_sample_that_left_the_dict(org, records):
    records.pop("S02")
    org.ingest(synthesis=records, replace=True)
    assert org.project.sample_ids() == ["S01"]


def test_replace_keeps_a_sample_that_has_links_of_its_own(org, records, data):
    """Linked data is not the dict's to delete."""
    org.link("S02", "waxs1d", f"{data['xrd']}/S02.dat")
    records.pop("S02")
    org.ingest(synthesis=records, replace=True)

    assert "S02" in org.project.sample_ids()
    assert "synthesis" not in org["S02"].stages
    assert org["S02"].modalities == ["waxs1d"]


def test_a_new_record_is_appended(org, records):
    records["S03"] = {"sample_id": "S03",
                      "synthesis_batch": {"status": "error"},
                      "conditions": {"temperature_C": 120.0}}
    org.ingest(synthesis=records, replace=True)
    assert org.project.sample_ids() == ["S01", "S02", "S03"]
    assert org["S03"].measurements == []


# ---------------------------------------------------------------------------
# Results, linked back
# ---------------------------------------------------------------------------

def test_a_result_file_round_trips(tmp_path):
    from NanoOrganizer.analysis.result import AnalysisResult

    result = AnalysisResult(
        analysis="peak_fit", sample_id="S01", measurement_id="S01:uvvis",
        values={"peak1_center": 530.0}, errors={"peak1_center": 0.4},
        units={"peak1_center": "nm"},
        curves={"x": np.linspace(0, 1, 5), "y_fit": np.arange(5.0)},
        diagnostics={"n_points": 5}, message="")

    path = result_store.save_result(result, tmp_path)
    loaded = result_store.load_result(path)

    assert loaded.analysis == "peak_fit"
    assert loaded.values["peak1_center"] == 530.0
    assert loaded.errors["peak1_center"] == 0.4
    assert loaded.diagnostics["n_points"] == 5
    np.testing.assert_allclose(loaded.curves["y_fit"], np.arange(5.0))


def test_loading_something_that_is_not_a_result_says_so(tmp_path):
    path = tmp_path / "plain.npz"
    np.savez(path, data=np.arange(4.0))
    with pytest.raises(ValueError, match="not a NanoOrganizer result"):
        result_store.load_result(path)


def test_link_result_attaches_the_fit_to_its_sample(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    fit = org.run("peak_fit", "S01", modality="waxs1d", x_range=(2.5, 3.5),
                  n_peaks=1)
    assert fit.ok

    measurement = org.link_result(fit)
    assert measurement.modality == "fit"
    assert measurement.stage == "analysis"
    # The role names the technique it ran on, so two fits of one analysis
    # cannot share an id.
    assert measurement.role == "peak_fit-waxs1d"
    # Recorded relative to the organizer's folder, and resolved from there.
    assert not Path(measurement.paths[0]).is_absolute()
    assert measurement.resolve(org.resolver)
    # The scalars reached the table too.
    assert org["S01"].get_derived("waxs1d_peak1_center") == pytest.approx(3.0,
                                                                         abs=0.05)


def test_a_linked_fit_cannot_make_the_raw_data_ambiguous(org, data):
    """Why a fit gets its own modality rather than reusing the source's."""
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    org.link_result(org.run("peak_fit", "S01", modality="waxs1d",
                            x_range=(2.5, 3.5), n_peaks=1))
    assert org.plot("S01", "waxs1d") is not None


def test_a_fit_survives_reopening_and_redraws_without_refitting(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
              link=True, verbose=False)
    org.save()

    later = Organizer(org.path)
    loaded = later.result("S01", "peak_fit")
    assert loaded.analysis == "peak_fit"
    assert set(["x", "y", "y_fit", "residual"]).issubset(loaded.curves)
    assert later.plot_result("S01", "peak_fit") is not None
    # And through the ordinary dispatch, which must not read the bundle as
    # a plain array.
    assert later.plot("S01", "fit") is not None


def test_results_table_lists_what_has_been_analysed(org, data):
    for sample in ("S01", "S02"):
        org.link(sample, "waxs1d", f"{data['xrd']}/{sample}.dat")
    org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
              link=True, verbose=False)

    table = org.results()
    assert sorted(table["sample_id"]) == ["S01", "S02"]
    assert set(table["analysis"]) == {"peak_fit"}
    assert table["readable"].all()
    assert "fit_r2" in table.columns


def test_results_can_live_in_a_project_folder_beside_the_organizer(
        tmp_path, records, data):
    """Many organizers in one folder, each project's results in its own."""
    org = Organizer(tmp_path / "Orgnizer" / "lab.json", name="lab")
    org.ingest(synthesis=records)
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    results = tmp_path / "Project" / "Results"
    org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
              write=False, link=True, folder=results, verbose=False)

    measurement = org.measurement("S01", "fit")
    assert measurement.paths[0].startswith("../Project/Results/")
    assert (results / Path(measurement.paths[0]).name).exists()
    # write=False: the values are in the file, not in the organizer.
    assert not org["S01"].derived
    org.save()

    later = Organizer(org.path)
    table = later.results(analysis="peak_fit")
    assert list(table["sample_id"]) == ["S01"]
    assert table["readable"].all() and "fit_r2" in table.columns
    assert later.results(analysis="something_else").empty

    # A relative folder is relative to the organizer, not to where Python runs.
    later.link_result(later.run("peak_fit", "S01", modality="waxs1d",
                                x_range=(2.5, 3.5), n_peaks=1),
                      folder="../Project/Results", write=False)
    assert later.measurement("S01", "fit").resolve(later.resolver)[0] \
        .parent.resolve() == results.resolve()


def test_an_analysis_can_run_on_another_analysis_stored_result(org, data):
    from NanoOrganizer.analysis import (ANALYSIS_REGISTRY, Analysis,
                                        AnalysisResult, register_analysis)
    from NanoOrganizer.analysis import store as result_store

    def peak_shift(measurement, resolver, **_):
        fit = result_store.load_result(measurement.resolve(resolver)[0])
        result = AnalysisResult("peak_shift", sample_id=fit.sample_id,
                                measurement_id=fit.measurement_id)
        return result.set("shift", fit.values["peak1_center"] - 3.0)

    register_analysis(Analysis("peak_shift", peak_shift, modalities=("fit",),
                               stages=("analysis",), results_of=("peak_fit",)))
    try:
        org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
        org.link_result(org.run("peak_fit", "S01", modality="waxs1d",
                                x_range=(2.5, 3.5), n_peaks=1))
        assert "peak_shift" not in org.analyses("S01", modality="waxs1d")

        first = org.run("peak_shift", "S01")
        assert first.values["shift"] == pytest.approx(0.0, abs=0.05)
        org.link_result(first, write=False)
        # Its own stored result is not something it runs on: still one target.
        frame = org.batch("peak_shift", write=False, link=True, verbose=False)
        assert len(frame) == 1 and frame["ok"].all()
        assert org.result("S01", "peak_shift").values["shift"] == \
            pytest.approx(first.values["shift"])
    finally:
        ANALYSIS_REGISTRY.pop("peak_shift", None)


@pytest.fixture()
def toy(org, data):
    """A registered analysis with a method on arrays, counting its runs."""
    from NanoOrganizer.analysis import (ANALYSIS_REGISTRY, Analysis,
                                        AnalysisResult, register_analysis)
    from NanoOrganizer.analysis.peaks import load_curve

    calls = []

    def toy_peak(x, y, *, scale: float = 1.0, window=(2.0, 4.0)):
        inside = (x >= window[0]) & (x <= window[1])
        result = AnalysisResult("toy_peak")
        result.set("height", scale * float(y[inside].max()))
        result.curves["x"] = x
        return result

    def adapter(measurement, resolver, **settings):
        calls.append(measurement.sample_id)
        x, y, _ = load_curve(measurement, resolver)
        result = toy_peak(x, y, **settings)
        result.sample_id = measurement.sample_id
        result.measurement_id = measurement.measurement_id
        return result

    register_analysis(Analysis("toy_peak", adapter, modalities=("waxs1d",),
                               kernel=toy_peak))
    for sample in ("S01", "S02"):
        org.link(sample, "waxs1d", f"{data['xrd']}/{sample}.dat")
    yield calls
    ANALYSIS_REGISTRY.pop("toy_peak", None)


def test_settings_are_recorded_with_their_defaults_and_kept(org, toy, tmp_path):
    result = org.run("toy_peak", "S01", settings={"scale": 2.0})
    assert result.settings == {"scale": 2.0, "window": [2.0, 4.0]}
    org.link_result(result, folder=tmp_path, write=False)
    assert org.result("S01", "toy_peak").settings == result.settings


def test_done_before_is_loaded_not_run_again(org, toy, tmp_path, capsys):
    keep = dict(link=True, write=False, folder=tmp_path)
    first = org.run("toy_peak", "S01", settings={"scale": 2.0}, **keep)
    again = org.run("toy_peak", "S01", settings={"scale": 2.0}, **keep)
    assert toy == ["S01"]                                 # ran once
    assert again.values == first.values
    assert "done before" in capsys.readouterr().out

    org.run("toy_peak", "S01", settings={"scale": 3.0}, **keep)
    assert toy == ["S01", "S01"]                          # other settings: ran
    org.run("toy_peak", "S01", settings={"scale": 3.0}, overwrite=True, **keep)
    assert len(toy) == 3                                  # asked to: ran
    for path in tmp_path.glob("*.npz"):
        path.unlink()
    org.run("toy_peak", "S01", settings={"scale": 3.0}, **keep)
    assert len(toy) == 4                                  # file gone: ran


def test_batch_takes_samples_and_says_what_it_did(org, toy, tmp_path):
    keep = dict(link=True, write=False, folder=tmp_path, verbose=False)
    frame = org.batch("toy_peak", "S01", settings={"scale": 2.0}, **keep)
    assert list(frame["sample_id"]) == ["S01"] and list(frame["status"]) == ["ran"]

    frame = org.batch("toy_peak", ["S01", "S02"], settings={"scale": 2.0}, **keep)
    assert dict(zip(frame["sample_id"], frame["status"])) == {
        "S01": "loaded", "S02": "ran"}
    frame = org.batch("toy_peak", settings={"scale": 2.0}, **keep)
    assert set(frame["status"]) == {"loaded"} and len(frame) == 2
    assert toy == ["S01", "S02"]


def test_new_samples_are_done_the_way_the_kept_ones_were(org, toy, tmp_path):
    keep = dict(link=True, write=False, folder=tmp_path, verbose=False)
    assert org.kept_settings("toy_peak") == {}            # nothing kept yet
    org.batch("toy_peak", "S01", settings={"scale": 2.0}, **keep)
    used = org.kept_settings("toy_peak")
    assert used == {"scale": 2.0, "window": [2.0, 4.0]}   # defaults included

    frame = org.batch("toy_peak", settings=used, **keep)
    assert dict(zip(frame["sample_id"], frame["status"])) == {
        "S01": "loaded", "S02": "ran"}

    org.run("toy_peak", "S02", settings={"scale": 3.0}, **keep)   # redone
    assert org.kept_settings("toy_peak", "S02")["scale"] == 3.0
    assert org.kept_settings("toy_peak", "S01")["scale"] == 2.0
    assert org.kept_settings("toy_peak", "nobody") == {}


def test_a_mistyped_setting_is_refused_not_ignored(org, toy):
    with pytest.raises(TypeError, match="no setting 'scal'.*scale, window"):
        org.run("toy_peak", "S01", scal=2.0)
    with pytest.raises(TypeError, match="no setting"):
        org.batch("toy_peak", settings={"scal": 2.0}, verbose=False)
    with pytest.raises(TypeError, match="no setting"):
        org.run_method("toy_peak", np.arange(5.0), np.ones(5), scal=2.0)
    # An analysis without a method on arrays keeps its tolerant options.
    assert "x_range" in org.run("peak_fit", "S01", modality="waxs1d",
                                x_range=(2.5, 3.5)).settings


def test_run_method_is_run_on_arrays_you_hold(org, toy):
    from NanoOrganizer.analysis.peaks import load_curve

    settings = {"scale": 2.0, "window": (2.5, 3.5)}
    x, y, _ = load_curve(org.measurement("S01", "waxs1d"), org.resolver)
    on_arrays = org.run_method("toy_peak", x, y, settings=settings)
    on_sample = org.run("toy_peak", "S01", settings=settings)
    assert on_arrays.values == on_sample.values
    assert on_arrays.settings == on_sample.settings
    with pytest.raises(TypeError, match="no method on arrays"):
        org.run_method("peak_fit", x, y)


def test_a_result_built_on_another_reruns_when_that_one_is_redone(
        org, toy, tmp_path):
    from NanoOrganizer.analysis import (ANALYSIS_REGISTRY, Analysis,
                                        AnalysisResult, register_analysis)
    from NanoOrganizer.analysis import store as result_store

    calls = []

    def double(measurement, resolver, **_):
        calls.append(1)
        peak = result_store.load_result(measurement.resolve(resolver)[0])
        result = AnalysisResult("toy_double", sample_id=peak.sample_id,
                                measurement_id=peak.measurement_id)
        return result.set("twice", 2 * peak.values["height"])

    register_analysis(Analysis("toy_double", double, modalities=("fit",),
                               stages=("analysis",), results_of=("toy_peak",)))
    keep = dict(link=True, write=False, folder=tmp_path, verbose=False)
    try:
        org.run("toy_peak", "S01", settings={"scale": 1.0}, **keep)
        org.run("toy_double", "S01", **keep)
        org.run("toy_double", "S01", **keep)
        assert len(calls) == 1                            # loaded the second time
        org.run("toy_peak", "S01", settings={"scale": 5.0}, **keep)
        twice = org.run("toy_double", "S01", **keep)
        assert len(calls) == 2                            # its input changed
        assert twice.values["twice"] == pytest.approx(
            2 * org.result("S01", "toy_peak").values["height"])
    finally:
        ANALYSIS_REGISTRY.pop("toy_double", None)


def test_batch_without_link_writes_no_files(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
              verbose=False)
    assert not org.results_dir.exists()
    assert org["S01"].get_derived("waxs1d_peak1_center") is not None


def test_asking_for_a_result_that_was_never_linked_says_so(org):
    with pytest.raises(KeyError):
        org.result("S01", "peak_fit")


# ---------------------------------------------------------------------------
# A: looking at the organiser, and carving subsets out of it
# ---------------------------------------------------------------------------

def test_describe_answers_what_a_session_opens_with(org, data, capsys):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    text = org.describe()
    printed = capsys.readouterr().out
    assert text in printed

    for expected in ("samples", "S01", "stages", "synthesis", "measurements"):
        assert expected in text


def test_overview_is_the_same_thing_as_data(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    info = org.overview()
    assert info["n_samples"] == 2
    assert info["sample_ids"] == ["S01", "S02"]
    assert info["stages"] == {"synthesis": 2}
    assert "uvvis" in info["modalities"]["curve"]
    assert info["n_unresolved"] == 0


def test_overview_counts_stored_fits_separately(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
              link=True, verbose=False)
    info = org.overview()
    assert info["analyses"] == {"peak_fit (waxs1d)": 1}
    # 'fit' is an analysis product, not a technique the campaign measured.
    assert "fit" not in sum(info["modalities"].values(), [])


def test_ids_answers_without_changing_the_selection(org):
    assert org.ids() == ["S01", "S02"]
    hot = org.ids("`synthesis.conditions.temperature_C` > 90")
    assert hot == ["S02"]
    assert org.basket == [], "ids() must not commit to a selection"


def test_ids_respects_an_existing_basket(org):
    org.select(["S01"])
    assert org.ids("`synthesis.conditions.temperature_C` > 0") == ["S01"]


def test_tree_walks_the_store(org):
    text = org.tree(depth=1)
    assert "samples" in text and "project" in text


def test_subset_takes_an_explicit_list(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    child = org.subset(["S01"], name="one")

    assert child.project.sample_ids() == ["S01"]
    assert org.project.sample_ids() == ["S01", "S02"]
    assert child.measurement("S01", modality="waxs1d").resolve(child.resolver)


def test_subset_takes_a_query(org):
    child = org.subset(query="`synthesis.conditions.temperature_C` > 90")
    assert child.project.sample_ids() == ["S02"]


def test_subset_writes_nothing_until_saved(org, tmp_path):
    child = org.subset(["S01"], name="later")
    assert not child.path.exists()
    child.save()
    assert child.path.exists()
    # And the parent file is untouched by the child's save.
    assert child.path != org.path


def test_subset_is_a_deep_copy_not_a_view(org, data):
    """Analysing a subset must not write back into the parent by accident."""
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    child = org.subset(["S01"])
    child.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
                verbose=False)

    assert child["S01"].get_derived("waxs1d_peak1_center") is not None
    assert org["S01"].get_derived("waxs1d_peak1_center") is None


def test_subset_refuses_an_unknown_sample(org):
    with pytest.raises(KeyError, match="S99"):
        org.subset(["S01", "S99"])


# ---------------------------------------------------------------------------
# B: lazy loading
# ---------------------------------------------------------------------------

def test_lazy_frames_know_their_length_without_reading(org):
    frames = org.data("S01", "uvvis", lazy=True)
    assert len(frames) == 4
    assert len(frames.names) == 4
    assert "unread" in repr(frames)


def test_lazy_frames_are_indexable_and_iterable(org):
    frames = org.data("S01", "uvvis", lazy=True)

    x, y, info = frames[0]
    assert x.shape == y.shape
    assert info["index"] == 0

    assert len(list(frames)) == 4
    # A sequence, not a generator: usable twice.
    assert len(list(frames)) == 4
    assert frames[-1][2]["file"] == frames.names[-1]


def test_lazy_load_matches_the_eager_read(org):
    lazy_x, lazy_y, _ = org.data("S01", "uvvis", lazy=True).load()
    eager_x, eager_y, _ = org.data("S01", "uvvis")

    np.testing.assert_allclose(lazy_x, eager_x)
    assert lazy_y.shape == eager_y.shape
    np.testing.assert_allclose(lazy_y, eager_y)


def test_lazy_images_stack_on_load(tmp_path, records, data):
    pytest.importorskip("PIL")
    from PIL import Image

    scope = tmp_path / "scope"
    scope.mkdir()
    for index in range(3):
        Image.fromarray(np.full((16, 16), 100 + index, dtype=np.uint8)).save(
            scope / f"img_{index}.tif")

    organizer = Organizer(tmp_path / "lab.json")
    organizer.link("S01", "tem", str(scope))

    frames = organizer.data("S01", "tem", lazy=True)
    assert len(frames) == 3
    one, info = frames[1]
    assert one.shape == (16, 16)

    stack, info = frames.load()
    assert stack.shape == (3, 16, 16)
    assert info["n_frames"] == 3


def test_a_single_image_loads_as_a_plain_array(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    scope = tmp_path / "scope"
    scope.mkdir()
    Image.fromarray(np.zeros((8, 8), dtype=np.uint8)).save(scope / "only.tif")

    organizer = Organizer(tmp_path / "lab.json")
    organizer.link("S01", "tem", str(scope))
    array, info = organizer.data("S01", "tem", lazy=True).load()
    assert array.shape == (8, 8)


def test_a_volume_in_one_file_is_memory_mapped(tmp_path):
    """A tomogram must be sliceable without becoming resident."""
    volume = np.arange(4 * 5 * 6, dtype=float).reshape(4, 5, 6)
    path = tmp_path / "tomo.npy"
    np.save(path, volume)

    organizer = Organizer(tmp_path / "lab.json")
    organizer.link("S01", "tomo", str(path))

    frames = organizer.data("S01", "tomo", lazy=True)
    assert len(frames) == 4                     # planes, not files
    plane, info = frames[2]
    np.testing.assert_allclose(plane, volume[2])
    assert info["plane"] == 2

    whole, info = frames.load()
    np.testing.assert_allclose(whole, volume)


def test_lazy_and_a_frame_selector_together_are_refused(org):
    with pytest.raises(TypeError, match="index the result"):
        org.data("S01", "uvvis", lazy=True, frame=2)


# ---------------------------------------------------------------------------
# C/E: comparing an explicit list without disturbing the selection
# ---------------------------------------------------------------------------

def test_overlay_takes_an_explicit_sample_list(org, data):
    for sample in ("S01", "S02"):
        org.link(sample, "waxs1d", f"{data['xrd']}/{sample}.dat")
    org.select(["S01"])

    axes = org.overlay("waxs1d", sample_ids=["S01", "S02"])
    assert len(axes.get_lines()) == 2
    assert org.basket == ["S01"], "overlay must not change the selection"


def test_table_and_catalog_take_an_explicit_list(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    assert list(org.table(sample_ids=["S02"]).index) == ["S02"]
    assert list(org.catalog(sample_ids=["S02"]).index) == ["S02"]


# ---------------------------------------------------------------------------
# D: one fit, looked at, then the batch
# ---------------------------------------------------------------------------

def test_fit_tries_one_sample_and_stores_nothing(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    params = dict(x_range=(2.5, 3.5), n_peaks=1, background="linear")

    result = org.fit("S01", "waxs1d", **params)
    assert result.ok
    assert result.values["peak1_center"] == pytest.approx(3.0, abs=0.05)
    assert org["S01"].get_derived("waxs1d_peak1_center") is None
    assert not org.results_dir.exists()


def test_fit_and_its_picture_are_two_calls(org, data):
    import matplotlib.pyplot as plt

    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    result = org.fit("S01", "waxs1d", x_range=(2.5, 3.5), n_peaks=1)
    assert result.ok

    # Drawn where it is told: the residual strip is split off the given Axes,
    # and both panels come back.
    fig, ax = plt.subplots()
    top, bottom = org.plot_fit(result, ax=ax)
    assert top is ax and bottom.figure is fig
    plt.close(fig)


def test_fit_refuses_to_draw(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    with pytest.raises(TypeError, match="plot_fit"):
        org.fit("S01", "waxs1d", show=True, x_range=(2.5, 3.5), n_peaks=1)


def test_the_same_params_go_on_to_the_batch(org, data):
    for sample in ("S01", "S02"):
        org.link(sample, "waxs1d", f"{data['xrd']}/{sample}.dat")
    params = dict(x_range=(2.5, 3.5), n_peaks=1, background="linear")

    trial = org.fit("S01", "waxs1d", **params)
    table = org.batch("peak_fit", modality="waxs1d", verbose=False, **params)

    assert table["ok"].all()
    assert org["S01"].get_derived("waxs1d_peak1_center") == pytest.approx(
        trial.values["peak1_center"])


def test_tree_shows_unsaved_state_not_the_file_on_disk(org, data):
    """Walking the saved file would show the state before the last links."""
    org.save()
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")   # not saved

    text = org.tree(depth=3, limit=40)
    assert "waxs1d" in text, "tree() must reflect the live organiser"
    # And it leaves no scratch file behind, nor touches the real one.
    assert org.path.exists()
    assert "tmp" not in text.splitlines()[0]


def test_two_fits_of_one_analysis_do_not_overwrite_each_other(org, data):
    """Peak-fitting a spectrum and a diffraction pattern are two results."""
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")

    org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
              link=True, verbose=False)
    org.batch("peak_fit", modality="uvvis", x_range=(500, 560), n_peaks=1,
              link=True, verbose=False)

    table = org.results()
    rows = table[table["sample_id"] == "S01"]
    assert sorted(rows["modality"]) == ["uvvis", "waxs1d"]

    waxs = org.result("S01", "peak_fit", modality="waxs1d")
    uvvis = org.result("S01", "peak_fit", modality="uvvis")
    assert waxs.values["peak1_center"] == pytest.approx(3.0, abs=0.05)
    assert uvvis.values["peak1_center"] > 400
    # And the derived columns kept them apart too.
    assert org["S01"].get_derived("waxs1d_peak1_center") != \
        org["S01"].get_derived("uvvis_peak1_center")


def test_an_ambiguous_stored_result_names_the_candidates(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
              link=True, verbose=False)
    org.batch("peak_fit", modality="uvvis", x_range=(500, 560), n_peaks=1,
              link=True, verbose=False)

    with pytest.raises(KeyError, match="Narrow with modality"):
        org.result("S01", "peak_fit")


def test_asking_for_a_result_lists_what_is_actually_there(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
              link=True, verbose=False)

    with pytest.raises(KeyError, match="peak_fit of waxs1d"):
        org.result("S01", "curve_metrics")


def test_overview_separates_fits_by_the_technique_they_ran_on(org, data):
    org.link("S01", "waxs1d", f"{data['xrd']}/S01.dat")
    org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.5), n_peaks=1,
              link=True, verbose=False)
    org.batch("peak_fit", modality="uvvis", x_range=(500, 560), n_peaks=1,
              link=True, verbose=False)

    analyses = org.overview()["analyses"]
    assert "peak_fit (waxs1d)" in analyses
    assert "peak_fit (uvvis)" in analyses


# ---------------------------------------------------------------------------
# High-throughput: the same model, more of it
# ---------------------------------------------------------------------------

def test_ten_thousand_samples_stay_workable(tmp_path):
    """Keying on sample_id is not a small-campaign idea.

    Not a benchmark — a guard that nothing here is accidentally quadratic.
    """
    import time

    organizer = Organizer(tmp_path / "ht.json")
    count = 10000
    organizer.ingest(synthesis={
        f"HT{i:05d}": {"sample_id": f"HT{i:05d}",
                       "conditions": {"temperature_C": 60 + (i % 50)}}
        for i in range(count)})

    for index in range(count):
        organizer.link(f"HT{index:05d}", "uvvis",
                       f"/plates/p{index // 96:03d}/HT{index:05d}_*.csv",
                       alias=(index == 0), check=False)

    assert len(organizer.project) == count

    start = time.perf_counter()
    organizer.save()
    reopened = Organizer(tmp_path / "ht.json")
    table = reopened.table()
    hits = reopened.ids("`synthesis.conditions.temperature_C` > 100")
    elapsed = time.perf_counter() - start

    assert len(reopened.project) == count
    assert table.shape[0] == count
    assert len(hits) == 1800
    # Generous: this is about catching an O(n^2), not about timing a machine.
    assert elapsed < 60, f"save+load+table+filter took {elapsed:.1f}s"


# ---------------------------------------------------------------------------
# Relative paths travel with the organizer
# ---------------------------------------------------------------------------

def test_relative_links_ingest_and_fits_name_no_absolute_path(tmp_path,
                                                               monkeypatch):
    folder = tmp_path / "campaign"
    (folder / "xrd").mkdir(parents=True)
    q = np.linspace(2.0, 4.0, 400)
    np.savetxt(folder / "xrd" / "S01.dat",
               np.column_stack([q, 100 * np.exp(-0.5 * ((q - 3) / 0.05) ** 2) + 5]))
    (folder / "MetaData").mkdir()
    (folder / "MetaData" / "Synthesis_dict.py").write_text(
        "Synthesis_dict = {'S01': {'sample_id': 'S01', 'c': {'T': 60.0}}}\n")
    monkeypatch.chdir(tmp_path)                 # not the organizer's folder

    org = Organizer(folder / "o.json")
    org.ingest("MetaData/Synthesis_dict.py")
    org.link("S01", "waxs1d", "xrd")
    org.batch("peak_fit", modality="waxs1d", link=True, verbose=False,
              x_range=(2.5, 3.5))
    org.save()

    text = (folder / "o.json").read_text()
    assert str(tmp_path) not in text
    assert org.measurement("S01", modality="waxs1d").paths == ["xrd/S01.dat"]
    assert org.project.config.path_aliases == []


def test_a_subset_saved_elsewhere_rebases_its_relative_paths(org, data,
                                                              tmp_path):
    rel = Path("rig/diffractometer/S01.dat")
    org.link("S01", "waxs1d", rel.as_posix())          # relative to lab.json
    child = org.subset(["S01"], path=tmp_path / "sub" / "child.json")

    recorded = child.measurement("S01", modality="waxs1d").paths[0]
    assert recorded == "../rig/diffractometer/S01.dat"
    assert child.measurement("S01", modality="waxs1d").resolve(child.resolver)


def test_summary_and_repr_show_where_from_here(org, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert "Root: ." in org.summary()
    assert str(tmp_path) not in repr(org)
