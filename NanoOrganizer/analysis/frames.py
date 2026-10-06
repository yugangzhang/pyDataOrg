#!/usr/bin/env python3
"""
Frame-name grammars – reading the clock out of a spectrum filename.

Acquisition software encodes the frame's place in a run in its filename, and
every instrument spells it differently::

    run_b01_t00000s_T94C.npy       batch b01, 0 s, 94 C
    scan_0042.dat                  frame index only
    sample_kin_t00060s.npy         60 s into a kinetic series

A *grammar* turns a filename into a :class:`FrameInfo`. Two general ones are
registered below; an instrument with its own convention adds a
:func:`register_grammar` call and nothing downstream changes.

The measurement's recorded file list, not a folder scan, decides which frames
belong to a sample — the metadata is the authority on that, and two samples
routinely share one run directory (``r01``/``r02``/``r03`` side by side).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from NanoOrganizer.analysis.series import FrameSeries

KINETIC = "kinetic"
STATIC = "static"


@dataclass
class FrameInfo:
    """What a filename says about one frame."""

    name: str = ""
    batch: str = ""
    t_s: float = float("nan")
    T_c: float = float("nan")
    kind: str = KINETIC
    reagent: str = ""
    scan: int = -1

    @property
    def timed(self) -> bool:
        """True if the name carried a clock, i.e. it belongs on a time axis."""
        return bool(np.isfinite(self.t_s))


def _temperature(text: Optional[str]) -> float:
    """``'94'`` → 94.0; ``'na'`` (not recorded) → NaN."""
    if not text or text.lower() == "na":
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


@dataclass
class FrameGrammar:
    """An ordered set of patterns that parse one rig's filenames."""

    key: str
    label: str
    patterns: Tuple[re.Pattern, ...] = ()
    batch_prefix: str = ""

    def parse(self, name: str) -> Optional[FrameInfo]:
        """Return a :class:`FrameInfo`, or None if no pattern matches."""
        stem = Path(str(name)).name
        for pattern in self.patterns:
            match = pattern.search(stem)
            if not match:
                continue
            groups = match.groupdict()

            batch = groups.get("batch") or ""
            if batch and self.batch_prefix and not batch.startswith(self.batch_prefix):
                batch = f"{self.batch_prefix}{batch}"

            time_text = groups.get("t")
            scan_text = groups.get("scan")
            if time_text is not None:
                return FrameInfo(
                    name=stem, batch=batch.lower(), t_s=float(time_text),
                    T_c=_temperature(groups.get("T")), kind=KINETIC,
                )
            return FrameInfo(
                name=stem, batch=batch.lower(),
                T_c=_temperature(groups.get("T")), kind=STATIC,
                reagent=(groups.get("reagent") or "").strip("_"),
                scan=int(scan_text) if scan_text is not None else -1,
            )
        return None

    def matches(self, names: Iterable[str]) -> int:
        """How many of *names* this grammar can parse."""
        return sum(1 for n in names if self.parse(n) is not None)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GRAMMAR_REGISTRY: Dict[str, FrameGrammar] = {}


def register_grammar(grammar: FrameGrammar, overwrite: bool = False) -> FrameGrammar:
    if grammar.key in GRAMMAR_REGISTRY and not overwrite:
        raise ValueError(f"Frame grammar {grammar.key!r} is already registered")
    GRAMMAR_REGISTRY[grammar.key] = grammar
    return grammar


register_grammar(FrameGrammar(
    key="batch_time",
    label="Batch and time (…_b01_t00000s_T94C.npy)",
    patterns=(
        re.compile(
            r"_(?P<batch>[a-zA-Z]\d+)_t(?P<t>\d+(?:\.\d+)?)s"
            r"(?:_T(?P<T>na|-?\d+(?:\.\d+)?)C?)?"
        ),
    ),
))

register_grammar(FrameGrammar(
    key="time_only",
    label="Time only (…_t00060s.npy)",
    patterns=(
        re.compile(r"_t(?P<t>\d+(?:\.\d+)?)s"
                   r"(?:_T(?P<T>na|-?\d+(?:\.\d+)?)C?)?"),
    ),
))

