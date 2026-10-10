#!/usr/bin/env python3
"""
A campaign as one table: inputs → results → objectives, one row per sample.

The organizer's sample table is wide — every recorded field, dotted — and
kept analysis results live in files. The questions a campaign asks ("which
recipe is best, and is the search still improving?") need perhaps twenty of
those numbers, under names a person can type. A :class:`Campaign` names them:

=============  ===============================================================
``input``      what the experimenter (or an optimiser) chooses — a recipe
               variable, a composition, a temperature
``context``    recorded alongside but not chosen — batch, status, timestamps
``protocol``   how a measurement was made; rows that differ here are not
               comparable
``result``     what was measured or derived about the sample
``objective``  a result the campaign is trying to push one way
=============  ===============================================================

A column's *source* is a sample-table column (``synthesis.conditions.T_C``,
``derived.peak1_center``) or ``analysis:value`` — a value read from that
analysis' kept result files (see :func:`kept_values`). ::

    from pyDataOrg.campaign import Campaign, Column, Objective

    spec = Campaign("my-screen", columns=[
        Column("x", "synthesis.composition.x", "fraction x", kind="input"),
        Column("rate", "testing.performance.rate", "rate", "1/s",
               kind="objective"),
    ], objectives=[Objective("rate", maximize=True)], bounds={"x": (0, 1)})

    frame = spec.table(org)                   # adapter: the open organizer
    ranked = spec.rank(frame)                 # kernel: a plain frame in, out

Kernels (:func:`campaign_frame`, :func:`pareto_mask`, :func:`rank`,
:func:`best_so_far` …) take arrays or a plain frame and touch no files; the
functions that read an organizer are :func:`kept_values` and
:func:`campaign_table`. Project packages register their campaign with
:func:`register_campaign`, and the GUI's Campaign and Next-experiments pages
offer it by name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

KINDS = ("input", "context", "protocol", "result", "objective")
NUMERIC_KINDS = ("input", "result", "objective")
SAMPLE = "sample"


@dataclass(frozen=True)
class Column:
    """A short campaign column and where it comes from."""

    name: str
    source: str
    label: str = ""
    unit: str = ""
    kind: str = "context"

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"column {self.name!r}: kind {self.kind!r} is "
                             f"not one of {', '.join(KINDS)}")

    @property
    def axis_label(self) -> str:
        text = self.label or self.name
        return f"{text} ({self.unit})" if self.unit else text


@dataclass(frozen=True)
class Objective:
    """A column and which way is better.

    *log* models it on a log10 scale when optimising — right for a positive
    quantity that varies by factors (a rate constant), wrong for a fraction.
    """

    name: str
    maximize: bool = True
    log: bool = False

    @property
    def arrow(self) -> str:
        return "↑" if self.maximize else "↓"

    def label(self, labels: Optional[Mapping[str, str]] = None) -> str:
        return f"{(labels or {}).get(self.name, self.name)} {self.arrow}"


# ---------------------------------------------------------------------------
# Kernels: plain frames in, plain frames out
# ---------------------------------------------------------------------------

def campaign_frame(table: pd.DataFrame,
                   columns: Sequence[Column]) -> pd.DataFrame:
    """Pick and rename the campaign columns from a sample table.

    A column the table does not have yet (an analysis not run) comes back
    all-NaN rather than missing, so code downstream sees one shape. Input,
    result and objective columns are made numeric.
    """
    out = pd.DataFrame(index=table.index)
    out[SAMPLE] = table["sample_id"] if "sample_id" in table else table.index
    for column in columns:
        out[column.name] = table[column.source] if column.source in table \
            else np.nan
    for column in columns:
        if column.kind in NUMERIC_KINDS:
            out[column.name] = pd.to_numeric(out[column.name], errors="coerce")
    return out.reset_index(drop=True)


def usable(frame: pd.DataFrame, names: Sequence[str]) -> pd.Series:
    """Rows where every column in *names* is a finite number."""
    if not len(names):
        return pd.Series(True, index=frame.index)
    missing = [n for n in names if n not in frame]
    if missing:
        return pd.Series(False, index=frame.index)
    block = frame[list(names)].apply(pd.to_numeric, errors="coerce")
    return pd.Series(np.isfinite(block.to_numpy(dtype=float)).all(axis=1),
                     index=frame.index)


def majority(frame: pd.DataFrame, columns: Sequence[str]) -> Dict[str, object]:
    """The combination of *columns* most rows share (e.g. the usual
    measurement protocol); ``{}`` when no row has them."""
    present = [c for c in columns if c in frame and frame[c].notna().any()]
    block = frame[present].dropna() if present else pd.DataFrame()
    if block.empty:
        return {}
    key = block.astype(str).agg("|".join, axis=1)
    row = block[key == key.value_counts().index[0]].iloc[0]
    return {c: row[c] for c in present}


def comparable(frame: pd.DataFrame, names: Sequence[str] = (), *,
               inputs: Sequence[str] = (),
               protocol: Optional[Mapping[str, object]] = None,
               protocol_columns: Sequence[str] = (),
               done: Optional[Tuple[str, str]] = None) -> pd.Series:
    """Rows whose numbers can be compared with each other.

    Every column of *inputs* and *names* a number; finished, if *done*
    (``(column, value)``) is given; and measured the same way as most rows —
    *protocol* overrides that majority (``{}`` keeps every row).
    """
    keep = usable(frame, list(inputs) + list(names))
    if done is not None and done[0] in frame:
        keep &= frame[done[0]].astype(str).eq(str(done[1]))
    if protocol is None:
        protocol = majority(frame, protocol_columns)
    for column, value in (protocol or {}).items():
        if column in frame:
            keep &= frame[column].astype(str).eq(str(value))
    return keep


def pareto_mask(values, maximize: Sequence[bool]) -> np.ndarray:
    """True for rows no other row beats on every objective.

    *values* is ``(n, m)``; rows with a NaN are never on the front.
    """
    y = np.asarray(values, dtype=float)
    if y.ndim != 2 or y.shape[1] != len(maximize):
        raise ValueError(f"values must be (n, {len(maximize)}); got {y.shape}")
    sign = np.where(np.asarray(maximize, dtype=bool), 1.0, -1.0)
    z = y * sign
    finite = np.isfinite(z).all(axis=1)
    front = finite.copy()
    for i in np.flatnonzero(finite):
        others = z[finite]
        beaten = np.any(np.all(others >= z[i], axis=1)
                        & np.any(others > z[i], axis=1))
        front[i] = not beaten
    return front


def rank(frame: pd.DataFrame, objectives: Sequence[Objective],
         weights: Optional[Sequence[float]] = None,
         inputs: Sequence[str] = ()) -> pd.DataFrame:
    """Score every row that has *inputs* and the objectives, best first.

    Each objective is rescaled to 0–1 over the rows that have it (1 = best),
    and the score is their weighted mean. A Pareto flag rides along: a high
    score with ``pareto=False`` means another row is at least as good on
    every count.
    """
    names = [o.name for o in objectives]
    keep = usable(frame, list(inputs) + names)
    out = frame.loc[keep].copy()
    if out.empty:
        out["score"] = []
        out["pareto"] = []
        return out
    w = np.ones(len(names)) if weights is None else np.asarray(weights, float)
    parts = []
    for o in objectives:
        v = out[o.name].astype(float).to_numpy()
        lo, hi = np.nanmin(v), np.nanmax(v)
        scaled = (v - lo) / (hi - lo) if hi > lo else np.ones_like(v)
        parts.append(scaled if o.maximize else 1.0 - scaled)
    out["score"] = np.average(np.vstack(parts), axis=0, weights=w)
    out["pareto"] = pareto_mask(out[names].to_numpy(dtype=float),
                                [o.maximize for o in objectives])
    return out.sort_values("score", ascending=False)


def chronological(frame: pd.DataFrame, when: str) -> pd.DataFrame:
    """The rows that have a *when* time, in the order it happened."""
    times = pd.to_datetime(frame[when], errors="coerce") if when in frame \
        else pd.Series(pd.NaT, index=frame.index)
    return frame.loc[times.notna()].assign(_t=times).sort_values("_t") \
        .drop(columns="_t")


def best_so_far(values, maximize: bool = True) -> np.ndarray:
    """Running best of a sequence (campaign progress), NaNs carried over."""
    v = np.asarray(values, dtype=float)
    out = np.full(v.shape, np.nan)
    best = np.nan
    for i, x in enumerate(v):
        if np.isfinite(x) and (not np.isfinite(best)
                               or (x > best if maximize else x < best)):
            best = x
        out[i] = best
    return out


# ---------------------------------------------------------------------------
# Adapters: read an open organizer
# ---------------------------------------------------------------------------

def kept_values(workbench, analysis: str, *,
                all_samples: bool = True) -> pd.DataFrame:
    """The values of *analysis*' kept results (files), one row per sample,
    indexed by sample id; empty when none is kept."""
    kept = workbench.results(all_samples=all_samples, analysis=analysis)
    if kept.empty:
        return pd.DataFrame()
    kept = kept[kept["readable"].astype(bool)]
    return kept.drop_duplicates("sample_id", keep="last").set_index("sample_id")


def campaign_table(workbench, columns: Sequence[Column], *,
                   all_samples: bool = True) -> pd.DataFrame:
    """The campaign table of an open organizer: its sample table plus the
    values of the kept results the columns name, through
    :func:`campaign_frame`."""
    table = workbench.table(all_samples=all_samples)
    ids = table["sample_id"] if "sample_id" in table \
        else pd.Series(table.index, index=table.index)
    wanted: Dict[str, List[str]] = {}
    for column in columns:
        if ":" in column.source:
            analysis, value = column.source.split(":", 1)
            wanted.setdefault(analysis, []).append(value)
    extra = {}
    for analysis, values in wanted.items():
        kept = kept_values(workbench, analysis, all_samples=all_samples)
        for value in values:
            if value in kept:
                extra[f"{analysis}:{value}"] = ids.map(kept[value]).to_numpy()
    if extra:
        table = pd.concat([table, pd.DataFrame(extra, index=table.index)], axis=1)
    return campaign_frame(table, columns)


# ---------------------------------------------------------------------------
# The specification
# ---------------------------------------------------------------------------

@dataclass
class Campaign:
    """Which columns a campaign reads, and what it is trying to achieve.

    *when* names a time column (for progress); *done* is ``(column, value)``
    a finished row has; *protocol* lists columns that must agree for two
    rows to be compared; *bounds* and *rounding* describe the input space
    an optimiser may propose in.
    """

    name: str
    columns: Sequence[Column]
    objectives: Sequence[Objective] = ()
    when: str = ""
    done: Optional[Tuple[str, str]] = None
    protocol: Sequence[str] = ()
    bounds: Mapping[str, Tuple[float, float]] = field(default_factory=dict)
    rounding: Mapping[str, float] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self):
        names = [c.name for c in self.columns]
        duplicated = sorted({n for n in names if names.count(n) > 1})
        if duplicated:
            raise ValueError(f"campaign {self.name!r}: duplicate columns "
                             f"{', '.join(duplicated)}")
        unknown = [o.name for o in self.objectives if o.name not in names]
        if unknown:
            raise ValueError(f"campaign {self.name!r}: objectives "
                             f"{', '.join(unknown)} are not columns")

    # -- names ------------------------------------------------------------

    def names(self, *kinds: str) -> List[str]:
        """Column names of the given kinds (all, if none given)."""
        return [c.name for c in self.columns if not kinds or c.kind in kinds]

    @property
    def inputs(self) -> List[str]:
        return self.names("input")

    @property
    def labels(self) -> Dict[str, str]:
        """``{name: axis label}`` — what the plots take as *labels*."""
        return {c.name: c.axis_label for c in self.columns}

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(f"campaign {self.name!r} has no column {name!r}")

    def objective(self, name: str) -> Objective:
        """The declared :class:`Objective` called *name*, else one that
        maximises it."""
        for o in self.objectives:
            if o.name == name:
                return o
        return Objective(name)

    # -- the table --------------------------------------------------------

    def frame(self, table: pd.DataFrame) -> pd.DataFrame:
        """Kernel: this campaign's columns from a sample table."""
        return campaign_frame(table, self.columns)

    def table(self, workbench, *, all_samples: bool = True) -> pd.DataFrame:
        """Adapter: this campaign's table from an open organizer."""
        return campaign_table(workbench, self.columns, all_samples=all_samples)

    def comparable(self, frame: pd.DataFrame, names: Sequence[str] = (), *,
                   protocol: Optional[Mapping[str, object]] = None,
                   finished: bool = True) -> pd.Series:
        return comparable(frame, names, inputs=self.inputs, protocol=protocol,
                          protocol_columns=self.protocol,
                          done=self.done if finished else None)

    def rank(self, frame: pd.DataFrame,
             objectives: Optional[Sequence[Objective]] = None,
             weights: Optional[Sequence[float]] = None) -> pd.DataFrame:
        return rank(frame, list(objectives or self.objectives), weights,
                    inputs=self.inputs)

    def references(self, frame: pd.DataFrame) -> pd.Series:
        """Rows measured without inputs — reference materials. They
        benchmark the measurement; they are not points of the campaign."""
        return ~usable(frame, self.inputs) if self.inputs \
            else pd.Series(False, index=frame.index)

    def to_dict(self) -> Dict[str, object]:
        """A JSON-ready description (for an agent, or to save beside a
        proposal)."""
        return {
            "name": self.name, "description": self.description,
            "columns": [vars(c) for c in self.columns],
            "objectives": [vars(o) for o in self.objectives],
            "when": self.when, "done": list(self.done) if self.done else None,
            "protocol": list(self.protocol),
            "bounds": {k: list(v) for k, v in self.bounds.items()},
            "rounding": dict(self.rounding),
        }


