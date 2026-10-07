"""Tests for the multimodal demo project.

The showcase is the worked example a new user meets first, so it has to build
on a bare checkout and it has to be *true*: every technique in it is generated
from one hidden control variable, and the point of these tests is that
independent techniques recover that variable and agree with each other.

A demo whose numbers do not come back is worse than no demo, because it
teaches the pipeline is working when it is not.
"""

import numpy as np
import pytest

from NanoOrganizer import analysis, open_project
from NanoOrganizer.demo import build_showcase_project, showcase_truth
from NanoOrganizer.demo import materials as mat
from NanoOrganizer.demo import signals as sig

FRACTIONS = (0.0, 0.5, 1.0)


@pytest.fixture(scope="module")
def project_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("showcase") / "CuAuDemo"
    build_showcase_project(root, fractions=FRACTIONS, n_frames=4,
                           n_micrographs=1, image_size=320, tomo_size=40)
    return root


@pytest.fixture(scope="module")
def truth():
    return showcase_truth(FRACTIONS).set_index("sample_id")


@pytest.fixture()
def workbench(project_root):
    return open_project(project_root)


# ---------------------------------------------------------------------------
# Shape of the campaign
# ---------------------------------------------------------------------------

def test_all_four_visualisation_groups_are_present(workbench):
    """A demo that only exercises 1D curves would not test the dispatch."""
    assert workbench.project.groups() == ["curve", "image", "volume",
                                          "correlation"]


def test_it_covers_the_techniques_it_claims_to(workbench):
    present = set(workbench.project.modalities())
    expected = {"uvvis", "ir", "raman", "xps", "xas", "eds", "saxs1d",
                "waxs1d", "saxs2d", "dls", "xpcs_g2", "ec", "dos",
                "tem", "sem", "tomo"}
    assert expected <= present


def test_four_stages_each_from_its_own_metadata_file(workbench):
    stages = {s for sample in workbench.project.samples.values()
              for s in sample.stages}
    assert stages == {"synthesis", "characterization", "testing", "computation"}


def test_both_routes_in_are_used(workbench):
    """Metadata declares most measurements; some arrive as a bare folder."""
    sample = workbench.project.get_sample("CuAu01")
    declared = sample.get_measurements(modality="uvvis")[0]
    by_folder = sample.get_measurements(modality="tem")[0]
    assert declared.pattern and not declared.paths
    assert by_folder.paths


def test_the_measurement_matrix_is_sparse(workbench):
    """Beamtime-limited techniques are not on every sample, which is what
    availability() exists to show."""
    with_xas = [s for s in workbench.project.sample_ids()
                if workbench.project.get_sample(s).get_measurements(modality="xas")]
    assert with_xas == ["CuAu01", "CuAu03"]
    assert len(with_xas) < len(FRACTIONS)


def test_the_failed_synthesis_has_a_row_but_no_data(workbench):
    failed = workbench.project.get_sample(f"CuAu{len(FRACTIONS) + 1:02d}")
    assert failed is not None
    assert failed.stages["synthesis"].status == "error"
    assert failed.measurements == []


def test_everything_that_is_declared_resolves(workbench):
    report = workbench.available()
    assert report["n_unresolved"] == 0
    assert report["n_available"] == report["n_measurements"]


def test_authored_parameters_are_filterable(workbench, truth):
    table = workbench.table().set_index("sample_id")
    column = "synthesis.composition.nominal_x_Au"
    assert column in table.columns
    assert table.loc[truth.index, column].tolist() == list(FRACTIONS)


# ---------------------------------------------------------------------------
# Does the pipeline recover the hidden variable?
# ---------------------------------------------------------------------------

def test_uvvis_recovers_the_plasmon_position(workbench, truth):
    frame = workbench.batch("peak_fit", modality="uvvis", verbose=False,
                            x_range=(470.0, 800.0), background="linear")
    assert int(frame["ok"].sum()) == len(FRACTIONS)

    fitted = workbench.table().set_index("sample_id")["derived.uvvis_peak1_center"]
    for sample_id, row in truth.iterrows():
        assert fitted[sample_id] == pytest.approx(row["true_lspr_nm"], abs=2.0)


