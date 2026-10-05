"""Tests for the structure inspector.

The promise this module makes is that a directory, a JSON file, an HDF5 group
and a Python metadata module all behave the same way: ask for children, get a
layer, descend. These tests check that promise holds for each of them, that
the inspector reads *structure* rather than data, and that nothing it is
pointed at can make it raise.
"""

import json

import numpy as np
import pytest

from NanoOrganizer import structure as S


@pytest.fixture()
def sandbox(tmp_path):
    """A directory with one of everything the inspector claims to open."""
    (tmp_path / "RawData" / "run01").mkdir(parents=True)
    for index in range(5):
        np.save(tmp_path / "RawData" / "run01" / f"frame_{index:03d}.npy",
                np.linspace(0, 1, 64))

    json.dump({"project": {"name": "demo",
                           "samples": [{"id": "A", "T": 60.0},
                                       {"id": "B", "T": 90.0}],
                           "count": 2}},
              open(tmp_path / "record.json", "w"))

    np.savez(tmp_path / "reduced.npz", q=np.linspace(0, 1, 32),
             intensity=np.random.rand(32, 3))

    (tmp_path / "table.dat").write_text(
        "# instrument: demo\n# q_invA\tI\n0.01\t120.5\n0.02\t118.1\n0.03\t99.0\n")

    (tmp_path / "Meta_dict.py").write_text(
        'Meta_dict = {\n'
        '    "S1": {"sample_id": "S1", "conditions": {"T": 60.0}},\n'
        '    "S2": {"sample_id": "S2", "conditions": {"T": 90.0}},\n'
        '}\n')
    return tmp_path


def names(nodes):
    return [n.name for n in nodes]


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------

def test_an_address_splits_into_a_file_and_a_path_inside_it():
    path, inside = S.split_address("/a/b.json::x/0/y")
    assert path.name == "b.json"
    assert inside == ["x", "0", "y"]


def test_a_plain_path_has_nothing_inside():
    path, inside = S.split_address("/a/b")
    assert inside == []


def test_joining_is_the_inverse_of_splitting():
    address = "/a/b.h5::entry/data"
    path, inside = S.split_address(address)
    assert S.join_address(path, inside) == address


def test_breadcrumbs_reach_every_ancestor(sandbox):
    address = S.join_address(sandbox / "record.json", ["project", "samples"])
    trail = S.breadcrumbs(address)
    assert [label for label, _ in trail][-3:] == ["record.json", "project",
                                                  "samples"]
    # Every crumb must be a usable address, or the trail is decoration.
    assert S.describe(trail[-3][1]).kind in {"file", "mapping"}


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------

def test_a_folder_summarises_what_is_in_it(sandbox):
    node = S.describe(str(sandbox / "RawData" / "run01"))
    assert node.kind == "folder"
    assert "5 files" in node.detail
    assert ".npy 5" in node.detail


def test_a_folder_lists_folders_before_files(sandbox):
    listed = S.children(str(sandbox))
    kinds = [n.kind for n in listed]
    assert kinds.index("folder") < kinds.index("file")