def from_columns(table: pd.DataFrame, inputs: Sequence[str],
                 objectives: Sequence[Objective], *, name: str = "ad hoc",
                 results: Sequence[str] = (), when: str = "") -> Campaign:
    """A campaign made on the spot from sample-table column names — for a
    project that has not declared one. Each column keeps its full name."""
    seen: List[str] = []
    columns: List[Column] = []

    def add(source: str, kind: str):
        if source and source not in seen:
            seen.append(source)
            columns.append(Column(source, source, kind=kind))

    for source in inputs:
        add(source, "input")
    for o in objectives:
        add(o.name, "objective")
    for source in results:
        add(source, "result")
    if when:
        add(when, "context")
    bounds = {}
    for source in inputs:
        values = pd.to_numeric(table.get(source), errors="coerce") \
            if source in table else pd.Series(dtype=float)
        if values.notna().any():
            bounds[source] = (float(values.min()), float(values.max()))
    return Campaign(name, columns, list(objectives), when=when, bounds=bounds)


CAMPAIGNS: Dict[str, Campaign] = {}


def register_campaign(spec: Campaign, overwrite: bool = True) -> Campaign:
    """Make *spec* available by name (GUI pages, :func:`get_campaign`)."""
    if spec.name in CAMPAIGNS and not overwrite:
        raise KeyError(f"campaign {spec.name!r} is already registered")
    CAMPAIGNS[spec.name] = spec
    return spec


def _builtin() -> None:
    """The demo's campaign is built in: importing the demo registers it."""
    import pyDataOrg.demo  # noqa: F401


def get_campaign(name: str) -> Campaign:
    _builtin()
    try:
        return CAMPAIGNS[name]
    except KeyError:
        raise KeyError(f"no campaign {name!r}; registered: "
                       f"{', '.join(CAMPAIGNS) or 'none'}") from None


def list_campaigns() -> List[str]:
    _builtin()
    return list(CAMPAIGNS)


__all__ = [
    "KINDS", "SAMPLE", "Column", "Objective", "Campaign",
    "campaign_frame", "usable", "majority", "comparable", "pareto_mask",
    "rank", "chronological", "best_so_far",
    "kept_values", "campaign_table", "from_columns",
    "CAMPAIGNS", "register_campaign", "get_campaign", "list_campaigns",
]