def test_waxs_recovers_the_lattice_parameter(workbench, truth):
    """Vegard's law run backwards: the (111) position measures composition."""
    frame = workbench.batch("peak_fit", modality="waxs1d", verbose=False,
                            x_range=(2.5, 3.6), n_peaks=2,
                            shape="pseudo_voigt", background="linear")
    assert int(frame["ok"].sum()) == len(FRACTIONS)

    q111 = workbench.table().set_index("sample_id")["derived.waxs1d_peak1_center"]
    for sample_id, row in truth.iterrows():
        lattice = 2.0 * np.pi * np.sqrt(3.0) / q111[sample_id]
        assert lattice == pytest.approx(row["true_lattice_A"], abs=0.01)


def test_eds_recovers_the_bulk_composition(workbench, truth):
    for prefix, lo, hi in (("cu_", 7.7, 8.4), ("au_", 9.4, 10.0)):
        workbench.batch("curve_metrics", modality="eds", verbose=False,
                        prefix=f"eds_{prefix}", x_min=lo, x_max=hi)

    table = workbench.table().set_index("sample_id")
    gold = table["derived.eds_au_area"] / sig.EDS_K_FACTOR_AU_CU
    copper = table["derived.eds_cu_area"]
    recovered = gold / (gold + copper)
    for sample_id, row in truth.iterrows():
        assert recovered[sample_id] == pytest.approx(row["x_Au"], abs=0.05)


def test_tem_recovers_the_particle_diameter(workbench, truth):
    frame = workbench.batch("particle_sizing", modality="tem", verbose=False)
    assert int(frame["ok"].sum()) == len(FRACTIONS)

    measured = workbench.table().set_index("sample_id")["derived.tem_d_mean"]
    for sample_id, row in truth.iterrows():
        assert measured[sample_id] == pytest.approx(row["true_diameter_nm"],
                                                    rel=0.25)


def test_xpcs_and_dls_see_the_same_particles_by_different_routes(workbench):
    """Both measure diffusion; the numbers must be consistent, not equal."""
    workbench.batch("curve_metrics", modality="xpcs_g2", verbose=False,
                    threshold=1.14, subtract_baseline=False)
    table = workbench.table().set_index("sample_id")
    half_life = table.loc["CuAu01", "derived.xpcs_g2_x_at_threshold"]

    rate = np.log(2.0) / (2.0 * half_life)
    diffusion = rate / sig.XPCS_Q_INV_A ** 2 * 1e-20        # m² s⁻¹
    diameter_nm = (1.380649e-23 * 298.0
                   / (3.0 * np.pi * sig.XPCS_VISCOSITY_Pa_s * diffusion)) * 1e9
    assert diameter_nm == pytest.approx(mat.aggregate_nm(FRACTIONS[0]), rel=0.1)


def test_dft_density_of_states_has_the_advertised_centroid(workbench, truth):
    workbench.batch("curve_metrics", modality="dos", verbose=False,
                    x_min=-8.0, x_max=0.5)
    centroid = workbench.table().set_index("sample_id")["derived.dos_x_centroid"]
    for sample_id, row in truth.iterrows():
        assert centroid[sample_id] == pytest.approx(row["true_d_band_eV"],
                                                    abs=0.25)


def test_two_modalities_do_not_overwrite_each_others_columns(workbench):
    """peak_fit applies to every curve, so its columns carry the modality."""
    workbench.batch("peak_fit", modality="uvvis", verbose=False,
                    x_range=(470.0, 800.0), background="linear")
    workbench.batch("peak_fit", modality="waxs1d", verbose=False,
                    x_range=(2.5, 3.6), n_peaks=2, background="linear")

    table = workbench.table()
    assert "derived.uvvis_peak1_center" in table.columns
    assert "derived.waxs1d_peak1_center" in table.columns
    assert "derived.peak1_center" not in table.columns


# ---------------------------------------------------------------------------
# Internal consistency of the generator
# ---------------------------------------------------------------------------

