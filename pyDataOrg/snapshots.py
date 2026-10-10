#!/usr/bin/env python3
"""
Dated snapshots of authored records, and what changed between them.

Sample records are often written somewhere that keeps changing — an
instrument's control repository, a shared folder an operator edits as runs
finish. A project should not read that moving target directly: an analysis
run today and re-run next month would silently see different records. So the
project keeps **snapshots** in its own ``MetaData/`` folder::

    MetaData/Synthesis_dict_MyProj_20261002.py
    MetaData/Synthesis_dict_MyProj_20261007.py     <- the newest one is read
    MetaData/Testing_dict_MyProj_20261007.py

and every analysis ran on a file that still exists, unchanged, next to its
data. An older snapshot can be reopened to see what was known then.

Where the live records come from is a :class:`RecordSource`: a file on disk
(:class:`FileSource`) or a file at a git ref (:class:`GitSource`). Three
steps, each one call::

    source = GitSource("~/Repos/instrument-control", "origin/main",
                       {"synthesis": "records/Synthesis_dict.py"})
    plan = plan_sync("~/Data/MyProj", source, tag="MyProj")   # writes nothing
    print(plan.summary())
    write_snapshots(plan)              # copy the changed records into MetaData/

Nothing here edits the source or fetches from a remote: a git ref is read as
it stands (``git fetch`` there first for the very latest).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Union

METADATA_DIR = "MetaData"

SNAPSHOT_RE = re.compile(
    r"^(?P<stage>[A-Za-z]+)_dict_(?P<tag>[A-Za-z0-9]+)_(?P<date>\d{8})"
    r"(?:_(?P<n>\d+))?\.py$")


# ---------------------------------------------------------------------------
# Snapshots already in the project
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Snapshot:
    """One dated copy of a stage's records inside ``MetaData/``."""

    path: Path
    stage: str
    tag: str
    date: str          # YYYYMMDD
    n: int = 1         # second snapshot on the same day -> 2

    @property
    def order(self):
        return (self.date, self.n)


def snapshots(root: Union[str, Path],
              metadata_dir: str = METADATA_DIR) -> Dict[str, List[Snapshot]]:
    """Every snapshot in *root*'s ``MetaData/``, oldest first, per stage."""
    folder = Path(root).expanduser() / metadata_dir
    out: Dict[str, List[Snapshot]] = {}
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.py")):
        match = SNAPSHOT_RE.match(path.name)
        if not match:
            continue
        snap = Snapshot(path=path, stage=match["stage"].lower(),
                        tag=match["tag"], date=match["date"],
                        n=int(match["n"] or 1))
        out.setdefault(snap.stage, []).append(snap)
    for stage in out:
        out[stage].sort(key=lambda s: s.order)
    return out


def latest_snapshots(root: Union[str, Path],
                     metadata_dir: str = METADATA_DIR) -> List[Path]:
    """The newest snapshot of each stage — what the project should read.

    A ``MetaData/`` holding no dated snapshots at all is an ordinary project,
    and every ``*.py`` in it is returned instead.
    """
    root = Path(root).expanduser()
    found = snapshots(root, metadata_dir)
    if found:
        return [found[stage][-1].path for stage in sorted(found)]
    folder = root / metadata_dir
    return sorted(folder.glob("*.py")) if folder.is_dir() else []


def read_records(source: Union[str, Path]) -> Dict[str, Dict[str, dict]]:
    """``{dict_name: {sample_id: record}}`` from a records file or its text.

    Text is written to a scratch file first, because the records are Python
    and executing it is the only faithful way to read it — so only read
    records you would run.
    """
    from pyDataOrg.ingest.pydict import find_sample_dicts

    if isinstance(source, Path) or (isinstance(source, str)
                                    and "\n" not in source
                                    and source.endswith(".py")):
        return find_sample_dicts(Path(source).expanduser())
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "records.py"
        path.write_text(str(source), encoding="utf-8")
        return find_sample_dicts(path)


# ---------------------------------------------------------------------------
# What changed
# ---------------------------------------------------------------------------

