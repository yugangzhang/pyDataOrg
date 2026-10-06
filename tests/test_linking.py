"""Tests for building an organiser by linking, and for drawing what it links.

The case under test is the one the folder conventions do not cover: data that
already exists somewhere else and is not going to move.  What must hold is
that linking it records where it is *without rewriting anything*, that the
store survives a round trip, and that a measurement can then be drawn and
analysed through the same calls as one that arrived by ingest.
"""

from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt                                    # noqa: E402

from NanoOrganizer import new_organizer, open_project               # noqa: E402
from NanoOrganizer.analysis import frames as _frames                # noqa: E402
from NanoOrganizer.core import linking                              # noqa: E402
from NanoOrganizer.demo import build_showcase_project               # noqa: E402
from NanoOrganizer.viz import show                                  # noqa: E402

FRACTIONS = (0.0, 0.5, 1.0)


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    """A generated campaign, used here only as *data that exists somewhere*."""
    root = tmp_path_factory.mktemp("linksource") / "CuAuDemo"
    build_showcase_project(root, fractions=FRACTIONS, n_frames=4,
                           n_micrographs=1, image_size=256, tomo_size=32)
    return root


@pytest.fixture()
def organizer(tmp_path, data_root):
    """An organiser whose store is nowhere near the data it links."""
    wb = new_organizer(tmp_path / "Study", name="linked study")
    for index in range(1, len(FRACTIONS) + 1):
        sample = f"CuAu{index:02d}"
        wb.link(sample, "uvvis",
                f"{data_root}/RawSpectra/uvvis_runs/uvvis_b{index:02d}_*.npy",
                stage="synthesis",
                aux={"wavelength_file":
                     f"{data_root}/RawSpectra/uvvis_runs/axis_wavelength.npy"})
        wb.link(sample, "waxs1d", f"{data_root}/Scattering/{sample}/waxs_1d.dat")
        wb.link(sample, "tem", f"{data_root}/TEMData/{sample}")
        wb.set_params(sample, au_fraction=FRACTIONS[index - 1])
    return wb


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ---------------------------------------------------------------------------
# Interpreting a source
# ---------------------------------------------------------------------------

def test_a_glob_is_kept_live_and_a_directory_is_listed(tmp_path, data_root):
    """The two forms mean different things and must not be conflated."""
    wb = new_organizer(tmp_path / "Study")

    live = wb.link("A", "uvvis",
                   f"{data_root}/RawSpectra/uvvis_runs/uvvis_b01_*.npy")
    assert live.pattern and not live.paths

    listed = wb.link("B", "tem", f"{data_root}/TEMData/CuAu01")
    assert listed.paths and not listed.pattern
    assert all(p.endswith(".tif") for p in listed.paths)


def test_a_directory_listing_honours_the_modality_extensions(tmp_path, data_root):
    """``note.txt`` sits beside the micrographs and is not a micrograph."""
    wb = new_organizer(tmp_path / "Study")
    measurement = wb.link("A", "tem", f"{data_root}/TEMData/CuAu01")
    assert not any("note.txt" in p for p in measurement.paths)


def test_extensions_can_be_widened(tmp_path):
    """A folder of .dat files joins a modality that never declared .dat."""
    folder = tmp_path / "raw"
    folder.mkdir()
    (folder / "scan.odd").write_text("1 2\n3 4\n")

    wb = new_organizer(tmp_path / "Study")
    with pytest.raises(FileNotFoundError, match="extension"):
        wb.link("A", "uvvis", str(folder))

    measurement = wb.link("A", "uvvis", str(folder), extensions=[".odd"])
    assert len(measurement.paths) == 1


def test_link_folder_records_a_pattern_not_a_snapshot(tmp_path, data_root):
    """A running experiment writes frames after the link; they must appear."""
    folder = tmp_path / "live"
    folder.mkdir()
    (folder / "a.dat").write_text("1 2\n")

    wb = new_organizer(tmp_path / "Study")
    measurement = wb.link_folder("A", "waxs1d", folder, pattern="*.dat")
    assert len(measurement.resolve(wb.resolver)) == 1

    (folder / "b.dat").write_text("3 4\n")
    assert len(measurement.resolve(wb.resolver)) == 2


def test_an_unknown_modality_says_what_is_available(tmp_path):
    wb = new_organizer(tmp_path / "Study")
    with pytest.raises(KeyError, match="uvvis"):
        wb.link("A", "uv_vis_spectra", "/nowhere/*.csv")


def test_two_globs_in_one_measurement_are_refused(tmp_path):
    """One measurement holds one pattern; silently dropping one would lie."""
    wb = new_organizer(tmp_path / "Study")
    with pytest.raises(ValueError, match="one glob"):
        wb.link("A", "uvvis", ["/a/*.csv", "/b/*.csv"])


