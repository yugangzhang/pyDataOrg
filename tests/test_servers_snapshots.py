"""Machines (servers) and dated record snapshots."""

import subprocess

import pytest

from pyDataOrg import servers
from pyDataOrg.snapshots import (
    FileSource, GitSource, compare_records, latest_snapshots, plan_sync,
    read_records, snapshots, write_snapshots,
)


# ---------------------------------------------------------------------------
# servers
# ---------------------------------------------------------------------------

def test_a_server_swaps_the_longest_matching_prefix():
    here = servers.Server("ws", {"/instrument": "/mnt/i",
                                 "/instrument/share": "/mnt/share"})
    assert here.local("/instrument/share/a/*.csv") == "/mnt/share/a/*.csv"
    assert here.local("/instrument/b.dat") == "/mnt/i/b.dat"
    assert here.local("/instrumental/b.dat") == "/instrumental/b.dat"
    assert here.local("/elsewhere/x") == "/elsewhere/x"


def test_aliases_leave_out_prefixes_that_do_not_move():
    here = servers.Server("ws", {"/a": "/a/", "/b": "/mnt/b"})
    assert here.aliases() == {"/b": "/mnt/b"}


def test_auto_picks_the_mounted_server(tmp_path, monkeypatch):
    monkeypatch.setattr(servers, "SERVERS",
                        {servers.RECORDED: servers.SERVERS[servers.RECORDED]})
    servers.register_server(servers.Server("gone", {"/x": "/no/such/place"}))
    servers.register_server(servers.Server("here", {"/x": str(tmp_path)}))
    assert servers.server("auto").name == "here"
    assert servers.server().name == servers.RECORDED
    with pytest.raises(KeyError, match="unknown server"):
        servers.server("nope")
    with pytest.raises(ValueError, match="reserved"):
        servers.register_server(servers.Server("auto"))


def test_an_organizer_on_a_server_resolves_recorded_paths(tmp_path, monkeypatch):
    from pyDataOrg import Organizer

    monkeypatch.setattr(servers, "SERVERS", dict(servers.SERVERS))
    mount = tmp_path / "mnt" / "spectra"
    (mount / "S1").mkdir(parents=True)
    (mount / "S1" / "a.csv").write_text("x,y\n1,2\n")
    servers.register_server(servers.Server(
        "ws", {"/instrument/share/spectra": str(mount)}))

    org = Organizer(tmp_path / "org.json", server="ws")
    assert org.local("/instrument/share/spectra/S1/a.csv") == \
        str(mount / "S1" / "a.csv")
    org.add_sample("S1")
    m = org.link("S1", "uvvis", "/instrument/share/spectra/S1/a.csv",
                 check=False)
    assert m.resolve(org.resolver) == [mount / "S1" / "a.csv"]


# ---------------------------------------------------------------------------
# snapshots
# ---------------------------------------------------------------------------

RECORDS_V1 = '''Synthesis_dict = {
    "S1": {"sample_id": "S1", "T_C": 90},
    "S2": {"sample_id": "S2", "T_C": 95},
}
'''
RECORDS_V2 = '''Synthesis_dict = {
    "S1": {"sample_id": "S1", "T_C": 91},
    "S3": {"sample_id": "S3", "T_C": 85},
}
'''


def test_compare_records_finds_new_changed_and_removed():
    old = read_records(RECORDS_V1)
    new = read_records(RECORDS_V2)
    diff = compare_records("synthesis", old, new)
    assert (diff.added, diff.changed, diff.removed) == (["S3"], ["S1"], ["S2"])
    assert diff.any and "1 new" in diff.summary()
    same = compare_records("synthesis", old, old)
    assert not same.any and same.unchanged == 2


def test_a_file_source_syncs_into_dated_snapshots(tmp_path):
    live = tmp_path / "live" / "Synthesis_dict.py"
    live.parent.mkdir()
    live.write_text(RECORDS_V1)
    project = tmp_path / "P"
    source = FileSource({"synthesis": live})

    plan = plan_sync(project, source, tag="Demo", today="20260101")
    assert plan.needed and not (project / "MetaData").exists()   # wrote nothing
    written = write_snapshots(plan)
    assert [p.name for p in written] == ["Synthesis_dict_Demo_20260101.py"]

    again = plan_sync(project, source, tag="Demo", today="20260101")
    assert not again.needed and write_snapshots(again) == []

    live.write_text(RECORDS_V2)
    later = plan_sync(project, source, tag="Demo", today="20260101")
    assert later.diffs["synthesis"].added == ["S3"]
    second = write_snapshots(later)[0]
    assert second.name == "Synthesis_dict_Demo_20260101_2.py"   # same day
    assert latest_snapshots(project) == [second]
    assert [s.n for s in snapshots(project)["synthesis"]] == [1, 2]
    assert set(read_records(second)["Synthesis_dict"]) == {"S1", "S3"}


def test_latest_snapshots_of_an_ordinary_project_is_every_dict(tmp_path):
    (tmp_path / "MetaData").mkdir()
    (tmp_path / "MetaData" / "Synthesis_dict.py").write_text(RECORDS_V1)
    assert [p.name for p in latest_snapshots(tmp_path)] == ["Synthesis_dict.py"]


def test_a_tag_must_be_plain(tmp_path):
    with pytest.raises(ValueError, match="letters and digits"):
        plan_sync(tmp_path, FileSource({}), tag="my-proj")


def test_a_git_source_reads_a_ref_without_touching_the_tree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.org")
    git("config", "user.name", "t")
    (repo / "records").mkdir()
    (repo / "records" / "Synthesis_dict.py").write_text(RECORDS_V1)
    git("add", ".")
    git("commit", "-q", "-m", "first records")
    (repo / "records" / "Synthesis_dict.py").write_text("broken = ")  # unstaged

    source = GitSource(repo, "HEAD", {"synthesis": "records/Synthesis_dict.py"})
    assert "first records" in source.revision().describe()
    plan = plan_sync(tmp_path / "P", source, tag="G", today="20260102")
    assert plan.diffs["synthesis"].added == ["S1", "S2"]
    with pytest.raises(KeyError, match="no records for stage"):
        source.text("testing")