def test_a_big_folder_is_truncated_and_says_so(tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    for index in range(50):
        (folder / f"f{index:03d}.txt").write_text("x")

    listed = S.children(str(folder), limit=10)
    assert len(listed) == 11
    assert listed[-1].kind == "more"
    assert "+40 more" in listed[-1].name


# ---------------------------------------------------------------------------
# Reading structure, not data
# ---------------------------------------------------------------------------

def test_an_npy_reports_its_shape_without_loading_it(sandbox):
    node = S.describe_file(sandbox / "RawData" / "run01" / "frame_000.npy")
    assert node.kind == "array"
    assert "(64,)" in node.detail
    assert "float64" in node.detail


def test_a_huge_file_is_described_but_not_parsed(tmp_path, monkeypatch):
    """Clicking a node must never hang the browser."""
    big = tmp_path / "huge.json"
    big.write_text("{}")
    monkeypatch.setattr(S, "MAX_PARSE_BYTES", 0)
    node = S.describe_file(big)
    assert node.expandable is False
    assert "too large" in node.detail


def test_npz_members_come_back_with_shapes(sandbox):
    listed = S.children(str(sandbox / "reduced.npz"))
    assert set(names(listed)) == {"q", "intensity"}
    assert "(32, 3)" in dict((n.name, n.detail) for n in listed)["intensity"]


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def test_json_descends_one_layer_at_a_time(sandbox):
    address = str(sandbox / "record.json")
    top = S.children(address)
    assert names(top) == ["project"]

    inner = S.children(top[0].address)
    assert set(names(inner)) == {"name", "samples", "count"}

    samples = [n for n in inner if n.name == "samples"][0]
    assert samples.kind == "sequence"
    assert "2 items of dict" in samples.detail

    first = S.children(samples.address)[0]
    assert first.name == "0"
    assert set(names(S.children(first.address))) == {"id", "T"}


def test_scalars_show_their_type_and_value(sandbox):
    inner = S.children(S.children(str(sandbox / "record.json"))[0].address)
    detail = dict((n.name, n.detail) for n in inner)
    assert detail["count"] == "int = 2"
    assert detail["name"] == "str = demo"


# ---------------------------------------------------------------------------
# Metadata modules
# ---------------------------------------------------------------------------

def test_a_metadata_module_exposes_its_sample_dicts(sandbox):
    top = S.children(str(sandbox / "Meta_dict.py"))
    assert names(top) == ["Meta_dict"]
    assert "2 samples" in top[0].detail

    samples = S.children(top[0].address)
    assert names(samples) == ["S1", "S2"]
    assert set(names(S.children(samples[0].address))) == {"sample_id",
                                                          "conditions"}


def test_a_module_with_no_sample_dicts_says_so(tmp_path):
    (tmp_path / "plain.py").write_text("x = 1\n")
    listed = S.children(str(tmp_path / "plain.py"))
    assert listed[0].kind == "error"


# ---------------------------------------------------------------------------
# Text tables
# ---------------------------------------------------------------------------

def test_a_text_table_reports_its_shape_and_headers(sandbox):
    listed = S.children(str(sandbox / "table.dat"))
    detail = dict((n.name, n.detail) for n in listed)
    assert "3 rows × 2 columns" in detail["shape"]
    assert any("instrument: demo" in n.detail for n in listed)


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------

def test_a_missing_path_is_an_error_node_not_an_exception():
    node = S.describe("/no/such/place")
    assert node.kind == "error"
    assert S.children("/no/such/place")[0].kind == "error"


def test_an_unparseable_file_is_an_error_node(tmp_path):
    """A browser that throws on one bad file in a thousand is not a browser."""
    broken = tmp_path / "broken.json"
    broken.write_text("{not json at all")
    listed = S.children(str(broken))
    assert len(listed) == 1 and listed[0].kind == "error"


def test_a_leaf_simply_has_no_children(tmp_path):
    (tmp_path / "image.tif").write_bytes(b"II*\x00")
    assert S.children(str(tmp_path / "image.tif")) == []


# ---------------------------------------------------------------------------
# Text tree
# ---------------------------------------------------------------------------

def test_the_text_tree_descends_and_indents(sandbox):
    text = S.tree(str(sandbox), depth=3, limit=10)
    assert "RawData" in text
    assert "run01" in text
    assert "frame_000.npy" in text
    assert "│" in text or "└" in text


def test_depth_limits_how_far_it_walks(sandbox):
    shallow = S.tree(str(sandbox), depth=1, limit=10)
    assert "RawData" in shallow
    assert "run01" not in shallow


def test_the_tree_reports_the_true_remainder(tmp_path):
    """Counting the truncated list would report the size of the truncation,
    not of what was left out."""
    folder = tmp_path / "many"
    folder.mkdir()
    for index in range(30):
        (folder / f"f{index:02d}.txt").write_text("x")

    text = S.tree(str(folder), depth=1, limit=5)
    assert "+25 more" in text


def test_human_bytes_reads_like_a_file_manager():
    assert S.human_bytes(512) == "512 B"
    assert S.human_bytes(2048) == "2.0 KB"
    assert S.human_bytes(5 * 1024 ** 3) == "5.0 GB"


# ---------------------------------------------------------------------------
# HDF5
# ---------------------------------------------------------------------------

def test_hdf5_groups_datasets_and_attributes(tmp_path):
    h5py = pytest.importorskip("h5py")

    path = tmp_path / "run.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("entry/data/image", data=np.zeros((16, 16)),
                              compression="gzip")
        handle["entry"].attrs["title"] = "demo run"

    entry = S.children(str(path))[0]
    assert entry.name == "entry" and entry.kind == "group"

    inside = S.children(entry.address)
    assert any(n.name == "@title" and "demo run" in n.detail for n in inside)

    image = S.children([n for n in inside if n.name == "data"][0].address)[0]
    assert image.kind == "array"
    assert "(16, 16)" in image.detail and "gzip" in image.detail


# ---------------------------------------------------------------------------
# On a real generated project
# ---------------------------------------------------------------------------

def test_it_walks_the_demo_project(tmp_path):
    from NanoOrganizer.demo import build_showcase_project

    root = build_showcase_project(tmp_path / "Demo", fractions=(0.0, 1.0),
                                  n_frames=2, with_images=False,
                                  with_tomography=False)
    text = S.tree(str(root), depth=3, limit=20)
    for expected in ("MetaData", "Synthesis_dict.py", "Electrochemistry",
                     "Spectroscopy"):
        assert expected in text, expected

    module = S.children(str(root / "MetaData" / "Characterization_dict.py"))
    samples = S.children(module[0].address)
    blocks = names(S.children(samples[0].address))
    assert "UVVis" in blocks and "EDS" in blocks


# ---------------------------------------------------------------------------
# Housekeeping entries
# ---------------------------------------------------------------------------

def test_pycache_is_hidden_but_counted(tmp_path):
    """Ingesting a metadata module creates __pycache__; reporting our own
    footprint back as the user's data would be wrong — but so would dropping
    it silently."""
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / ".hidden").write_text("x")
    (tmp_path / "real.dat").write_text("1 2\n")

    assert names(S.children(str(tmp_path))) == ["real.dat"]
    assert "2 hidden" in S.describe(str(tmp_path)).detail

    shown = names(S.children(str(tmp_path), show_hidden=True))
    assert "__pycache__" in shown and ".hidden" in shown


def test_show_hidden_reaches_the_text_tree(tmp_path):
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "real.dat").write_text("1 2\n")
    assert "__pycache__" not in S.tree(str(tmp_path), depth=1)
    assert "__pycache__" in S.tree(str(tmp_path), depth=1, show_hidden=True)
