#!/usr/bin/env python3
"""
Tables for machine learning and for other programs.

The organizer's sample table is built for people: dotted names, text and
numbers mixed, a column per recorded field. A model wants a matrix — one row
per sample, numeric features, a known index — and another program wants a
file it can read without this package. Two calls:

:func:`feature_frame` (kernel)
    a plain table in, the numeric feature matrix out — coverage filter,
    categorical columns dropped or coded, constant columns removed.
:func:`feature_table` (adapter)
    the same from an open organizer, optionally through a
    :class:`~pyDataOrg.campaign.Campaign` so kept results and short names
    are included.
:func:`write_table`
    CSV, Parquet or JSON by suffix, the index kept.

::

    X = feature_table(org, min_coverage=0.8)            # samples × features
    write_table(X, "features.parquet")
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd


def feature_frame(table: pd.DataFrame, *, index: str = "sample_id",
                  include: Sequence[str] = (), exclude: Sequence[str] = (),
                  min_coverage: float = 0.0, categorical: str = "drop",
                  drop_constant: bool = True) -> pd.DataFrame:
    """The numeric feature matrix of a sample table.

    *include* keeps only those columns (and any whose name starts with one
    of them followed by ``.``); *exclude* removes columns the same way.
    A column is kept when at least *min_coverage* of the rows have a value.
    *categorical* is ``"drop"`` (text columns left out) or ``"codes"``
    (each text column replaced by integer category codes, missing = -1).
    """
    if categorical not in ("drop", "codes"):
        raise ValueError("categorical is 'drop' or 'codes'")

    def matches(name: str, prefixes: Sequence[str]) -> bool:
        return any(name == p or name.startswith(p + ".") for p in prefixes)

    frame = table.copy()
    if index in frame:
        frame = frame.set_index(index, drop=True)
    columns = [c for c in frame.columns
               if (not include or matches(c, include))
               and not matches(c, exclude)]
    out = {}
    for name in columns:
        values = frame[name]
        numbers = pd.to_numeric(values, errors="coerce")
        present = values.notna()
        if present.any() and numbers[present].notna().all():
            out[name] = numbers.astype(float)
        elif categorical == "codes" and present.any():
            out[name] = pd.Series(
                pd.Categorical(values.astype("string")).codes,
                index=frame.index).where(present, -1).astype(float)
    result = pd.DataFrame(out, index=frame.index)
    if min_coverage > 0 and len(result):
        coverage = result.notna().mean()
        result = result.loc[:, coverage >= min_coverage]
    if drop_constant and len(result):
        varying = result.nunique(dropna=True) > 1
        result = result.loc[:, varying]
    result.index.name = "sample_id"
    return result


def feature_table(workbench, *, campaign=None, all_samples: bool = True,
                  **options) -> pd.DataFrame:
    """:func:`feature_frame` of an open organizer (adapter).

    With *campaign* (a :class:`~pyDataOrg.campaign.Campaign` or its
    registered name) the campaign's own columns are used — short names, kept
    results included — instead of every recorded field.
    """
    if campaign is not None:
        from pyDataOrg import campaign as _campaign

        spec = _campaign.get_campaign(campaign) if isinstance(campaign, str) \
            else campaign
        table = spec.table(workbench, all_samples=all_samples)
        return feature_frame(table, index="sample", **options)
    return feature_frame(workbench.table(all_samples=all_samples), **options)


def write_table(frame: pd.DataFrame, path: Union[str, Path]) -> Path:
    """Write *frame* by suffix — ``.csv``, ``.parquet``, ``.json`` — keeping
    the index. Returns the path written."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame.to_csv(path)
    elif suffix in (".parquet", ".pq"):
        frame.to_parquet(path)
    elif suffix == ".json":
        frame.reset_index().to_json(path, orient="records", indent=1,
                                    default_handler=str)
    else:
        raise ValueError(f"unknown table format {suffix!r}: use .csv, "
                         f".parquet or .json")
    return path


def jsonable_records(frame: pd.DataFrame, limit: Optional[int] = None):
    """Rows as plain dicts — NaN as ``None``, numpy scalars as Python ones."""
    rows = frame if limit is None else frame.head(int(limit))
    records = rows.reset_index().to_dict(orient="records") \
        if rows.index.name else rows.to_dict(orient="records")
    return [{str(k): _plain(v) for k, v in row.items()} for row in records]


def _plain(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if value is None or value is pd.NaT:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value if isinstance(value, (str, int, bool)) else str(value)


__all__ = ["feature_frame", "feature_table", "write_table", "jsonable_records"]