@dataclass
class RecordDiff:
    """How one stage's records differ between two snapshots."""

    stage: str
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    unchanged: int = 0

    @property
    def any(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def summary(self) -> str:
        if not self.any:
            return f"{self.stage}: no change ({self.unchanged} records)"
        parts = []
        for label, ids in (("new", self.added), ("changed", self.changed),
                           ("removed", self.removed)):
            if ids:
                shown = ", ".join(ids[:4]) + (" …" if len(ids) > 4 else "")
                parts.append(f"{len(ids)} {label} ({shown})")
        return f"{self.stage}: " + "; ".join(parts)


def _flat(records: Mapping[str, Mapping[str, dict]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for dict_name, block in records.items():
        for sample_id, record in block.items():
            out[str(sample_id)] = json.dumps(
                {"dict": dict_name, "record": record},
                sort_keys=True, default=str)
    return out


def compare_records(stage: str, old: Mapping, new: Mapping) -> RecordDiff:
    """Sample by sample: which records are new, gone, or edited.

    *old* and *new* are ``{dict_name: {sample_id: record}}``, as
    :func:`read_records` returns.
    """
    before, after = _flat(old), _flat(new)
    diff = RecordDiff(stage=stage)
    diff.added = sorted(set(after) - set(before))
    diff.removed = sorted(set(before) - set(after))
    for key in sorted(set(after) & set(before)):
        if after[key] == before[key]:
            diff.unchanged += 1
        else:
            diff.changed.append(key)
    return diff


# ---------------------------------------------------------------------------
# Where the live records are
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Revision:
    """Which version of the live records was read."""

    source: str
    version: str = ""
    date: str = ""
    note: str = ""

    def describe(self) -> str:
        text = self.source + (f" @ {self.version}" if self.version else "")
        if self.date:
            text += f" ({self.date})"
        return text + (f" — {self.note}" if self.note else "")


class RecordSource:
    """Where a project's live records are: one file per stage.

    Subclasses implement :meth:`text` and :meth:`revision`; :attr:`files`
    is ``{stage: where that stage's records are}``.
    """

    files: Mapping[str, str] = {}

    def stages(self) -> List[str]:
        return list(self.files)

    def text(self, stage: str) -> str:              # pragma: no cover
        raise NotImplementedError

    def revision(self) -> Revision:                 # pragma: no cover
        raise NotImplementedError

    def _check(self, stage: str) -> str:
        if stage not in self.files:
            raise KeyError(f"no records for stage {stage!r}; "
                           f"known: {', '.join(self.files)}")
        return self.files[stage]


class FileSource(RecordSource):
    """Records in files on disk: ``{stage: path}``."""

    def __init__(self, files: Mapping[str, Union[str, Path]]):
        self.files = {stage: str(path) for stage, path in files.items()}

    def text(self, stage: str) -> str:
        return Path(self._check(stage)).expanduser().read_text(encoding="utf-8")

    def revision(self) -> Revision:
        times = [Path(p).expanduser().stat().st_mtime
                 for p in self.files.values() if Path(p).expanduser().exists()]
        newest = (_dt.datetime.fromtimestamp(max(times)).strftime("%Y-%m-%d %H:%M")
                  if times else "")
        return Revision(source="files", date=newest)


class GitSource(RecordSource):
    """Records in a git repository at a ref: ``{stage: path in the repo}``.

    Read with ``git show <ref>:<path>`` — the working tree is never touched,
    so the ref can be a remote-tracking branch nobody has checked out.
    """

    def __init__(self, repo: Union[str, Path], ref: str,
                 files: Mapping[str, str]):
        self.repo = Path(repo).expanduser()
        self.ref = ref
        self.files = dict(files)

    def _git(self, *args: str) -> str:
        try:
            done = subprocess.run(["git", "-C", str(self.repo), *args],
                                  check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:                # pragma: no cover
            raise RuntimeError("git is not installed") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"git {' '.join(args)} failed in {self.repo.name}: "
                f"{exc.stderr.strip() or exc}") from exc
        return done.stdout

    def text(self, stage: str) -> str:
        return self._git("show", f"{self.ref}:{self._check(stage)}")

    def revision(self) -> Revision:
        line = self._git("log", "-1", "--format=%h%x1f%ci%x1f%s",
                         self.ref).strip()
        commit, date, subject = (line.split("\x1f") + ["", "", ""])[:3]
        return Revision(source=f"{self.repo.name} {self.ref}", version=commit,
                        date=date[:16], note=subject)


# ---------------------------------------------------------------------------
# Planning and writing a sync
# ---------------------------------------------------------------------------

@dataclass
class SyncPlan:
    """What :func:`write_snapshots` would do. Building one writes nothing."""

    root: Path
    revision: Revision
    texts: Dict[str, str]
    diffs: Dict[str, RecordDiff]
    current: Dict[str, Optional[Path]]
    targets: Dict[str, Path]
    origins: Dict[str, str] = field(default_factory=dict)

    @property
    def needed(self) -> bool:
        return any(d.any for d in self.diffs.values())

    def summary(self) -> str:
        lines = [f"live records: {self.revision.describe()}"]
        for stage, diff in self.diffs.items():
            current = self.current.get(stage)
            lines.append(f"  {diff.summary()}"
                         + (f"   [now: {current.name}]" if current else
                            "   [no snapshot yet]"))
        if self.needed:
            lines.append("  would write: " + ", ".join(
                p.name for s, p in self.targets.items() if self.diffs[s].any))
        else:
            lines.append("  the project is up to date")
        return "\n".join(lines)


def snapshot_path(root: Union[str, Path], stage: str, tag: str, date: str,
                  metadata_dir: str = METADATA_DIR) -> Path:
    """``MetaData/<Stage>_dict_<tag>_<date>.py``, or ``…_2.py`` if taken."""
    folder = Path(root).expanduser() / metadata_dir
    stem = f"{stage.capitalize()}_dict_{tag}_{date}"
    path = folder / f"{stem}.py"
    n = 2
    while path.exists():
        path = folder / f"{stem}_{n}.py"
        n += 1
    return path


def plan_sync(root: Union[str, Path], source: RecordSource, *, tag: str,
              stages: Sequence[str] = (), today: Optional[str] = None,
              metadata_dir: str = METADATA_DIR) -> SyncPlan:
    """Compare *source*'s records with the project's newest snapshots."""
    if not re.fullmatch(r"[A-Za-z0-9]+", tag):
        raise ValueError(f"tag {tag!r}: letters and digits only")
    root = Path(root).expanduser()
    revision = source.revision()
    date = today or _dt.date.today().strftime("%Y%m%d")
    existing = snapshots(root, metadata_dir)

    texts, diffs, current, targets, origins = {}, {}, {}, {}, {}
    for stage in stages or source.stages():
        text = source.text(stage)
        latest = existing.get(stage, [None])[-1]
        old = read_records(latest.path) if latest else {}
        diffs[stage] = compare_records(stage, old, read_records(text))
        texts[stage] = text
        current[stage] = latest.path if latest else None
        targets[stage] = snapshot_path(root, stage, tag, date, metadata_dir)
        origins[stage] = source.files.get(stage, "")
    return SyncPlan(root=root, revision=revision, texts=texts, diffs=diffs,
                    current=current, targets=targets, origins=origins)


def write_snapshots(plan: SyncPlan, *, force: bool = False) -> List[Path]:
    """Write a new snapshot for every stage whose records changed.

    Existing snapshots are never overwritten; a second one on the same day
    gets a ``_2`` suffix. Returns the files written (none when up to date).
    """
    written = []
    for stage, text in plan.texts.items():
        if not (force or plan.diffs[stage].any):
            continue
        target = plan.targets[stage]
        target.parent.mkdir(parents=True, exist_ok=True)
        origin = Path(plan.origins.get(stage, "")).name or stage
        header = (
            f"# Snapshot of {origin}\n"
            f"# {plan.revision.describe()}\n"
            f"# Written by pyDataOrg.snapshots on "
            f"{_dt.date.today().isoformat()}. Do not edit; take a new "
            f"snapshot instead.\n")
        target.write_text(header + text, encoding="utf-8")
        written.append(target)
    return written


__all__ = [
    "METADATA_DIR", "SNAPSHOT_RE", "Snapshot", "snapshots", "latest_snapshots",
    "read_records", "RecordDiff", "compare_records",
    "Revision", "RecordSource", "FileSource", "GitSource",
    "SyncPlan", "snapshot_path", "plan_sync", "write_snapshots",
]