register_grammar(FrameGrammar(
    key="frame_index",
    label="Frame index (…_0042.npy)",
    patterns=(
        re.compile(r"(?:^|[_\-])(?P<t>\d{3,})(?:\.[A-Za-z0-9]+)?$"),
    ),
))


def detect_grammar(names: Sequence[str],
                   default: Optional[str] = None) -> Optional[FrameGrammar]:
    """Return the registered grammar that parses the most of *names*.

    A grammar must parse at least half the names to be accepted, so a
    coincidental match on a stray file cannot select the wrong rig.
    """
    names = [str(n) for n in names]
    if not names:
        return GRAMMAR_REGISTRY.get(default) if default else None

    scored = [(g.matches(names), g) for g in GRAMMAR_REGISTRY.values()]
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    if best_score * 2 >= len(names):
        return best
    return GRAMMAR_REGISTRY.get(default) if default else None


# ---------------------------------------------------------------------------
# Measurement → FrameSeries
# ---------------------------------------------------------------------------

def load_series(measurement, resolver, *, kind: str = KINETIC,
                grammar: Optional[FrameGrammar] = None,
                crop: Optional[Tuple[float, float]] = None,
                wavelength=None):
    """Read a measurement's frames into a :class:`FrameSeries`.

    Parameters
    ----------
    measurement : Measurement
        Supplies the file list; its ``aux["wavelength_file"]`` supplies the axis.
    resolver : PathResolver
        Maps the recorded paths onto this machine.
    kind : {"kinetic", "static", "all"}
        Which frames to keep.  Static reference scans have no clock, so mixing
        them into a kinetic series would put frames at a time they were never
        taken at.
    crop : (lo, hi), optional
        Wavelength range in nm.  Worth applying: the ends of the spectrometer's
        range are noise and they ruin every auto-scaled plot.

    Raises
    ------
    FileNotFoundError
        If no frames resolve, or no wavelength axis can be found.
    """
    paths = measurement.resolve(resolver)
    if not paths:
        raise FileNotFoundError(
            f"No frames resolve for {measurement.measurement_id}. "
            f"Check the project path aliases."
        )

    if grammar is None:
        grammar = detect_grammar([p.name for p in paths])
    if grammar is None:
        raise ValueError(
            f"No frame grammar parses {paths[0].name!r}. "
            f"Register one with analysis.frames.register_grammar()."
        )

    rows: List[Tuple[FrameInfo, Path]] = []
    for path in paths:
        info = grammar.parse(path.name)
        if info is None:
            continue
        if kind != "all" and info.kind != kind:
            continue
        rows.append((info, path))

    if not rows:
        raise FileNotFoundError(
            f"{measurement.measurement_id}: no {kind} frames among "
            f"{len(paths)} files (grammar={grammar.key})"
        )

    # Kinetic frames sort by their clock; static scans by reagent then scan
    # index, which is the order they were taken in.
    if kind == STATIC:
        rows.sort(key=lambda r: (r[0].reagent, r[0].scan))
        times = np.arange(len(rows), dtype=float)
        t_zero = "static scan index"
    else:
        rows.sort(key=lambda r: r[0].t_s)
        times = np.array([r[0].t_s for r in rows], dtype=float)
        t_zero = "file"

    axis = _wavelength_axis(measurement, resolver, wavelength)

    matrix = np.empty((len(rows), axis.size), dtype=float)
    for index, (_, path) in enumerate(rows):
        frame = np.load(path)
        if frame.size != axis.size:
            raise ValueError(
                f"{path.name} has {frame.size} points but the wavelength axis "
                f"has {axis.size}"
            )
        matrix[index] = frame

    temps = np.array([r[0].T_c for r in rows], dtype=float)
    series = FrameSeries(
        x=axis,
        values=matrix,
        t_s=times,
        t_zero=t_zero,
        names=tuple(r[1].name for r in rows),
        T_c=None if np.all(np.isnan(temps)) else temps,
        meta={
            "measurement_id": measurement.measurement_id,
            "sample_id": measurement.sample_id,
            "stage": measurement.stage,
            "batch": rows[0][0].batch,
            "grammar": grammar.key,
            "kind": kind,
            "reagent": np.array([r[0].reagent for r in rows]),
        },
    )
    if crop is not None:
        series = series.crop(*crop)
    return series


