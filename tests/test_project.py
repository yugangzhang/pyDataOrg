"""Tests for the sample-centric schema, metadata ingest, and the project store."""

import json
from pathlib import Path

import pytest

from NanoOrganizer.core import modality
from NanoOrganizer.core.project import Project
from NanoOrganizer.core.schema import Measurement, Sample, Stage, flatten_dict
from NanoOrganizer.ingest import choose_adapter
from NanoOrganizer.ingest.sampledict import modality_from_name

# A metadata module shaped like the ones written at the instrument: a helper
# function builds the repeated parts, and the paths point at a prefix that is
# not mounted where the tests run.
METADATA_MODULE = '''
"""Synthetic synthesis records for testing."""

REMOTE = "/instrument/share/spectra_share/SERIAL1/2026-09-21/run_a"


def _record(sample_id, ratio, batch_index, status="done"):
    return {
        "sample_id": sample_id,
        "synthesis_batch": {
            "batch_tag": "20260921_test",
            "run_id": "run_a",
            "campaign": "test_campaign",
            "status": status,
            "aborted": False,
            "started_at": "2026-09-21T15:47:33",
            "ended_at": "2026-09-21T18:33:23",
            "run_time_s": 9949.9,
            "run_record_path": f"{REMOTE}/run_record.json",
        },
        "conditions": {
            "temperature_C": ratio,
            "block_setpoint_C": 95.0,
            "hold_time_min": 40.0,
        },
        "chemical_injections": {
            "HAuCl4": {"stock_concentration_mM": 2.0, "volume_uL": 666.0},
        },
        "UV_Synthesis_data": {
            "spectrometer_serial": "SERIAL1",
            "saved_spectra": 100,
            "first_spectrum_at": "2026-09-21T15:48:39",
            "spectrum_glob": f"{REMOTE}/spec_b{batch_index:02d}_*.npy",
            "wavelength_file": f"{REMOTE}/wavelength.npy",
            "first_spectrum_file": "spec_b01_000.npy",
        },
    }


Synthesis_dict = {
    "Sample000001": _record("Sample000001", 6.0, 1),
    "Sample000002": _record("Sample000002", 2.0, 2, status="error"),
}
'''

CATALYSIS_MODULE = '''
REMOTE = "/instrument/share/spectra_share/SERIAL2/2026-09-27/run_b"

Catalysis_dict = {
    "Sample000001": {
        "sample_id": "Sample000001",
        "catalysis_batch": {
            "batch_name": "auto_test",
            "campaign": "cata_test",
            "status": "done",
        },
        "assay_protocol": {"total_volume_uL": 3000.0},
        "UV_Catalysis_data": {
            "run_id": "run_b",
            "spectrum_glob": f"{REMOTE}/auto_test_r01_*.npy",
            "wavelength_file": f"{REMOTE}/wavelength.npy",
        },
    },
}
'''


@pytest.fixture
def project(tmp_path):
    """A project with metadata, a TEM folder, and a mounted copy of the data."""
    root = tmp_path / "Project_Test"
    meta = root / "MetaData"
    meta.mkdir(parents=True)
    (meta / "Synthesis_dict_Test.py").write_text(METADATA_MODULE)
    (meta / "Catalysis_dict_Test.py").write_text(CATALYSIS_MODULE)

    tem = root / "TEMData" / "Sample000001"
    tem.mkdir(parents=True)
    for index in range(1, 4):
        (tem / f"{index}.tif").write_bytes(b"")
    (tem / "note.txt").write_text("6B-Auto_Au_6X")

    # The local stand-in for the instrument share.
    mount = tmp_path / "mount" / "spectra_share" / "SERIAL1" / "2026-09-21" / "run_a"
    mount.mkdir(parents=True)
    for index in range(3):
        (mount / f"spec_b01_{index:03d}.npy").write_bytes(b"")
    (mount / "spec_b02_000.npy").write_bytes(b"")
    (mount / "wavelength.npy").write_bytes(b"")

    proj = Project(root)
    proj.add_alias("/instrument/share", [str(tmp_path / "mount")])
    proj.ingest(meta / "Synthesis_dict_Test.py")
    proj.ingest(meta / "Catalysis_dict_Test.py")
    proj.attach_folders()
    return proj


# ---------------------------------------------------------------------------
# Modality registry
# ---------------------------------------------------------------------------

def test_shape_determines_visualisation_group():
    assert modality.get("uvvis").group == "curve"
    assert modality.get("tem").group == "image"
    assert modality.get("tomo").group == "volume"
    assert modality.get("xpcs_g2").group == "correlation"


