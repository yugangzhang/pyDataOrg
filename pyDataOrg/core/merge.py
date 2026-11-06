#!/usr/bin/env python3
"""
Merging – fold what another organiser holds into this one.

Two people work on one campaign, each with an organiser: one is the master,
the other a co-worker's copy that has moved ahead (new records ingested, new
fits kept). :func:`merge_projects` brings the co-worker's additions into the
master and leaves everything the master already holds alone::

    report = merge_projects(master.project, other.project,
                            copy_to=master_root / "Results")
    report[report["action"] == "clash"]          # where the two disagree

The master wins. Item by item — a sample, a stage record, a measurement, a
derived value:

=================  ==========================================================
only in *other*    added (a measurement's relative paths rebased; files of
                   a *copy* modality copied into *copy_to* first)
the same in both   nothing to do
different          kept as the master has it, reported as a ``clash``
=================  ==========================================================

A measurement to be copied whose files cannot be read here is not added
(it would be a dead link) and is reported ``unreadable``; one linked where it is
is added either way, noted when it is not readable here. Nothing is saved, and *other* is
never changed.
"""

from __future__ import annotations

import filecmp
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

import pandas as pd

from pyDataOrg.core.pathmap import is_relative
from pyDataOrg.core.project import Project
from pyDataOrg.core.schema import Measurement, Sample

COLUMNS = ["sample", "kind", "item", "action", "note"]


def _row(sample, kind, item, action, note=""):
    return dict(sample=sample, kind=kind, item=item, action=action, note=note)


def _anchored(path: str, root: Path) -> str:
    """*path* as recorded in a project at *root*: a relative one made absolute."""
    return os.path.normpath(str(Path(root) / path)) if is_relative(path) else path


def _same_measurement(a: Measurement, a_root: Path,
                      b: Measurement, b_root: Path) -> bool:
    """Whether two measurements say the same, paths compared where they point."""
    def key(m: Measurement, root: Path) -> dict:
        data = m.to_dict()
        data["paths"] = [_anchored(p, root) for p in m.paths]
        data["pattern"] = _anchored(m.pattern, root) if m.pattern else ""
        return data
    return key(a, a_root) == key(b, b_root)


def _copied(measurement: Measurement, other: Project, into: Project,
            copy_to: Path) -> Optional[Measurement]:
    """*measurement* with its files copied into *copy_to* and recorded
    relative to *into*'s root; ``None`` when a file is not readable here or
    one of the same name in *copy_to* differs."""
    found = measurement.resolve(other.resolver)
    if not found or len(found) < len(measurement.paths):
        return None
    copy_to.mkdir(parents=True, exist_ok=True)
    paths = []
    for source in found:
        target = copy_to / Path(source).name
        if target.exists():
            if not filecmp.cmp(source, target, shallow=False):
                return None
        else:
            shutil.copy2(source, target)
        paths.append(Path(os.path.relpath(target.absolute(), into.root)).as_posix())
    copy = Measurement.from_dict(measurement.to_dict())
    copy.paths, copy.pattern = paths, ""
    return copy


def _rebased(measurement: Measurement, old_root: Path, new_root: Path) -> Measurement:
    """A copy of *measurement* whose relative paths point at the same files
    from *new_root*."""
    def move(path):
        if not isinstance(path, str) or not path or not is_relative(path):
            return path
        return Path(os.path.relpath(Path(old_root) / path, new_root)).as_posix()
    copy = Measurement.from_dict(measurement.to_dict())
    copy.paths = [move(p) for p in copy.paths]
    copy.pattern = move(copy.pattern)
    copy.aux = {k: move(v) for k, v in copy.aux.items()}
    return copy


def merge_projects(into: Project, other: Project, *,
                   copy_to: Union[str, Path, None] = None,
                   copy: Sequence[str] = ("fit",),
                   samples: Sequence[str] = ()) -> pd.DataFrame:
    """Fold what *other* holds and *into* does not into *into*; *into* wins.

    Measurements of the modalities in *copy* (kept results, by default) have
    their files copied into *copy_to* (relative: to *into*'s root) — a
    co-worker's results folder may go away; without *copy_to* they are
    linked where they are. *samples* limits the merge to those ids.

    Returns a table, a row per item looked at that was not already the same:
    ``sample``, ``kind`` (sample / stage / measurement / derived), ``item``,
    ``action`` (``added``, ``clash`` — the master's kept —, ``unreadable``)
    and ``note``. Nothing is saved.
    """
    if copy_to is not None:
        copy_to = Path(copy_to).expanduser()
        if not copy_to.is_absolute():
            copy_to = Path(into.root) / copy_to
    rows: List[Dict] = []
    wanted = set(samples)
    for theirs in other.sorted_samples():
        sid = theirs.sample_id
        if wanted and sid not in wanted:
            continue
        ours = into.get_sample(sid)
        if ours is None:
            ours = into.samples[sid] = Sample(
                sample_id=sid, tags=list(theirs.tags), notes=theirs.notes,
                created_at=theirs.created_at)
            rows.append(_row(sid, "sample", sid, "added"))

        for name, stage in theirs.stages.items():
            mine = ours.stages.get(name)
            if mine is None:
                ours.stages[name] = stage
                rows.append(_row(sid, "stage", name, "added"))
            elif mine.to_dict() != stage.to_dict():
                rows.append(_row(sid, "stage", name, "clash", "the master's kept"))

        for measurement in theirs.measurements:
            mid = measurement.measurement_id
            mine = ours.get_measurement(mid)
            if mine is not None:
                if not _same_measurement(mine, into.root, measurement, other.root):
                    rows.append(_row(sid, "measurement", mid, "clash",
                                     "the master's kept"))
                continue
            if copy_to is not None and measurement.modality in copy:
                added = _copied(measurement, other, into, copy_to)
                if added is None:
                    rows.append(_row(sid, "measurement", mid, "unreadable",
                                     "a file is not readable here, or differs "
                                     "from one of that name already copied"))
                    continue
            else:
                added = _rebased(measurement, other.root, into.root)
            ours.add_measurement(added)
            readable = added.availability(into.resolver)["available"]
            rows.append(_row(sid, "measurement", mid, "added",
                             "" if readable else "not readable here"))

        for name, value in theirs.derived.items():
            mine = ours.derived.get(name)
            if mine is None:
                ours.derived[name] = value
                rows.append(_row(sid, "derived", name, "added"))
            elif str(mine.value) != str(value.value):
                rows.append(_row(sid, "derived", name, "clash", "the master's kept"))
    into._resolver = None
    return pd.DataFrame(rows, columns=COLUMNS)


__all__ = ["merge_projects"]