# ---------------------------------------------------------------------------
# Paths and portability
# ---------------------------------------------------------------------------

def test_paths_are_recorded_exactly_as_given(organizer, data_root):
    """A store that has been rewritten only works on the machine that wrote it."""
    measurement = organizer.measurement("CuAu01", modality="waxs1d")
    assert measurement.paths == [f"{data_root}/Scattering/CuAu01/waxs_1d.dat"]


def test_linking_registers_the_mount_as_an_alias(organizer):
    """One line to edit on the next machine, rather than every record."""
    prefixes = [a.prefix for a in organizer.project.config.path_aliases]
    assert prefixes, "linking recorded no alias"
    assert all(a.candidates for a in organizer.project.config.path_aliases)


def test_the_alias_makes_a_moved_tree_resolve(tmp_path, data_root):
    """The portability claim, tested the way it would actually be used."""
    recorded = "/instrument/that/is/not/mounted"
    wb = new_organizer(tmp_path / "Study")
    wb.link("A", "waxs1d", f"{recorded}/CuAu01/waxs_1d.dat")

    assert wb.project.availability()["n_unresolved"] == 1

    wb.project.add_alias(recorded, [f"{data_root}/Scattering"])
    assert wb.project.availability()["n_unresolved"] == 0


def test_mount_prefix_stops_at_the_mount_point():
    assert linking.mount_prefix("/proc/self/status") == "/proc"
    assert linking.mount_prefix("relative/path.csv") == ""


def test_linking_the_same_thing_twice_replaces_rather_than_duplicates(
        tmp_path, data_root):
    """Re-running a setup script must be safe."""
    wb = new_organizer(tmp_path / "Study")
    for _ in range(3):
        wb.link("A", "waxs1d", f"{data_root}/Scattering/CuAu01/waxs_1d.dat")
    assert len(wb["A"].measurements) == 1

    wb.link("A", "waxs1d", f"{data_root}/Scattering/CuAu02/waxs_1d.dat",
            role="repeat")
    assert len(wb["A"].measurements) == 2


# ---------------------------------------------------------------------------
# Bulk forms
# ---------------------------------------------------------------------------

def test_link_many_takes_a_nested_dict(tmp_path, data_root):
    wb = new_organizer(tmp_path / "Study")
    wb.link_many({
        "CuAu01": {"waxs1d": f"{data_root}/Scattering/CuAu01/waxs_1d.dat",
                   "tem": {"source": f"{data_root}/TEMData/CuAu01", "kV": 200}},
        "CuAu02": {"waxs1d": f"{data_root}/Scattering/CuAu02/waxs_1d.dat"},
    }, stage="characterization")

    assert sorted(wb.project.sample_ids()) == ["CuAu01", "CuAu02"]
    assert wb.measurement("CuAu01", modality="tem").meta["kV"] == 200


def test_link_table_takes_a_dataframe_and_keeps_extra_columns_as_metadata(
        tmp_path, data_root):
    pandas = pytest.importorskip("pandas")
    wb = new_organizer(tmp_path / "Study")
    wb.link_table(pandas.DataFrame([
        {"sample_id": "CuAu01", "modality": "waxs1d",
         "source": f"{data_root}/Scattering/CuAu01/waxs_1d.dat",
         "stage": "characterization", "operator": "RH"},
    ]))
    measurement = wb.measurement("CuAu01", modality="waxs1d")
    assert measurement.meta["operator"] == "RH"
    assert measurement.meta["linked"] is True


def test_link_table_names_the_row_it_could_not_read(tmp_path):
    wb = new_organizer(tmp_path / "Study")
    with pytest.raises(KeyError, match="row 0"):
        wb.link_table([{"modality": "uvvis", "source": "/a/*.csv"}])


def test_unlink_removes_only_what_matches(organizer):
    dropped = organizer.unlink("CuAu01", modality="tem")
    assert dropped == ["CuAu01:tem:characterization"]
    assert "tem" not in organizer["CuAu01"].modalities
    assert "waxs1d" in organizer["CuAu01"].modalities


# ---------------------------------------------------------------------------
# Parameters make the links filterable
# ---------------------------------------------------------------------------

def test_set_params_becomes_a_filterable_column(organizer):
    assert organizer.filter("`synthesis.au_fraction` > 0.4") == ["CuAu02",
                                                                 "CuAu03"]


def test_set_params_merges_and_promotes_stage_fields(organizer):
    organizer.set_params("CuAu01", temperature_C=90, status="done")
    stage = organizer["CuAu01"].stage("synthesis")
    assert stage.status == "done"
    assert stage.params["au_fraction"] == 0.0
    assert stage.params["temperature_C"] == 90


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------