def test_modality_aliases_resolve():
    assert modality.resolve_key("UV-Vis") == "uvvis"
    assert modality.resolve_key("saxs") == "saxs1d"
    assert modality.resolve_key("not_a_technique") is None


def test_registering_an_unknown_shape_is_rejected():
    with pytest.raises(ValueError):
        modality.register(modality.Modality(
            key="bogus", label="Bogus", domain="q", shape="hypercube"))


def test_modality_inferred_from_block_name():
    assert modality_from_name("UV_Synthesis_data") == "uvvis"
    assert modality_from_name("UV_Catalysis_data") == "uvvis"
    assert modality_from_name("TEM_data") == "tem"
    assert modality_from_name("refill_before_assay") == ""


# ---------------------------------------------------------------------------
# Flattening
# ---------------------------------------------------------------------------

def test_flatten_dict_produces_dotted_columns():
    row = flatten_dict({"a": {"b": {"c": 1}}, "d": [1, 2]})
    assert row["a.b.c"] == 1
    assert row["d"] == "1, 2"


def test_flatten_dict_stops_at_max_depth():
    deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    row = flatten_dict(deep, max_depth=2)
    assert any(isinstance(v, str) and "e" in v for v in row.values())


def test_flatten_dict_indexes_lists_of_dicts():
    row = flatten_dict({"runs": [{"id": "x"}, {"id": "y"}]})
    assert row["runs.0.id"] == "x"
    assert row["runs.1.id"] == "y"


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def test_ingest_creates_one_sample_per_key(project):
    assert project.sample_ids() == ["Sample000001", "Sample000002"]


def test_stage_label_comes_from_the_dict_name(project):
    sample = project.get_sample("Sample000001")
    assert set(sample.stages) == {"synthesis", "catalysis"}


def test_batch_provenance_is_promoted(project):
    stage = project.get_sample("Sample000001").stage("synthesis")
    assert stage.run_id == "run_a"
    assert stage.batch_tag == "20260921_test"
    assert stage.campaign == "test_campaign"
    assert stage.run_time_s == pytest.approx(9949.9)
    assert stage.ok is True


def test_run_id_is_found_outside_the_batch_block(project):
    """The catalysis schema keeps run_id with the data block, not the batch."""
    stage = project.get_sample("Sample000001").stage("catalysis")
    assert stage.run_id == "run_b"
    assert stage.batch_tag == "auto_test"


def test_failed_stage_is_flagged(project):
    stage = project.get_sample("Sample000002").stage("synthesis")
    assert stage.status == "error"
    assert stage.ok is False


def test_authored_parameters_survive_verbatim(project):
    params = project.get_sample("Sample000001").stage("synthesis").params
    assert params["conditions"]["temperature_C"] == 6.0
    assert params["chemical_injections"]["HAuCl4"]["volume_uL"] == 666.0


def test_measurement_blocks_become_measurements(project):
    sample = project.get_sample("Sample000001")
    uvvis = sample.get_measurements(modality="uvvis")
    assert {m.stage for m in uvvis} == {"synthesis", "catalysis"}
    assert uvvis[0].pattern.endswith("spec_b01_*.npy")
    assert "wavelength_file" in uvvis[0].aux


def test_bare_filenames_are_not_mistaken_for_paths(project):
    """``first_spectrum_file: 'spec_b01_000.npy'`` names a file, it does not locate one."""
    measurement = project.get_sample("Sample000001").get_measurements(
        modality="uvvis", stage="synthesis")[0]
    assert "first_spectrum_file" not in measurement.aux


def test_parameter_blocks_do_not_become_measurements(project):
    sample = project.get_sample("Sample000001")
    assert all(m.modality in {"uvvis", "tem"} for m in sample.measurements)


def test_reingest_is_idempotent(project):
    before = {s.sample_id: len(s.measurements) for s in project}
    project.reingest()
    after = {s.sample_id: len(s.measurements) for s in project}
    assert before == after


def test_adapter_is_detected_for_a_metadata_module(tmp_path):
    path = tmp_path / "Synthesis_dict.py"
    path.write_text(METADATA_MODULE)
    assert choose_adapter(path) == "sampledict"


def test_unreadable_source_is_reported(project):
    with pytest.raises(FileNotFoundError):
        project.ingest("MetaData/does_not_exist.py")


# ---------------------------------------------------------------------------
# Folder attachment
# ---------------------------------------------------------------------------

def test_folder_convention_attaches_unlinked_data(project):
    tem = project.get_sample("Sample000001").get_measurements(modality="tem")
    assert len(tem) == 1
    assert len(tem[0].paths) == 3
    assert tem[0].stage == "characterization"


