"""Tests for recorded-path resolution through the project alias table."""

from pathlib import Path

from NanoOrganizer.core.pathmap import (
    ALIASED, LOCAL, MISSING, PathAlias, PathResolver, suggest_aliases,
)


def _make_tree(tmp_path):
    """Build a local stand-in for a tree recorded under another prefix."""
    run = tmp_path / "local_mount" / "spectra_share" / "SERIAL1" / "2026-09-21" / "run_a"
    run.mkdir(parents=True)
    for name in ("spec_b01_000.npy", "spec_b01_001.npy", "spec_b02_000.npy"):
        (run / name).write_bytes(b"")
    (run / "wavelength.npy").write_bytes(b"")
    return run


def test_unaliased_path_is_missing_not_an_error(tmp_path):
    resolver = PathResolver()
    recorded = "/instrument/share/spectra_share/SERIAL1/run_a/spec.npy"

    assert resolver.resolve(recorded) is None
    assert resolver.exists(recorded) is False
    assert resolver.status(recorded) == MISSING


def test_alias_rewrites_a_recorded_prefix(tmp_path):
    _make_tree(tmp_path)
    resolver = PathResolver([
        ("/instrument/share", [str(tmp_path / "local_mount")]),
    ])
    recorded = ("/instrument/share/spectra_share/SERIAL1/2026-09-21/"
                "run_a/spec_b01_000.npy")

    found = resolver.resolve(recorded)
    assert found is not None
    assert found.name == "spec_b01_000.npy"
    assert resolver.status(recorded) == ALIASED


def test_existing_path_wins_over_alias(tmp_path):
    real = tmp_path / "already_here.npy"
    real.write_bytes(b"")
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "already_here.npy").write_bytes(b"")

    resolver = PathResolver([(str(tmp_path), [str(decoy)])])
    assert resolver.resolve(real) == real
    assert resolver.status(real) == LOCAL


def test_first_matching_candidate_wins(tmp_path):
    second = tmp_path / "second"
    (second / "sub").mkdir(parents=True)
    (second / "sub" / "f.npy").write_bytes(b"")

    resolver = PathResolver([
        ("/recorded", [str(tmp_path / "first_missing"), str(second)]),
    ])
    found = resolver.resolve("/recorded/sub/f.npy")
    assert found == second / "sub" / "f.npy"


def test_prefix_must_match_whole_components(tmp_path):
    """``/data`` must not match ``/database``."""
    resolver = PathResolver([("/data", [str(tmp_path)])])
    assert resolver.candidates_for("/database/x.npy") == ["/database/x.npy"]


def test_glob_expands_through_the_alias(tmp_path):
    run = _make_tree(tmp_path)
    resolver = PathResolver([
        ("/instrument/share", [str(tmp_path / "local_mount")]),
    ])
    pattern = ("/instrument/share/spectra_share/SERIAL1/2026-09-21/"
               "run_a/*_b01_*.npy")

    hits = resolver.resolve_glob(pattern)
    assert [p.name for p in hits] == ["spec_b01_000.npy", "spec_b01_001.npy"]
    assert run.exists()


def test_glob_does_not_mix_two_roots(tmp_path):
    """A partially mounted tree must not contribute files from both prefixes."""
    first = tmp_path / "first" / "run"
    first.mkdir(parents=True)
    (first / "a_01.npy").write_bytes(b"")

    second = tmp_path / "second" / "run"
    second.mkdir(parents=True)
    (second / "a_02.npy").write_bytes(b"")

    resolver = PathResolver([("/rec", [str(tmp_path / "first"),
                                       str(tmp_path / "second")])])
    hits = resolver.resolve_glob("/rec/run/a_*.npy")
    assert [p.name for p in hits] == ["a_01.npy"]


def test_windows_recorded_path_resolves_on_posix(tmp_path):
    target = tmp_path / "proj" / "data.csv"
    target.parent.mkdir()
    target.write_text("x")

    resolver = PathResolver([(r"D:\Acquire", [str(tmp_path)])])
    assert resolver.resolve(r"D:\Acquire\proj\data.csv") == target


def test_resolve_many_splits_found_from_missing(tmp_path):
    present = tmp_path / "p.npy"
    present.write_bytes(b"")
    resolver = PathResolver()

    resolved, missing = resolver.resolve_many([present, "/nowhere/q.npy"])
    assert resolved == [present]
    assert missing == ["/nowhere/q.npy"]


def test_alias_round_trips_through_dict(tmp_path):
    original = PathResolver([("/rec", ["/local/a", "/local/b"])],
                            extra_roots=("/scratch",))
    restored = PathResolver.from_dict(original.to_dict())

    assert restored.aliases[0].prefix == "/rec"
    assert restored.aliases[0].candidates == ("/local/a", "/local/b")
    assert restored.extra_roots == ("/scratch",)


def test_add_alias_invalidates_the_cache(tmp_path):
    target = tmp_path / "mount" / "f.npy"
    target.parent.mkdir()
    target.write_bytes(b"")
    resolver = PathResolver()

    assert resolver.resolve("/rec/f.npy") is None   # caches the miss
    resolver.add_alias("/rec", [str(tmp_path / "mount")])
    assert resolver.resolve("/rec/f.npy") == target


def test_suggest_aliases_finds_a_shared_directory_name(tmp_path):
    local = tmp_path / "Storage" / "spectra_share"
    local.mkdir(parents=True)
    recorded = "/instrument/share/spectra_share/SERIAL1/run/x.npy"

    suggestions = suggest_aliases([recorded], [str(tmp_path)], max_depth=3)
    assert suggestions
    alias = suggestions[0]
    assert alias.prefix.endswith("spectra_share")
    assert str(local) in alias.candidates


def test_trailing_slashes_do_not_defeat_matching():
    alias = PathAlias(prefix="/rec/", candidates=("/local/",))
    assert alias.rewrite("/rec/sub/f.npy") == ["/local/sub/f.npy"]


# ---------------------------------------------------------------------------
# Relative paths: relative to the project root, never the working directory
# ---------------------------------------------------------------------------

def test_a_relative_path_resolves_against_the_base_not_the_cwd(tmp_path,
                                                                monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.dat").write_text("1 2\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert PathResolver().resolve("data/a.dat") is None          # cwd: not here
    resolver = PathResolver(base=tmp_path)
    assert resolver.resolve("data/a.dat") == tmp_path / "data" / "a.dat"
    assert resolver.status("data/a.dat") == LOCAL
    assert resolver.resolve_glob("data/*.dat") == [tmp_path / "data" / "a.dat"]
    assert resolver.anchor("/abs/x") == "/abs/x"                  # untouched


def test_display_path_says_where_from_here(tmp_path):
    from NanoOrganizer.core.pathmap import display_path

    repo = tmp_path / "Repos" / "NanoOrganizer"
    target = tmp_path / "Repos" / "OrgDemo" / "CuAu"
    assert display_path(target, start=repo) == "../OrgDemo/CuAu"
    assert display_path(target, start=repo / "notebook") == "../../OrgDemo/CuAu"
    assert display_path("TEMData/CuAu05") == "TEMData/CuAu05"     # already relative
    far = display_path(target, start=tmp_path / "a" / "b" / "c" / "d")
    assert ".." not in far                                        # too far: not relative
