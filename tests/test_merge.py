"""Merging a co-worker's organiser into the master: theirs added, ours kept."""

from pathlib import Path

from pyDataOrg import Organizer


def _organiser(path: Path, records: dict) -> Organizer:
    org = Organizer(path)
    org.ingest(synthesis=records)
    return org


def test_what_only_the_other_holds_is_added_and_ours_wins(tmp_path):
    master = _organiser(tmp_path / "master" / "org.json",
                        {"S1": {"T_C": 90}, "S2": {"T_C": 80}})
    other = _organiser(tmp_path / "theirs" / "org.json",
                       {"S1": {"T_C": 95}, "S2": {"T_C": 80}, "S3": {"T_C": 70}})
    other.ingest(catalysis={"S2": {"dose_uL": 5}})
    spectra = tmp_path / "data" / "S3.csv"
    spectra.parent.mkdir()
    spectra.write_text("1,2\n")
    other.link("S3", "uvvis", str(spectra), stage="synthesis")

    report = master.merge(other)

    assert sorted(master.project.sample_ids()) == ["S1", "S2", "S3"]
    assert master.project.get_sample("S1").stages["synthesis"].params["T_C"] == 90
    assert "catalysis" in master.project.get_sample("S2").stages
    assert master.project.get_sample("S3").get_measurements(modality="uvvis")
    clash = report[report["action"] == "clash"]
    assert list(clash["sample"]) == ["S1"] and list(clash["kind"]) == ["stage"]
    added = report[report["action"] == "added"]
    assert {"S3"} <= set(added.loc[added["kind"] == "sample", "sample"])
    assert master.merge(other)["action"].eq("clash").sum() == 1     # idempotent


def test_kept_result_files_are_copied_and_relinked(tmp_path):
    master = _organiser(tmp_path / "master" / "org.json", {"S1": {"T_C": 90}})
    other = _organiser(tmp_path / "theirs" / "org.json", {"S1": {"T_C": 90}})
    fit = tmp_path / "theirs" / "results" / "S1__fit.npz"
    fit.parent.mkdir()
    fit.write_bytes(b"fit")
    other.link("S1", "fit", "results/S1__fit.npz", stage="analysis", role="peak")
    other.link("S1", "fit", str(tmp_path / "gone.npz"), stage="analysis",
               role="lost", check=False)

    report = master.merge(other, copy_to="Results")

    copied = tmp_path / "master" / "Results" / "S1__fit.npz"
    assert copied.read_bytes() == b"fit"
    linked = master.project.get_sample("S1").get_measurements(modality="fit")
    assert [m.role for m in linked] == ["peak"]
    assert linked[0].paths == ["Results/S1__fit.npz"]
    assert list(report.loc[report["action"] == "unreadable", "item"]) == [
        "S1:fit:analysis-lost"]
