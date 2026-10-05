"""Tests for the synthetic demo project.

The demo is what a new user runs first, so it has to work on a bare checkout.
It is also the only place where the true answer is known, which makes it the
one honest end-to-end check that the pipeline recovers something real rather
than merely producing numbers.
"""

import numpy as np
import pytest

from NanoOrganizer import analysis, open_project
from NanoOrganizer.demo import (
    band_centre_nm, build_demo_project, demo_truth, particle_diameter_nm,
)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo") / "DemoProject"
    build_demo_project(root, temperatures=(60.0, 80.0, 100.0), n_frames=6,
                       n_images=2, image_size=256)
    return root


def test_project_has_both_routes_in(demo):
    """Spectra arrive by glob from the metadata; images by folder convention."""
    workbench = open_project(demo)
    assert len(workbench.project) == 3
    assert set(workbench.project.modalities()) == {"uvvis", "tem"}
    assert workbench.project.groups() == ["curve", "image"]


def test_everything_resolves(demo):
    report = open_project(demo).available()
    assert report["n_unresolved"] == 0
    assert report["n_available"] == report["n_measurements"]


def test_authored_parameters_are_filterable(demo):
    workbench = open_project(demo)
    column = "synthesis.conditions.temperature_C"
    table = workbench.table()
    assert column in table.columns
    assert sorted(table[column]) == [60.0, 80.0, 100.0]


def test_one_run_is_marked_failed(demo):
    """A uniformly tidy demo teaches the wrong lesson about real data."""
    statuses = open_project(demo).table()["synthesis.status"].tolist()
    assert "error" in statuses


def test_peak_fit_recovers_the_generated_band(demo):
    workbench = open_project(demo)
    frame = workbench.batch("peak_fit", verbose=False)
    assert int(frame["ok"].sum()) == len(frame) == 3

    truth = demo_truth((60.0, 80.0, 100.0)).set_index("sample_id")
    table = workbench.table().set_index("sample_id")
    for sample_id, row in truth.iterrows():
        fitted = table.loc[sample_id, "derived.uvvis_peak1_center"]
        assert fitted == pytest.approx(row["true_band_centre_nm"], abs=1.5)


def test_particle_sizing_recovers_the_generated_diameter(demo):
    workbench = open_project(demo)
    frame = workbench.batch("particle_sizing", verbose=False)
    assert int(frame["ok"].sum()) == len(frame) == 3

    truth = demo_truth((60.0, 80.0, 100.0)).set_index("sample_id")
    table = workbench.table().set_index("sample_id")
    for sample_id, row in truth.iterrows():
        measured = table.loc[sample_id, "derived.tem_d_mean"]
        assert measured == pytest.approx(row["true_diameter_nm"], rel=0.2)


def test_micrographs_carry_a_pixel_calibration(demo):
    """Without one, sizes would come back in pixels."""
    workbench = open_project(demo)
    result = analysis.run("particle_sizing",
                          workbench.measurement("Sample000001", modality="tem"),
                          workbench.resolver)
    assert result.diagnostics["calibrated"] is True
    assert result.diagnostics["unit"] == "nm"


def test_the_control_variable_is_monotonic(demo):
    """The trend Compare is meant to show has to actually be there."""
    workbench = open_project(demo)
    workbench.batch("peak_fit", verbose=False)

    table = workbench.table().sort_values("synthesis.conditions.temperature_C")
    centres = table["derived.uvvis_peak1_center"].tolist()
    assert centres == sorted(centres)


def test_truth_matches_the_generator():
    truth = demo_truth((60.0, 100.0))
    assert truth.loc[0, "true_band_centre_nm"] == band_centre_nm(60.0)
    assert truth.loc[1, "true_diameter_nm"] == particle_diameter_nm(100.0)


def test_rebuilding_is_safe_and_repeatable(tmp_path):
    root = tmp_path / "D"
    build_demo_project(root, temperatures=(70.0,), n_frames=3, with_images=False)
    first = len(list((root / "RawSpectra").rglob("*.npy")))

    build_demo_project(root, temperatures=(70.0,), n_frames=3, with_images=False)
    assert len(list((root / "RawSpectra").rglob("*.npy"))) == first


def test_it_refuses_to_delete_a_directory_it_did_not_make(tmp_path):
    """Pointing the generator at real data must not destroy it."""
    root = tmp_path / "RealData"
    root.mkdir()
    (root / "precious.txt").write_text("do not delete")

    with pytest.raises(FileExistsError, match="not empty"):
        build_demo_project(root)
    assert (root / "precious.txt").exists()