def test_faradaic_efficiencies_sum_to_one_hundred():
    """A product distribution that does not is not a product distribution."""
    for x in np.linspace(0.0, 1.0, 11):
        for potential in (-0.5, -0.8, -1.0, -1.3):
            total = sum(mat.faradaic_efficiency(float(x), potential).values())
            assert total == pytest.approx(100.0)


def test_the_co_partial_current_really_is_a_volcano():
    """The Sabatier maximum is the whole point of the structure-property story."""
    fractions = np.linspace(0.0, 1.0, 21)
    current = np.array([mat.co_partial_current(float(x)) for x in fractions])
    peak = int(np.argmax(current))
    assert 0 < peak < len(fractions) - 1
    assert current[peak] > current[0] and current[peak] > current[-1]


def test_gold_segregates_to_the_surface():
    """XPS and EDS are meant to disagree here, in one direction."""
    for x in (0.1, 0.25, 0.5, 0.75, 0.9):
        assert mat.surface_au_fraction(x) > x


def test_truth_table_matches_the_generator():
    row = showcase_truth((0.4,)).iloc[0]
    assert row["true_lattice_A"] == mat.lattice_parameter_A(0.4)
    assert row["true_lspr_nm"] == mat.lspr_nm(0.4)
    assert row["sample_id"] == "CuAu01"


# ---------------------------------------------------------------------------
# Files on disk
# ---------------------------------------------------------------------------

def test_micrographs_carry_a_pixel_calibration(workbench):
    result = analysis.run("particle_sizing",
                          workbench.measurement("CuAu01", modality="tem"),
                          workbench.resolver)
    assert result.diagnostics["calibrated"] is True
    assert result.diagnostics["unit"] == "nm"


def test_the_tem_banner_is_cropped_off(workbench):
    """It is below the image; nothing downstream should ever see those rows."""
    from NanoOrganizer.analysis.reading import load_image

    _, info = load_image(workbench.measurement("CuAu01", modality="tem"),
                         workbench.resolver)
    assert info["shape"][0] == info["shape"][1]


def test_sem_contrast_polarity_is_detected_not_assumed(workbench):
    """SEM particles are bright, TEM particles are dark, and the user should
    not have to remember which."""
    from NanoOrganizer.analysis.imaging import read_micrograph, segment_particles

    for modality, expected_dark in (("tem", True), ("sem", False)):
        path = workbench.measurement("CuAu01", modality=modality).resolve(
            workbench.resolver)[0]
        image, _, _ = read_micrograph(path)
        _, info = segment_particles(image)
        assert info["dark_particles"] is expected_dark, modality


def test_the_tomogram_is_a_volume(workbench):
    from NanoOrganizer.analysis.reading import load_volume

    volume, info = load_volume(workbench.measurement("CuAu01", modality="tomo"),
                               workbench.resolver)
    assert volume.ndim == 3 and len(set(volume.shape)) == 1


def test_every_measurement_can_be_read_by_its_group(workbench):
    """The viewer dispatches on group, so every measurement has to survive the
    reader for its own group — in one of fifteen file layouts."""
    from NanoOrganizer.analysis.reading import (
        load_curve_set, load_image, load_volume,
    )

    readers = {"curve": load_curve_set, "correlation": load_curve_set,
               "image": load_image, "volume": load_volume}
    failures = []
    for measurement in workbench.project.measurements():
        try:
            readers[measurement.group](measurement, workbench.resolver)
        except Exception as exc:
            failures.append(f"{measurement.measurement_id}: "
                            f"{type(exc).__name__}: {exc}")
    assert not failures, failures


def test_one_electrochemistry_measurement_holds_every_product(workbench):
    """Faradaic efficiencies arrive as one file per product, so the viewer
    gets several curves on one axis without any special case."""
    from NanoOrganizer.analysis.reading import load_curve_set

    measurement = workbench.measurement("CuAu01", modality="ec", role="co2-rr-fe")
    _, values, info = load_curve_set(measurement, workbench.resolver)
    assert values.shape[0] == len(mat.PRODUCTS)
    assert any("FE_CO.dat" in label for label in info["labels"])


