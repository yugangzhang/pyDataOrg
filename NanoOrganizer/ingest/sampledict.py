#!/usr/bin/env python3
"""
Adapter: sample-keyed Python dictionaries → :class:`Sample` records.

This adapter is deliberately generic.  It knows nothing about the chemistry; it knows that a record is a nested dictionary, that some of
its sub-dictionaries describe *files*, and that the rest are parameters worth
keeping verbatim.  A project with entirely different chemistry ingests through
the same code path.

Three things are recovered from each record:

**Stage**
    The dict variable name gives the stage label (``Synthesis_dict`` →
    ``synthesis``).  Run provenance is promoted from a ``*_batch`` sub-dict if
    one exists, so status, run id and timings become sortable columns.

**Measurements**
    Any sub-dictionary holding a glob, a path list, or path-valued ``*_file``
    entries becomes a :class:`Measurement`.  Its modality is read from the
    sub-dictionary's own name (``UV_Catalysis_data`` → ``uvvis``).

**Parameters**
    Everything else is stored unchanged in ``Stage.params`` and flattened into
    dotted columns later.  Nothing is dropped, so an unrecognised field is
    still filterable.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from NanoOrganizer.core import modality as _modality
from NanoOrganizer.core.schema import Measurement, Sample, Stage
from NanoOrganizer.ingest import pydict

# Keys whose value is a glob pattern.
_GLOB_SUFFIX = "_glob"
_GLOB_KEYS = {"glob", "pattern", "file_pattern"}

# Keys whose value is a list of paths.
_PATHLIST_KEYS = {"file_paths", "files", "paths", "filenames", "file_list"}

# Keys that name a directory holding the data.
_DIR_KEYS = {"data_directory", "directory", "folder", "data_dir", "run_directory"}

# Timestamp keys, best first.
_TIME_KEYS = (
    "first_spectrum_at", "first_kinetic_spectrum_at", "started_at",
    "run_started_at", "acquired_at", "timestamp", "date",
)

# Sub-dict name tokens that never denote a modality, so they are not tried.
_STOPWORDS = {
    "data", "measurement", "measurements", "plan", "file", "files", "info",
    "record", "records", "raw", "reduced", "result", "results", "run",
}

_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _tokens(name: str) -> List[str]:
    """Split ``"UV_Catalysis_data"`` / ``"uvVisData"`` into lowercase tokens."""
    spaced = _CAMEL_RE.sub("_", str(name))
    return [t for t in _TOKEN_RE.split(spaced) if t]


def _looks_like_path(value: Any) -> bool:
    """True for a string that carries directory structure, not a bare name."""
    return isinstance(value, str) and ("/" in value or "\\" in value)


def modality_from_name(name: str, fallback: str = "") -> str:
    """Infer a modality key from a sub-dictionary or folder name.

    Tries the whole name first, then each token, skipping generic words so
    that ``"UV_Catalysis_data"`` resolves on ``"uv"`` rather than failing.
    """
    direct = _modality.resolve_key(name)
    if direct:
        return direct
    tokens = _tokens(name)
    joined = "_".join(t for t in tokens if t.lower() not in _STOPWORDS)
    if joined:
        direct = _modality.resolve_key(joined)
        if direct:
            return direct
    for token in tokens:
        if token.lower() in _STOPWORDS:
            continue
        resolved = _modality.resolve_key(token)
        if resolved:
            return resolved
    return fallback


def _extract_files(block: Dict[str, Any]) -> Tuple[List[str], str, Dict[str, str]]:
    """Pull explicit paths, a glob, and companion files out of *block*.

    Returns ``(paths, pattern, aux)``.  ``*_file`` entries only count when the
    value looks like a path: a record that stores ``"first_spectrum_file":
    "run_water_s00.npy"`` is naming a file inside a directory, not locating it.
    """
    paths: List[str] = []
    pattern = ""
    aux: Dict[str, str] = {}

    for key, value in block.items():
        lowered = str(key).lower()

        if lowered in _PATHLIST_KEYS and isinstance(value, (list, tuple)):
            paths.extend(str(v) for v in value if v)
            continue

        if not isinstance(value, str) or not value:
            continue

        if lowered.endswith(_GLOB_SUFFIX) or lowered in _GLOB_KEYS:
            if not pattern:
                pattern = value
            continue

        if lowered.endswith("_file") or lowered.endswith("_path"):
            if _looks_like_path(value):
                aux[str(key)] = value
            continue

    return paths, pattern, aux


def _is_measurement_block(block: Dict[str, Any]) -> bool:
    """True if *block* references data files rather than only parameters."""
    paths, pattern, aux = _extract_files(block)
    if paths or pattern:
        return True
    # A directory plus companion files is still a measurement; a lone
    # ``run_record_path`` in a batch block is not.
    has_dir = any(str(k).lower() in _DIR_KEYS for k in block)
    data_aux = [k for k in aux if not str(k).lower().startswith("run_record")
                and not str(k).lower().startswith("manifest")]
    return bool(has_dir and data_aux)


def _timestamp(block: Dict[str, Any]) -> Optional[str]:
    for key in _TIME_KEYS:
        value = block.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _find_measurement_blocks(record: Dict[str, Any], max_depth: int = 3,
                             ) -> List[Tuple[str, Dict[str, Any]]]:
    """Walk *record* and return ``(name, block)`` for each measurement block."""
    found: List[Tuple[str, Dict[str, Any]]] = []

    def walk(node: Any, name: str, depth: int):
        if not isinstance(node, dict) or depth > max_depth:
            return
        if name and _is_measurement_block(node):
            found.append((name, node))
            return  # a measurement block is a leaf; do not split it further
        for key, value in node.items():
            if isinstance(value, dict):
                walk(value, str(key), depth + 1)

    walk(record, "", 0)
    return found


def _promote_batch(record: Dict[str, Any], stage_id: str) -> Dict[str, Any]:
    """Find the batch/provenance sub-dict and return its promoted fields."""
    candidates = [
        value for key, value in record.items()
        if isinstance(value, dict) and (
            str(key).lower().endswith("_batch") or str(key).lower() == "batch"
        )
    ]
    # Fall back to a block that merely carries run provenance.
    if not candidates:
        candidates = [
            value for value in record.values()
            if isinstance(value, dict) and "run_id" in value and "status" in value
        ]
    if not candidates:
        return {}

    batch = candidates[0]
    error = batch.get("error")
    status = str(batch.get("status") or "")
    if batch.get("aborted") and status not in {"error", "aborted"}:
        status = "aborted"
    # Some schemas keep the run id with the data block rather than the batch
    # block (a batch of one still has a run id), so look wider before giving up.
    run_id = str(batch.get("run_id") or "") or _find_nested(record, "run_id")
    return {
        "run_id": run_id,
        "batch_tag": str(batch.get("batch_tag") or batch.get("batch_name")
                         or batch.get("case_id") or ""),
        "campaign": str(batch.get("campaign") or ""),
        "status": status,
        "error": error if isinstance(error, str) else None,
        "started_at": batch.get("started_at") or batch.get("run_started_at"),
        "ended_at": batch.get("ended_at") or batch.get("run_ended_at"),
        "run_time_s": _as_float(batch.get("run_time_s")),
    }


def _find_nested(node: Any, key: str, max_depth: int = 3, _depth: int = 0) -> str:
    """Breadth-first search for the first non-empty string value under *key*."""
    if not isinstance(node, dict) or _depth > max_depth:
        return ""
    value = node.get(key)
    if isinstance(value, str) and value:
        return value
    for child in node.values():
        if isinstance(child, dict):
            found = _find_nested(child, key, max_depth, _depth + 1)
            if found:
                return found
    return ""


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def record_to_sample(sample_id: str, record: Dict[str, Any], stage_id: str,
                     source: str = "",
                     modality_map: Optional[Dict[str, str]] = None) -> Sample:
    """Convert one authored record into a :class:`Sample` with a single stage."""
    sample = Sample(sample_id=sample_id)

    stage = Stage(stage_id=stage_id, kind=stage_id, params=dict(record),
                  source=source, **_promote_batch(record, stage_id))
    sample.add_stage(stage)

    note = record.get("note") or record.get("notes")
    if isinstance(note, str) and note:
        sample.notes = note

    overrides = {k.lower(): v for k, v in (modality_map or {}).items()}

    for name, block in _find_measurement_blocks(record):
        # Precedence: what the record says, then a caller's override, then the
        # block's own name. An explicit ``modality`` key is the reliable route
        # — a block called "spectra" names no technique, and guessing from the
        # name only works when the author happened to put one there.
        key = (_modality.resolve_key(str(block.get("modality", "")))
               or overrides.get(name.lower())
               or modality_from_name(name))
        if not key:
            continue
        paths, pattern, aux = _extract_files(block)
        if not paths and not pattern:
            # Directory + companion files: build a pattern from the directory.
            directory = next(
                (str(v) for k, v in block.items()
                 if str(k).lower() in _DIR_KEYS and _looks_like_path(v)),
                "",
            )
            if not directory:
                continue
            pattern = f"{directory}/*"

        role = _role_from_name(name, stage_id)
        sample.add_measurement(Measurement(
            sample_id=sample_id, modality=key, stage=stage_id, role=role,
            paths=paths, pattern=pattern, aux=aux, meta=dict(block),
            timestamp=_timestamp(block),
        ))

    return sample


def _role_from_name(block_name: str, stage_id: str) -> str:
    """Keep the distinguishing part of a block name as the measurement role.

    ``UV_Catalysis_data`` inside the ``catalysis`` stage carries no extra
    information, so the role stays empty; ``UV_Kinetic_data`` becomes
    ``kinetic``.
    """
    tokens = [t.lower() for t in _tokens(block_name)]
    modality_key = modality_from_name(block_name)
    modality_tokens = set(_tokens(modality_key or "")) | {modality_key or ""}
    drop = _STOPWORDS | {stage_id.lower()} | {t.lower() for t in modality_tokens if t}
    kept = [t for t in tokens if t not in drop and not _modality.resolve_key(t)]
    # ``SAXS2D`` splits into ``saxs2`` + ``d``, neither of which resolves on its
    # own, so the leftovers would become a role of "saxs2-d" — the technique
    # name wearing a disguise. If the leftovers spell the modality, there is no
    # role here.
    if kept and modality_key and _modality.resolve_key("".join(kept)) == modality_key:
        return ""
    return "-".join(kept)


# ---------------------------------------------------------------------------
# Adapter entry point
# ---------------------------------------------------------------------------

def ingest(path: Path, project=None, stage: str = "", dicts: Sequence[str] = (),
           modality_map: Optional[Dict[str, str]] = None,
           **_ignored) -> List[Sample]:
    """Read every sample-keyed dict in *path* and return merged samples.

    Parameters
    ----------
    path : Path
        A ``.py`` metadata module.
    stage : str, optional
        Force a stage label for every dict in the file.  By default each dict
        gets its own stage inferred from its variable name, which is what makes
        one file able to describe several stages.
    dicts : sequence of str, optional
        Only ingest these dict variable names.
    modality_map : dict, optional
        Explicit ``{block_name: modality_key}`` overrides for records whose
        sub-dictionary names do not reveal the technique.
    """
    path = Path(path)
    found = pydict.find_sample_dicts(path)
    # Provenance names the file relative to the project when it is inside
    # it, like every other path the store keeps.
    shown = path
    root = getattr(project, "root", None)
    if root is not None:
        try:
            shown = Path(path).absolute().relative_to(Path(root)).as_posix()
        except ValueError:
            pass
    if dicts:
        wanted = {d.lower() for d in dicts}
        found = {k: v for k, v in found.items() if k.lower() in wanted}
    if not found:
        return []

    merged: Dict[str, Sample] = {}
    for dict_name, records in found.items():
        stage_id = stage or pydict.stage_from_name(dict_name) \
            or pydict.stage_from_filename(path, default="metadata")
        for sample_id, record in records.items():
            if not isinstance(record, dict):
                continue
            sample = record_to_sample(
                sample_id, record, stage_id,
                source=f"{shown}::{dict_name}", modality_map=modality_map,
            )
            existing = merged.get(sample_id)
            if existing is None:
                merged[sample_id] = sample
                continue
            for stage_obj in sample.stages.values():
                existing.add_stage(stage_obj)
            for measurement in sample.measurements:
                existing.add_measurement(measurement)
            if sample.notes and sample.notes not in existing.notes:
                existing.notes = "\n".join(
                    filter(None, [existing.notes, sample.notes])
                )

    return [merged[k] for k in sorted(merged)]


def ingest_mapping(records: Dict[str, Any], stage: str = "metadata",
                   source: str = "", modality_map: Optional[Dict[str, str]] = None,
                   ) -> List[Sample]:
    """Read a live ``{sample_id: record}`` dict — no file involved.

    The file-based adapter exists because metadata is usually *authored* at
    the instrument and must not be edited in place.  A dict held in a notebook
    is the other case: it is being written right now, and the loop is edit it,
    ingest, look, edit again.  Both end at :func:`record_to_sample`, so a
    record behaves the same whichever way it arrived.

    Entries whose value is not a dict are skipped rather than raising, since a
    metadata module habitually keeps a stray constant beside its records.
    """
    out: List[Sample] = []
    for sample_id, record in records.items():
        if not isinstance(record, dict):
            continue
        out.append(record_to_sample(str(sample_id), record, stage,
                                    source=source or f"dict::{stage}",
                                    modality_map=modality_map))
    return out


def detect(path: Path) -> bool:
    """True if this adapter can read *path*."""
    return pydict.looks_like_metadata_module(Path(path))


__all__ = ["ingest", "ingest_mapping", "detect", "record_to_sample",
           "modality_from_name"]
