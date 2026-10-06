#!/usr/bin/env python3
"""
Persisting analysis results – so a fit can be looked at again without refitting.

:class:`~NanoOrganizer.analysis.result.AnalysisResult` deliberately keeps its
three kinds of output apart, and they persist in two different places for the
same reason:

``values``
    scalars, written onto the sample as ``derived.*`` and saved with the
    store.  Already round-trips; nothing here is needed for them.

``curves`` and ``diagnostics``
    the fitted line, the residuals, the window and the R².  These are arrays
    and they stay **out** of the store — a sample store that accumulates
    spectra stops being readable, and it is the one file you want to be able
    to open in a text editor.

So a result is written beside the organiser as its own file and *linked back*
like any other data.  That is the whole trick: a fit is a measurement of a
measurement, so it does not need a second mechanism.  Reopening the organiser
months later, ``org.result("CuAu05", "peak_fit")`` reads the file and
``org.plot_result(...)`` redraws the fit over its data, with no analysis run
and no dependency on the code that produced it still behaving the same way.

The file is a plain ``.npz``: one entry per curve, plus a JSON blob under
``__meta__``.  It is readable with :func:`numpy.load` alone, which matters
because an archive format nobody else can open is not an archive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Union

import numpy as np

from NanoOrganizer.analysis.result import AnalysisResult

#: Where results go, relative to the organiser's store, unless told otherwise.
RESULTS_DIR = "results"

#: npz entry holding the JSON sidecar.
META_KEY = "__meta__"

SUFFIX = ".result.npz"


def result_filename(result: AnalysisResult) -> str:
    """A name that says what this is without having to open it."""
    parts = [result.sample_id or "sample", result.analysis or "analysis"]
    measurement = result.measurement_id or ""
    # The measurement id already starts with the sample id; keep the tail,
    # which is what distinguishes two fits of one sample.
    tail = measurement.split(":", 1)[1] if ":" in measurement else ""
    if tail:
        parts.append(tail.replace(":", "-"))
    return "__".join(p.replace("/", "-") for p in parts) + SUFFIX


def save_result(result: AnalysisResult, folder: Union[str, Path],
                name: str = "") -> Path:
    """Write *result* to ``folder`` and return the path.

    Non-array curves are dropped rather than pickled: ``allow_pickle`` turns a
    data file into executable code, and a result file is exactly the kind of
    thing that gets emailed around.
    """
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name or result_filename(result))

    arrays: Dict[str, np.ndarray] = {}
    skipped: List[str] = []
    for key, value in result.curves.items():
        array = np.asarray(value)
        if array.dtype == object:
            skipped.append(key)
            continue
        arrays[str(key)] = array

    meta = {
        "analysis": result.analysis,
        "sample_id": result.sample_id,
        "measurement_id": result.measurement_id,
        "values": result.values,
        "errors": result.errors,
        "units": result.units,
        "diagnostics": result.diagnostics,
        "ok": result.ok,
        "message": result.message,
        "curves": list(arrays),
        "dropped_curves": skipped,
    }
    arrays[META_KEY] = np.frombuffer(
        json.dumps(meta, default=str).encode("utf-8"), dtype=np.uint8)

    np.savez_compressed(path, **arrays)
    return path


def load_result(path: Union[str, Path]) -> AnalysisResult:
    """Read a result written by :func:`save_result`."""
    path = Path(path).expanduser()
    with np.load(path, allow_pickle=False) as bundle:
        if META_KEY not in bundle:
            raise ValueError(
                f"{path.name} is not a NanoOrganizer result file: no "
                f"{META_KEY!r} entry. It may be plain data — link it as a "
                f"measurement instead."
            )
        meta = json.loads(bytes(bundle[META_KEY]).decode("utf-8"))
        curves = {key: np.asarray(bundle[key]) for key in bundle.files
                  if key != META_KEY}

    return AnalysisResult(
        analysis=meta.get("analysis", ""),
        sample_id=meta.get("sample_id", ""),
        measurement_id=meta.get("measurement_id", ""),
        values=meta.get("values", {}),
        errors=meta.get("errors", {}),
        units=meta.get("units", {}),
        curves=curves,
        diagnostics=meta.get("diagnostics", {}),
        ok=bool(meta.get("ok", True)),
        message=meta.get("message", ""),
    )


def peek(path: Union[str, Path]) -> Dict[str, Any]:
    """Read a result's metadata without loading its arrays."""
    path = Path(path).expanduser()
    with np.load(path, allow_pickle=False) as bundle:
        if META_KEY not in bundle:
            return {}
        return json.loads(bytes(bundle[META_KEY]).decode("utf-8"))


__all__ = ["save_result", "load_result", "peek", "result_filename",
           "RESULTS_DIR", "SUFFIX"]