def test_rebuilding_is_safe_and_repeatable(tmp_path):
    root = tmp_path / "D"
    for _ in range(2):
        build_showcase_project(root, fractions=(0.3,), n_frames=2,
                               with_images=False, with_tomography=False)
    assert len(list((root / "RawSpectra").rglob("uvvis_*.npy"))) == 2


def test_it_refuses_to_delete_a_directory_it_did_not_make(tmp_path):
    root = tmp_path / "RealData"
    root.mkdir()
    (root / "precious.txt").write_text("do not delete")

    with pytest.raises(FileExistsError, match="not empty"):
        build_showcase_project(root)
    assert (root / "precious.txt").exists()


def test_it_builds_without_pillow(tmp_path):
    """A minimal install should get a project without micrographs, not an
    error."""
    root = build_showcase_project(tmp_path / "NoImages", fractions=(0.2, 0.8),
                                  n_frames=2, with_images=False,
                                  with_tomography=False)
    workbench = open_project(root)
    assert "uvvis" in workbench.project.modalities()
    assert "tem" not in workbench.project.modalities()


# ---------------------------------------------------------------------------
# The workflow route: ingest the four dicts, link the four bare folders by hand
# ---------------------------------------------------------------------------

def test_inverting_vegard_returns_the_composition():
    for x in (0.0, 0.3, 1.0):
        q111 = 2 * np.pi * np.sqrt(3) / mat.lattice_parameter_A(x)
        assert mat.fraction_from_lattice(mat.lattice_from_q(q111)) == \
            pytest.approx(x, abs=1e-12)
    with pytest.raises(ValueError, match="positive"):
        mat.lattice_from_q(0.0)


def test_line_intensities_give_the_composition_after_their_factors():
    # 3 parts gold to 1 part copper, with the gold line read 0.85x too weak.
    assert mat.fraction_from_signals(3 * 0.85, 1.0, gold_factor=0.85) == \
        pytest.approx(0.75)
    assert mat.fraction_from_signals(np.array([0.0, 1.0]),
                                     np.array([1.0, 0.0])).tolist() == [0.0, 1.0]


def test_the_hand_built_organizer_matches_the_attached_project(project_root,
                                                               tmp_path):
    from NanoOrganizer import Organizer

    org = Organizer(tmp_path / "cuau.json")
    for stage in ("Synthesis", "Characterization", "Testing", "Computation"):
        org.ingest(project_root / "MetaData" / f"{stage}_dict.py")
    folders = {"tem": "TEMData", "sem": "SEMData", "dls": "DLSData",
               "tomo": "TomoData"}
    for sample in org.ids():
        for modality, folder in folders.items():
            source = project_root / folder / sample
            if source.is_dir():
                org.link(sample, modality, str(source), stage="characterization")

    attached = open_project(project_root)
    assert (org.catalog(counts=True).sort_index(axis=1)
            .equals(attached.catalog(counts=True).sort_index(axis=1)))


def test_the_campaign_command_writes_data_and_answer_key(tmp_path, monkeypatch):
    from NanoOrganizer.demo.__main__ import main

    monkeypatch.setenv("NANOORGANIZER_DEMO_ROOT", str(tmp_path))
    assert main(["--campaign", "--no-images"]) == 0
    assert (tmp_path / "CuAu" / "Campaign" / "MetaData" /
            "Synthesis_dict.py").exists()
    assert (tmp_path / "CuAu" / "truth.csv").exists()
    assert not (tmp_path / "CuAu" / "cuau.json").exists()   # building is yours


def test_ingesting_a_metadata_module_writes_nothing_beside_it(tmp_path):
    from NanoOrganizer import Organizer

    meta = tmp_path / "MetaData"
    meta.mkdir()
    (meta / "Synthesis_dict.py").write_text(
        "Synthesis_dict = {'S1': {'sample_id': 'S1', 'c': {'T': 1.0}}}\n")
    Organizer(tmp_path / "o.json").ingest(meta / "Synthesis_dict.py")
    assert sorted(p.name for p in meta.iterdir()) == ["Synthesis_dict.py"]