def test_a_linked_organizer_survives_save_and_reload(organizer, tmp_path):
    organizer.save()
    reloaded = open_project(organizer.project.root, ingest=False, attach=False)

    assert reloaded.project.sample_ids() == organizer.project.sample_ids()
    assert reloaded.project.modalities() == organizer.project.modalities()
    assert reloaded.project.availability()["n_unresolved"] == 0
    # The data is still where it always was, not copied into the store.
    assert not (organizer.project.root / "TEMData").exists()


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------

def test_catalog_is_a_sample_by_technique_matrix(organizer):
    table = organizer.catalog()
    assert list(table.index) == ["CuAu01", "CuAu02", "CuAu03"]
    assert set(table.columns) == {"uvvis", "waxs1d", "tem"}
    assert table.loc["CuAu01", "uvvis"]

    counted = organizer.catalog(counts=True)
    assert counted.loc["CuAu01", "uvvis"] >= 1


def test_catalog_shows_the_gaps(organizer, data_root):
    organizer.link("CuAu01", "tomo", f"{data_root}/TomoData/CuAu01/tomogram.npy")
    table = organizer.catalog()
    assert table.loc["CuAu01", "tomo"]
    assert not table.loc["CuAu02", "tomo"]


# ---------------------------------------------------------------------------
# Reading and drawing by sample and technique
# ---------------------------------------------------------------------------

def test_data_returns_arrays_shaped_by_group(organizer):
    x, matrix, info = organizer.data("CuAu01", "uvvis")
    assert matrix.ndim == 2 and matrix.shape[1] == x.size
    assert info["t_s"] is not None

    array, _ = organizer.data("CuAu01", "tem")
    assert array.ndim == 2


def test_a_single_frame_still_comes_back_two_dimensional(organizer):
    """So a caller never has to branch on how many curves it asked for."""
    _, matrix, _ = organizer.data("CuAu01", "uvvis", frame=0)
    assert matrix.shape[0] == 1


def test_selecting_by_time_takes_the_nearest_frame(organizer):
    table = organizer.frames("CuAu01", "uvvis")
    recorded = sorted(t for t in table["t_s"] if np.isfinite(t))
    assert recorded, "the demo filenames carry a clock"

    wanted = recorded[1] + 3.0
    _, matrix, info = organizer.data("CuAu01", "uvvis", t=wanted)
    assert matrix.shape[0] == 1
    assert f"{recorded[1]:.0f}" in info["labels"][0]


def test_frames_lists_every_file_even_unparsed_ones(organizer):
    table = organizer.frames("CuAu01", "tem")
    assert len(table) == len(organizer.measurement("CuAu01", modality="tem").paths)
    assert set(["index", "file", "t_s", "T_c"]).issubset(table.columns)


def test_pick_frame_explains_an_impossible_request():
    rows = [{"index": 0, "file": "a.tif", "t_s": float("nan"),
             "T_c": float("nan"), "batch": "", "scan": -1, "kind": ""}]
    with pytest.raises(KeyError, match="no frame carries a time"):
        _frames.pick_frame(rows, t=10)


def test_plot_dispatches_on_group_not_technique(organizer, data_root):
    organizer.link("CuAu01", "tomo", f"{data_root}/TomoData/CuAu01/tomogram.npy")

    for modality in ("uvvis", "waxs1d", "tem", "tomo"):
        axes = organizer.plot("CuAu01", modality)
        assert hasattr(axes, "figure"), f"{modality} did not draw an Axes"


def test_interactive_returns_a_plotly_figure(organizer):
    pytest.importorskip("plotly")
    figure = organizer.plot("CuAu01", "uvvis", engine="interactive")
    assert figure.__class__.__name__ == "Figure"


def test_an_unknown_engine_is_refused(organizer):
    with pytest.raises(ValueError, match="engine"):
        organizer.plot("CuAu01", "uvvis", engine="svg")


def test_overlay_draws_one_curve_per_sample(organizer):
    axes = organizer.overlay("waxs1d")
    assert len(axes.get_lines()) == 3


def test_overlay_skips_what_cannot_be_read_and_says_so(organizer, capsys):
    organizer.link("CuAu04", "waxs1d", "/not/mounted/waxs_1d.dat")
    axes = organizer.overlay("waxs1d")
    assert len(axes.get_lines()) == 3
    assert "skipped 1" in capsys.readouterr().out


def test_an_ambiguous_request_names_the_candidates(organizer, data_root):
    organizer.link("CuAu01", "waxs1d",
                   f"{data_root}/Scattering/CuAu01/waxs_1d.dat", role="repeat")
    with pytest.raises(KeyError, match="Narrow with"):
        organizer.plot("CuAu01", "waxs1d")
    assert organizer.plot("CuAu01", "waxs1d", role="repeat") is not None