def test_side_car_note_is_captured(project):
    tem = project.get_sample("Sample000001").get_measurements(modality="tem")[0]
    assert tem.meta["note"] == "6B-Auto_Au_6X"


def test_non_matching_extensions_are_skipped(project):
    tem = project.get_sample("Sample000001").get_measurements(modality="tem")[0]
    assert not any(p.endswith("note.txt") for p in tem.paths)


def test_folder_for_an_unknown_sample_creates_it(tmp_path):
    root = tmp_path / "P"
    folder = root / "SEMData" / "Sample999"
    folder.mkdir(parents=True)
    (folder / "a.tif").write_bytes(b"")

    proj = Project(root)
    proj.attach_folders()
    assert "Sample999" in proj
    assert proj.get_sample("Sample999").modalities == ["sem"]


# ---------------------------------------------------------------------------
# Path resolution through the project
# ---------------------------------------------------------------------------

def test_measurement_resolves_through_the_project_alias(project):
    measurement = project.get_sample("Sample000001").get_measurements(
        modality="uvvis", stage="synthesis")[0]
    files = measurement.resolve(project.resolver)
    assert [f.name for f in files] == [
        "spec_b01_000.npy", "spec_b01_001.npy", "spec_b01_002.npy",
    ]


def test_companion_file_resolves(project):
    measurement = project.get_sample("Sample000001").get_measurements(
        modality="uvvis", stage="synthesis")[0]
    aux = measurement.resolve_aux(project.resolver)
    assert aux["wavelength_file"].name == "wavelength.npy"


def test_unmounted_data_is_reported_not_raised(project):
    """The catalysis share is not mounted; browsing must still work."""
    measurement = project.get_sample("Sample000001").get_measurements(
        modality="uvvis", stage="catalysis")[0]
    report = measurement.availability(project.resolver)
    assert report["available"] is False
    assert report["missing"]

    summary = project.availability()
    assert summary["n_unresolved"] >= 1
    assert summary["n_available"] >= 1


# ---------------------------------------------------------------------------
# Table and filtering
# ---------------------------------------------------------------------------

def test_sample_table_has_dotted_parameter_columns(project):
    frame = project.to_dataframe()
    column = "synthesis.conditions.temperature_C"
    assert frame.loc["Sample000001", column] == 6.0
    assert frame.loc["Sample000002", column] == 2.0


def test_missing_modality_is_false_not_nan(project):
    frame = project.to_dataframe()
    assert frame["has.tem"].dtype == bool
    assert frame.loc["Sample000001", "has.tem"]
    assert not frame.loc["Sample000002", "has.tem"]


def test_measurement_table_carries_group_and_stage(project):
    frame = project.to_dataframe(level="measurement")
    tem = frame[frame["modality"] == "tem"].iloc[0]
    assert tem["group"] == "image"
    assert tem["sample_id"] == "Sample000001"


def test_filter_on_an_authored_parameter(project):
    hits = project.filter(**{
        "synthesis.conditions.temperature_C": 6.0})
    assert hits == ["Sample000001"]


def test_filter_with_a_predicate(project):
    hits = project.filter(lambda s: not s.stage("synthesis").ok)
    assert hits == ["Sample000002"]


def test_groups_present_in_the_project(project):
    assert project.groups() == ["curve", "image"]


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------

def test_derived_values_become_filterable_columns(project):
    sample = project.get_sample("Sample000001")
    sample.set_derived("k_app", 0.0123, unit="1/s", error=0.0004,
                       analysis="uvvis_kinetics",
                       source="Sample000001:uvvis:catalysis")

    frame = project.to_dataframe()
    assert frame.loc["Sample000001", "derived.k_app"] == pytest.approx(0.0123)
    assert frame.loc["Sample000001", "derived.k_app.error"] == pytest.approx(0.0004)


def test_derived_value_records_its_provenance(project):
    sample = project.get_sample("Sample000001")
    entry = sample.set_derived("lspr_nm", 523.4, analysis="peak_fit",
                               source="Sample000001:uvvis:synthesis")
    assert entry.analysis == "peak_fit"
    assert entry.computed_at
    assert sample.get_derived("lspr_nm") == pytest.approx(523.4)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_project_round_trips_through_disk(project):
    project.get_sample("Sample000001").set_derived("k_app", 0.0123, unit="1/s")
    project.save()

    reopened = Project.load(project.root)
    assert reopened.sample_ids() == project.sample_ids()

    sample = reopened.get_sample("Sample000001")
    assert sample.get_derived("k_app") == pytest.approx(0.0123)
    assert set(sample.stages) == {"synthesis", "catalysis"}
    assert len(sample.measurements) == 3
    assert sample.stage("synthesis").params[
        "conditions"]["temperature_C"] == 6.0