def _wavelength_axis(measurement, resolver, override=None) -> np.ndarray:
    """Find the wavelength axis for *measurement*."""
    if override is not None:
        return np.asarray(override, dtype=float)

    aux = measurement.resolve_aux(resolver)
    for key in ("wavelength_file", "wavelength", "axis_file"):
        if key in aux:
            return np.load(aux[key]).astype(float)

    # Fall back to a ``*wave*.npy`` sitting beside the frames.
    paths = measurement.resolve(resolver)
    if paths:
        folder = paths[0].parent
        hits = sorted(p for p in folder.glob("*.npy") if "wave" in p.name.lower())
        if hits:
            return np.load(hits[0]).astype(float)

    raise FileNotFoundError(
        f"No wavelength axis for {measurement.measurement_id}: no resolvable "
        f"'wavelength_file' in aux and no '*wave*.npy' beside the frames."
    )


# ---------------------------------------------------------------------------
# The layer below a measurement: its individual frames
# ---------------------------------------------------------------------------

def frame_table(measurement, resolver, *,
                grammar: Optional[FrameGrammar] = None) -> List[Dict[str, Any]]:
    """Describe every frame of *measurement*: one row per file.

    A measurement is rarely one number — it is forty spectra taken while the
    reaction ran, or a micrograph series, or a temperature ramp.  This is that
    layer, made addressable: each row carries the frame's index, its file, and
    whatever the filename admitted about *when* (``t_s``) and *how hot*
    (``T_c``) it was taken.

    Names that no registered grammar parses still get a row, with ``t_s`` and
    ``T_c`` as NaN — an unparsed frame is listed, never dropped.
    """
    paths = measurement.resolve(resolver)
    if not paths:
        return []

    names = [p.name for p in paths]
    grammar = grammar or detect_grammar(names)

    rows: List[Dict[str, Any]] = []
    for index, path in enumerate(paths):
        info = grammar.parse(path.name) if grammar else None
        rows.append({
            "index": index,
            "file": path.name,
            "path": str(path),
            "t_s": info.t_s if info else float("nan"),
            "T_c": info.T_c if info else float("nan"),
            "batch": info.batch if info else "",
            "scan": info.scan if info else -1,
            "kind": info.kind if info else "",
        })
    return rows


def pick_frame(rows: Sequence[Dict[str, Any]], *, frame: Optional[int] = None,
               t: Optional[float] = None, T: Optional[float] = None,
               file: str = "") -> int:
    """Return the index of the frame *frame*/*t*/*T*/*file* asks for.

    ``t`` and ``T`` select the **nearest** recorded value rather than an exact
    one, because an acquisition clock never lands on a round number; ``frame``
    is a plain index and ``file`` matches a name or a substring of one.  Later
    arguments narrow earlier ones, so ``t=600, T=90`` means *the frame closest
    to 600 s among those recorded at about 90 °C*.
    """
    if not rows:
        raise IndexError("the measurement has no readable frames")

    pool = list(rows)

    if T is not None:
        valid = [r for r in pool if r["T_c"] == r["T_c"]]
        if not valid:
            raise KeyError("no frame carries a temperature in its name; "
                           "select by frame= or t= instead")
        nearest = min(abs(r["T_c"] - float(T)) for r in valid)
        pool = [r for r in valid if abs(r["T_c"] - float(T)) == nearest]

    if t is not None:
        valid = [r for r in pool if r["t_s"] == r["t_s"]]
        if not valid:
            raise KeyError("no frame carries a time in its name; "
                           "select by frame= instead")
        pool = [min(valid, key=lambda r: abs(r["t_s"] - float(t)))]

    if file:
        hits = [r for r in pool if r["file"] == file] or \
               [r for r in pool if file in r["file"]]
        if not hits:
            raise KeyError(f"no frame named {file!r}")
        pool = hits

    if frame is not None:
        if T is None and t is None and not file:
            if not -len(rows) <= frame < len(rows):
                raise IndexError(f"frame {frame} of {len(rows)}")
            return int(rows[frame]["index"])
        pool = [pool[frame]]

    return int(pool[0]["index"])


__all__ = [
    "FrameInfo", "FrameGrammar", "GRAMMAR_REGISTRY", "register_grammar",
    "detect_grammar", "load_series", "frame_table", "pick_frame",
    "KINETIC", "STATIC",
]