def test_analysis_runs_on_linked_data_like_any_other(organizer):
    table = organizer.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.6),
                            n_peaks=2, background="linear", verbose=False)
    assert table["ok"].all()
    assert organizer["CuAu01"].get_derived("waxs1d_peak1_center") > 0


def test_show_module_is_reachable_without_streamlit(organizer):
    """The GUI's dispatch is library code, so a notebook gets it too."""
    measurement = organizer.measurement("CuAu01", modality="uvvis")
    assert show.figure(measurement, organizer.resolver) is not None


def test_data_refuses_a_selector_it_cannot_honour(organizer):
    """Silently ignoring a keyword is the kind of thing that costs a day."""
    with pytest.raises(TypeError, match="frame="):
        organizer.data("CuAu01", "tem", reduce="mean")


def test_unlink_with_no_filter_drops_the_whole_sample(organizer):
    dropped = organizer.unlink("CuAu02")
    assert len(dropped) == 3
    assert organizer["CuAu02"].measurements == []


# ---------------------------------------------------------------------------
# Export, and the round trip back in
# ---------------------------------------------------------------------------

def test_links_table_round_trips_exactly(organizer, tmp_path):
    """Export, edit in a spreadsheet, re-import — the claim worth testing."""
    table = organizer.links_table()
    assert set(["sample_id", "modality", "source", "stage"]).issubset(
        table.columns)

    path = tmp_path / "links.csv"
    table.to_csv(path, index=False)

    fresh = new_organizer(tmp_path / "Reimported")
    fresh.link_table(path)

    def signature(wb):
        return {m.measurement_id: (tuple(m.paths), m.pattern, m.aux,
                                   dict(m.meta))
                for m in wb.project.measurements()}

    assert signature(fresh) == signature(organizer)


def test_a_folder_link_exports_as_its_folder(tmp_path):
    """The short form, so a hand-edit stays readable."""
    folder = tmp_path / "scope"
    folder.mkdir()
    for name in ("a.dat", "b.dat"):
        (folder / name).write_text("1 2\n")

    wb = new_organizer(tmp_path / "Study")
    wb.link("A", "waxs1d", str(folder))
    assert len(wb.measurement("A", modality="waxs1d").paths) == 2

    row = wb.project.links_table()[0]
    assert row["source"] == str(folder)


def test_a_partial_folder_exports_as_a_list_not_the_folder(tmp_path):
    """Re-importing must never quietly link a *different* set of files."""
    folder = tmp_path / "scope"
    folder.mkdir()
    for name in ("a.dat", "b.dat", "c.dat"):
        (folder / name).write_text("1 2\n")

    wb = new_organizer(tmp_path / "Study")
    wb.link("A", "waxs1d", [str(folder / "a.dat"), str(folder / "c.dat")])

    row = wb.project.links_table()[0]
    assert row["source"] != str(folder)
    assert linking.SEP in row["source"]

    fresh = new_organizer(tmp_path / "Reimported")
    fresh.link_table([row])
    assert fresh.measurement("A", modality="waxs1d").paths == \
        wb.measurement("A", modality="waxs1d").paths


def test_a_semicolon_list_is_split_on_import(tmp_path, data_root):
    wb = new_organizer(tmp_path / "Study")
    both = ";".join([f"{data_root}/Scattering/CuAu01/waxs_1d.dat",
                     f"{data_root}/Scattering/CuAu02/waxs_1d.dat"])
    wb.link_table([{"sample_id": "A", "modality": "waxs1d", "source": both}])
    assert len(wb.measurement("A", modality="waxs1d").paths) == 2


def test_aux_survives_the_table_as_json(organizer, tmp_path):
    rows = organizer.project.links_table()
    uvvis = next(r for r in rows if r["modality"] == "uvvis")
    assert "wavelength_file" in uvvis["aux"]

    fresh = new_organizer(tmp_path / "Reimported2")
    fresh.link_table(rows)
    assert fresh.measurement("CuAu01", modality="uvvis").aux == \
        organizer.measurement("CuAu01", modality="uvvis").aux


def test_remove_sample_forgets_it_and_clears_it_from_the_basket(organizer):
    organizer.select(["CuAu01", "CuAu02"])
    assert organizer.remove_sample("CuAu01")
    assert "CuAu01" not in organizer.project.sample_ids()
    assert organizer.basket == ["CuAu02"]
    assert not organizer.remove_sample("CuAu01")


def test_add_sample_takes_parameters_and_needs_no_data(organizer):
    """A synthesis that failed is a result; leaving it out biases the rest."""
    organizer.add_sample("CuAu09", status="error", error="precipitated")
    sample = organizer["CuAu09"]
    assert sample.measurements == []
    assert sample.stage("synthesis").status == "error"
    assert "CuAu09" in organizer.table(all_samples=True).index