def test_aliases_survive_a_reopen(project):
    project.save()
    reopened = Project.load(project.root)
    measurement = reopened.get_sample("Sample000001").get_measurements(
        modality="uvvis", stage="synthesis")[0]
    assert len(measurement.resolve(reopened.resolver)) == 3


def test_metadata_sources_are_remembered(project):
    project.save()
    config = json.loads((project.root / ".nanoorganizer" / "project.json").read_text())
    recorded = [Path(s["path"]).name for s in config["metadata_sources"]]
    assert sorted(recorded) == ["Catalysis_dict_Test.py", "Synthesis_dict_Test.py"]


def test_authored_metadata_is_never_modified(project):
    """Ingest reads; it must not write back into the source module."""
    source = project.root / "MetaData" / "Synthesis_dict_Test.py"
    assert source.read_text() == METADATA_MODULE


# ---------------------------------------------------------------------------
# Schema guards
# ---------------------------------------------------------------------------

def test_measurement_id_is_stable():
    first = Measurement(sample_id="S1", modality="uvvis", stage="synthesis")
    second = Measurement(sample_id="S1", modality="UV-Vis", stage="synthesis")
    assert first.measurement_id == second.measurement_id


def test_adding_a_measurement_for_another_sample_is_rejected():
    sample = Sample(sample_id="S1")
    with pytest.raises(ValueError):
        sample.add_measurement(Measurement(sample_id="S2", modality="tem"))


def test_re_adding_a_measurement_replaces_it():
    sample = Sample(sample_id="S1")
    sample.add_measurement(Measurement(sample_id="S1", modality="tem",
                                       paths=["a.tif"]))
    sample.add_measurement(Measurement(sample_id="S1", modality="tem",
                                       paths=["a.tif", "b.tif"]))
    assert len(sample.measurements) == 1
    assert len(sample.measurements[0].paths) == 2


def test_merging_a_stage_keeps_existing_parameters():
    sample = Sample(sample_id="S1")
    sample.add_stage(Stage(stage_id="synthesis", params={"a": 1, "b": 2}))
    sample.add_stage(Stage(stage_id="synthesis", params={"b": 3, "c": 4}))
    assert sample.stage("synthesis").params == {"a": 1, "b": 3, "c": 4}


def test_a_key_with_a_space_does_not_drop_the_whole_dict(tmp_path):
    from NanoOrganizer.ingest.pydict import find_sample_dicts

    meta = tmp_path / "Catalysis_dict.py"
    meta.write_text(
        "Catalysis_dict = {\n"
        "    'Sample000001': {'k': 1},\n"
        "    'Au standard_10nm': {'k': 2},\n"
        "}\n")
    found = find_sample_dicts(meta)
    assert sorted(found["Catalysis_dict"]) == ["Au standard_10nm", "Sample000001"]


def test_a_refused_records_dict_is_reported_not_dropped_silently(tmp_path):
    from NanoOrganizer.ingest.pydict import find_sample_dicts

    meta = tmp_path / "Synthesis_dict.py"
    meta.write_text(
        "Synthesis_dict = {'Sample000001': {'k': 1}, 'a sentence, not a key!': {}}\n")
    with pytest.warns(UserWarning, match="Synthesis_dict was not read"):
        assert find_sample_dicts(meta) == {}


def test_failed_records_get_their_own_stage():
    from NanoOrganizer.ingest.pydict import stage_from_name

    assert stage_from_name("Synthesis_dict") == "synthesis"
    assert stage_from_name("Catalysis_dict_2026") == "catalysis"
    assert stage_from_name("Synthesis_failed_dict") == "synthesis_failed"
    assert stage_from_name("Catalysis_planned_dict") == "catalysis_planned"


def test_a_file_ingested_with_replace_is_the_whole_truth_for_its_stage(tmp_path):
    old = tmp_path / "Synthesis_dict_A.py"
    old.write_text("Synthesis_dict = {'S1': {'T': 90}, 'S2': {'T': 95}}\n")
    new = tmp_path / "Synthesis_dict_B.py"
    new.write_text("Synthesis_dict = {'S1': {'T': 91}}\n")
    cat = tmp_path / "Catalysis_dict.py"
    cat.write_text("Catalysis_dict = {'S2': {'k': 1}}\n")

    project = Project(tmp_path)
    project.ingest(old)
    project.ingest(cat)
    project.ingest(new, replace=True)

    assert project.get_sample("S1").stages["synthesis"].params["T"] == 91
    s2 = project.get_sample("S2")
    assert "synthesis" not in s2.stages          # left the newer snapshot
    assert "catalysis" in s2.stages              # another stage is untouched
