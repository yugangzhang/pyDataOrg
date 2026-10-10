#!/usr/bin/env python3
"""
Linking – attach data to a sample wherever that data happens to live.

:meth:`Project.attach_folders` handles the tidy case: data already laid out as
``<Modality>Data/<SampleID>/`` under the project root.  Real campaigns are not
tidy.  The micrographs are on the microscope's share, the beamline wrote its
own tree on another mount, and the spectra are in whatever folder the student
made that afternoon.  None of it is going to move, and copying it would create
a second copy to keep in sync.

So the organiser links instead of collecting::

    project.link("CuAu05", "uvvis", "/mnt/specs/CuAu05/*.csv", stage="synthesis")
    project.link("CuAu05", "tem",   "/mnt/scope/session17/")
    project.link("CuAu05", "waxs1d", ["/beamline/2024_3/w1.dat"])

Three forms of *source* are accepted and they mean different things:

=================  ==========================================================
a glob string      stored as :attr:`Measurement.pattern` – a **live** query,
                   re-expanded at read time, so files added later appear
a directory        listed **now**, filtered by the modality's extensions, and
                   stored as explicit paths – a snapshot you can audit
a path or a list   stored verbatim as explicit paths
=================  ==========================================================

Use :func:`link_folder` when you want a directory to stay live:
``link_folder(..., "/mnt/scope/session17", pattern="*.tif")`` records the glob
rather than the listing.

Paths are recorded **exactly as given**.  Nothing is rewritten relative to the
project, because a store that has been rewritten is a store that only works on
the machine that wrote it.  Portability is handled the way the rest of the
package handles it – with an alias.  Each link registers one for the mount its
data sits on (``/mnt/instrument → /mnt/instrument``), which is a no-op here and the one
line to edit on the next machine::

    project.add_alias("/mnt/instrument", ["/data/instrument"])    # elsewhere

A **relative** path is relative to the project root — the folder the
organizer's JSON sits in — and is recorded relative, so data kept beside the
organizer needs no alias at all: the folder moves as one piece::

    org.link("CuAu05", "tem", "TEMData/CuAu05")          # beside cuau.json
    org.link("CuAu05", "dls", "../shared/DLS/CuAu05")    # one level up
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from pyDataOrg.core import modality as _modality
from pyDataOrg.core.schema import Measurement, STAGE_CHARACTERIZATION
from pyDataOrg.core.pathmap import is_relative

#: Characters that make a path a glob rather than a location.
GLOB_CHARS = "*?["

#: Separator joining several paths into one table cell.  A semicolon, because
#: a comma is a CSV delimiter and a colon is legal in a Windows path.
SEP = ";"

PathLike = Union[str, Path]
Source = Union[PathLike, Sequence[PathLike]]


# ---------------------------------------------------------------------------
# Mount detection
# ---------------------------------------------------------------------------

def mount_prefix(path: PathLike, fallback_depth: int = 2) -> str:
    """Return the prefix of *path* worth aliasing: its mount point.

    Walks up from *path* to the first real mount point, which is what makes
    ``/mnt/instrument/2024_3/...`` report ``/mnt/instrument`` – the thing that will
    be somewhere else on the next machine.  When the walk reaches ``/`` (a
    single-partition workstation, where every path is on the root filesystem)
    the first *fallback_depth* components are used instead, so a home directory
    reports ``/home/someone`` rather than the useless ``/``.

    Returns an empty string for a relative path: there is nothing to alias.
    """
    text = str(path).replace("\\", "/")
    if not text.startswith("/"):
        return ""

    # Stop at the first glob component – below it nothing is a real directory.
    parts = PurePosixPath(text).parts
    kept: List[str] = []
    for part in parts:
        if any(c in part for c in GLOB_CHARS):
            break
        kept.append(part)
    stem = PurePosixPath(*kept) if kept else PurePosixPath("/")

    probe = Path(stem)
    while True:
        try:
            if probe.is_dir() and os.path.ismount(probe):
                break
        except OSError:
            pass
        if probe.parent == probe:
            break
        probe = probe.parent

    found = str(probe)
    if found != "/":
        return found

    components = [p for p in parts[1:] if not any(c in p for c in GLOB_CHARS)]
    if not components:
        return ""
    return "/" + "/".join(components[:fallback_depth])


def register_mount_alias(project, path: PathLike, label: str = "") -> Optional[str]:
    """Record the mount *path* sits on as a project alias, if not already known.

    The alias maps the prefix onto itself, so resolution is unchanged here and
    the store names, in one place, every mount it depends on.  Returns the
    prefix that was added, or None if nothing was.
    """
    prefix = mount_prefix(path)
    if not prefix:
        return None
    for alias in project.config.path_aliases:
        if alias.prefix == prefix:
            return None
        # A deeper alias already covers this mount; adding the parent would
        # shadow it with a less specific rewrite.
        if prefix.startswith(alias.prefix.rstrip("/") + "/"):
            return None
    project.add_alias(prefix, [prefix], label or "recorded by link()")
    return prefix


# ---------------------------------------------------------------------------
# Source interpretation
# ---------------------------------------------------------------------------

def _is_glob(text: str) -> bool:
    return any(c in text for c in GLOB_CHARS)


def _check_modality(modality: str) -> str:
    """Resolve *modality* to a registry key, or explain what is available."""
    key = _modality.resolve_key(modality)
    if key:
        return key

    wanted = str(modality).lower()
    near = [m.key for m in _modality.list_modalities()
            if wanted in m.key or wanted in m.label.lower()]
    hint = (f" Did you mean: {', '.join(near)}?" if near else
            f" Known keys: {', '.join(m.key for m in _modality.list_modalities())}.")
    raise KeyError(
        f"Unknown modality {modality!r}.{hint} "
        f"Register a new one with pyDataOrg.core.modality.register()."
    )


def interpret_source(source: Source, key: str, *,
                     extensions: Optional[Sequence[str]] = None,
                     recursive: bool = False,
                     base: Optional[PathLike] = None) -> Dict[str, Any]:
    """Turn *source* into ``{"paths": [...], "pattern": ""}``.

    *key* is a resolved modality key; its declared extensions filter a
    directory listing.  Pass *extensions* to override that, which is how a
    folder of ``.dat`` files joins a modality that never declared ``.dat``.

    A relative *source* is relative to *base* (the project root), and the
    files a relative folder lists are recorded relative to it too — a link
    given relative stays relative, so it travels with the organizer.
    """
    spec = _modality.get(key)
    suffixes = tuple(e.lower() for e in
                     (extensions if extensions is not None
                      else (spec.extensions if spec else ())))

    if isinstance(source, (str, Path)):
        items: List[PathLike] = [source]
        single = True
    else:
        items = list(source)
        single = False

    paths: List[str] = []
    pattern = ""

    for item in items:
        text = str(item).replace("\\", "/").rstrip("/") or str(item)
        if _is_glob(text):
            if pattern:
                raise ValueError(
                    "A measurement holds one glob pattern; got two "
                    f"({pattern!r} and {text!r}). Link them as two "
                    f"measurements with different role=, or pass explicit files."
                )
            pattern = text
            continue

        relative = base is not None and is_relative(text)
        probe = (Path(base) / text) if relative else Path(text).expanduser()
        if probe.is_dir():
            if not single:
                raise ValueError(
                    f"{text!r} is a directory and cannot be mixed into a list "
                    f"of files. Link it on its own, or use link_folder()."
                )
            found = sorted(probe.rglob("*") if recursive else probe.glob("*"))
            chosen = [p for p in found if p.is_file()
                      and (not suffixes or p.suffix.lower() in suffixes)]
            if not chosen:
                what = (f" with extension {', '.join(suffixes)}" if suffixes
                        else "")
                raise FileNotFoundError(
                    f"No files{what} in {probe}. Pass extensions=[...] to "
                    f"widen it, or a glob such as {probe}/*.dat."
                )
            paths.extend(Path(os.path.relpath(p, base)).as_posix() if relative
                         else str(p) for p in chosen)
            continue

        paths.append(text)

    return {"paths": paths, "pattern": pattern}


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------

def link(project, sample_id: str, modality: str, source: Source, *,
         stage: str = STAGE_CHARACTERIZATION, role: str = "", label: str = "",
         aux: Optional[Mapping[str, str]] = None,
         meta: Optional[Mapping[str, Any]] = None,
         timestamp: Optional[str] = None,
         extensions: Optional[Sequence[str]] = None,
         recursive: bool = False,
         alias: bool = True,
         check: bool = True,
         create_sample: bool = True,
         replace_existing: bool = True,
         **extra_meta) -> Measurement:
    """Attach *source* to *sample_id* as a measurement of *modality*.

    Parameters
    ----------
    source
        A glob string (kept live), a directory (listed now), or a path or list
        of paths.  See the module docstring.
    stage, role
        Which execution the data belongs to, and a sub-label within it.  The
        pair is part of the measurement's identity, so linking twice with the
        same stage and role replaces rather than duplicates – which is what
        makes re-running a setup script safe.
    aux
        Companion files that are not data frames: ``{"wavelength": "...npy"}``.
    meta, **extra_meta
        Instrument and acquisition metadata, kept verbatim.  Keywords are
        folded into *meta*, so ``link(..., operator="RH", kV=200)`` works.
    alias
        Register the mount this data sits on as a project alias.
    check
        Warn when the link resolves to nothing *here*.  Not an error — data on
        a mount that is not up is a normal, supported state — but a typo'd
        path is far more common than an offline mount, and it is otherwise
        invisible until something downstream reads the measurement.
    extensions
        Override the modality's file extensions when listing a directory.

    Returns
    -------
    Measurement
        The measurement that was created, already attached to the sample.
    """
    key = _check_modality(modality)
    files = interpret_source(source, key, extensions=extensions,
                             recursive=recursive, base=project.root)

    sample = project.get_sample(sample_id)
    if sample is None:
        if not create_sample:
            raise KeyError(f"unknown sample {sample_id!r}")
        sample = project.add_sample(sample_id)

    payload: Dict[str, Any] = dict(meta or {})
    payload.update(extra_meta)
    # Mark the provenance: the GUI lists links separately from measurements
    # that arrived by ingest, because only a link is the user's to remove.
    payload.setdefault("linked", True)

    measurement = Measurement(
        sample_id=sample_id, modality=key, stage=stage, role=role,
        label=label, paths=files["paths"], pattern=files["pattern"],
        aux=dict(aux or {}), meta=payload, timestamp=timestamp,
    )
    sample.add_measurement(measurement, replace_existing=replace_existing)

    if alias:
        for recorded in measurement.recorded_paths()[:1]:
            register_mount_alias(project, recorded)

    if check:
        _warn_if_unresolved(project, measurement)

    return measurement


def _warn_if_unresolved(project, measurement: Measurement) -> None:
    """Say so when a fresh link matches nothing on this machine."""
    if measurement.resolve(project.resolver):
        return

    recorded = (measurement.recorded_paths() or [""])[0]
    reason = ("that pattern matches nothing yet" if measurement.pattern
              else "that path does not exist here")
    warnings.warn(
        f"{measurement.measurement_id}: {reason} — {recorded!r}. "
        f"Fine if the data is on a mount that is not up (add an alias, and "
        f"see project.availability()); check for a typo otherwise. "
        f"Pass check=False to silence this.",
        UserWarning, stacklevel=3,
    )


def link_folder(project, sample_id: str, modality: str, folder: PathLike, *,
                pattern: str = "", **kwargs) -> Measurement:
    """Link a whole folder as a **live** glob rather than a file listing.

    ``link()`` on a directory records the files that are there now, which is
    auditable but goes stale.  This records ``folder/pattern`` instead, so
    frames written after the link appear the next time the measurement is
    read — the right choice while an experiment is still running.

    *pattern* defaults to one glob per declared extension where the modality
    names exactly one, and ``*`` otherwise.
    """
    key = _check_modality(modality)
    if not pattern:
        spec = _modality.get(key)
        extensions = spec.extensions if spec else ()
        pattern = f"*{extensions[0]}" if len(extensions) == 1 else "*"

    base = str(folder).replace("\\", "/").rstrip("/")
    return link(project, sample_id, key, f"{base}/{pattern}", **kwargs)


def link_many(project, mapping: Mapping[str, Mapping[str, Any]],
              **defaults) -> List[Measurement]:
    """Link a whole campaign from one nested dict.

    ``{sample_id: {modality: source}}`` is the short form.  A modality's value
    may instead be a dict of :func:`link` keyword arguments, which is how one
    entry carries a stage or instrument metadata::

        project.link_many({
            "CuAu01": {
                "uvvis": "/mnt/specs/CuAu01/*.csv",
                "tem":   {"source": "/mnt/scope/CuAu01/", "kV": 200},
            },
            "CuAu02": {"uvvis": "/mnt/specs/CuAu02/*.csv"},
        }, stage="characterization")

    Keyword *defaults* apply to every link and are overridden per entry.
    """
    created: List[Measurement] = []
    for sample_id, per_modality in mapping.items():
        for modality, value in per_modality.items():
            options = dict(defaults)
            if isinstance(value, Mapping):
                entry = dict(value)
                source = next((entry.pop(c) for c in ("source", "paths")
                               if c in entry), None)
                if source is None:
                    raise ValueError(
                        f"{sample_id}/{modality}: a dict entry needs a "
                        f"'source' key naming the files."
                    )
                options.update(entry)
            else:
                source = value
            created.append(link(project, sample_id, modality, source, **options))
    return created


def link_table(project, rows, **defaults) -> List[Measurement]:
    """Link from a table: a DataFrame, a CSV path, or a list of dicts.

    Recognised columns are ``sample_id``, ``modality``, ``source`` (or
    ``path``/``paths``/``pattern``), ``stage``, ``role``, ``label`` and
    ``aux``; anything else becomes measurement metadata.  A spreadsheet
    maintained by whoever ran the instrument is therefore an ingest format,
    with no adapter to write.

    A ``source`` holding several paths separated by ``;`` is split, and an
    ``aux`` cell may be a JSON object — which is what lets :func:`links_table`
    write a table this function reads back unchanged.
    """
    if isinstance(rows, (str, Path)):
        import pandas as pd

        rows = pd.read_csv(rows)
    if hasattr(rows, "to_dict"):
        records = rows.to_dict("records")
    else:
        records = [dict(r) for r in rows]

    passthrough = {"stage", "role", "label", "aux"}
    created: List[Measurement] = []

    for index, record in enumerate(records):
        entry = {k: v for k, v in record.items() if _present(v)}
        try:
            sample_id = str(entry.pop("sample_id"))
            modality = str(entry.pop("modality"))
        except KeyError as exc:
            raise KeyError(
                f"row {index}: a link table needs 'sample_id' and 'modality' "
                f"columns; this row has {sorted(record)}"
            ) from exc

        source = next((entry.pop(c) for c in
                       ("source", "paths", "path", "pattern") if c in entry),
                      None)
        if source is None:
            raise KeyError(
                f"row {index} ({sample_id}/{modality}): no 'source' column.")
        if isinstance(source, str) and SEP in source:
            source = [part.strip() for part in source.split(SEP) if part.strip()]

        options = dict(defaults)
        options.update({k: v for k, v in entry.items() if k in passthrough})
        if isinstance(options.get("aux"), str):
            options["aux"] = json.loads(options["aux"])

        extra = {k: v for k, v in entry.items() if k not in passthrough}
        extra.pop("linked", None)       # provenance, re-added by link()
        created.append(link(project, sample_id, modality, source,
                            meta=extra or None, **options))
    return created


def links_table(project, sample_ids: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """Describe every link as a row :func:`link_table` can read back.

    This is the export half of the round trip, and the reason it exists is
    that a spreadsheet is a better editor than a form: export the links, fix
    the forty rows where the instrument wrote the sample id with a different
    separator, re-import.

    Each row carries the measurement back in the form it was recorded, so what
    comes out can be fed straight back in:

    * a pattern exports as that pattern, and stays live;
    * explicit paths export as their **folder** when listing that folder would
      reproduce them exactly, and as a ``;``-joined list when it would not —
      so a re-import can never quietly link a different set of files;
    * ``aux`` becomes JSON, and metadata becomes one column per key.
    """
    wanted = set(sample_ids) if sample_ids else None
    rows: List[Dict[str, Any]] = []

    for sample in project.sorted_samples():
        if wanted is not None and sample.sample_id not in wanted:
            continue
        for measurement in sample.measurements:
            row: Dict[str, Any] = {
                "sample_id": sample.sample_id,
                "modality": measurement.modality,
                "source": _export_source(measurement, base=project.root),
                "stage": measurement.stage,
                "role": measurement.role,
            }
            if measurement.aux:
                row["aux"] = json.dumps(measurement.aux)
            for key, value in measurement.meta.items():
                if key == "linked" or isinstance(value, (dict, list)):
                    continue
                row.setdefault(key, value)
            rows.append(row)
    return rows


def _export_source(measurement, base: Optional[PathLike] = None) -> str:
    """The shortest form of a measurement's files that re-imports identically."""
    if measurement.pattern:
        return measurement.pattern
    if not measurement.paths:
        return ""
    if len(measurement.paths) == 1:
        return measurement.paths[0]

    parents = {str(Path(p).parent) for p in measurement.paths}
    if len(parents) == 1:
        folder = parents.pop()
        try:
            listed = interpret_source(folder, measurement.modality,
                                      base=base)["paths"]
        except (FileNotFoundError, OSError):
            listed = []
        if listed == list(measurement.paths):
            return folder
    return SEP.join(measurement.paths)


def _present(value: Any) -> bool:
    """False for the empty cells pandas leaves behind (NaN, None, '')."""
    if value is None:
        return False
    if isinstance(value, float) and value != value:     # NaN
        return False
    return not (isinstance(value, str) and not value.strip())


def unlink(project, sample_id: str, modality: str = "", stage: str = "",
           role: str = "") -> List[str]:
    """Remove matching measurements from a sample; returns the ids dropped.

    With no filters every measurement of the sample goes, which is the point
    when a whole session turns out to have been mislabelled.  Only the links
    are removed — the files are not touched.
    """
    sample = project.get_sample(sample_id)
    if sample is None:
        raise KeyError(f"unknown sample {sample_id!r}")

    doomed = {m.measurement_id for m in
              sample.get_measurements(modality=modality, stage=stage, role=role)}
    sample.measurements = [m for m in sample.measurements
                           if m.measurement_id not in doomed]
    return sorted(doomed)


__all__ = [
    "link", "link_folder", "link_many", "link_table", "links_table", "unlink",
    "mount_prefix", "register_mount_alias", "interpret_source", "SEP",
]
