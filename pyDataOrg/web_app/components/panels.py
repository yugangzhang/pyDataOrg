#!/usr/bin/env python3
"""
A page of panels the reader lays out: how many, how many to a row, and
which plot goes in each.

:func:`panel_layout` asks; :func:`panel_grid` gives one container per panel,
row by row. The page draws in them::

    chosen, per_row = panel_layout(PLOTS, "my_panels", default=["a", "b"])
    for box, name in zip(panel_grid(len(chosen), per_row), chosen):
        with box:
            draw(name)

*PLOTS* maps a plot's key to its label; what each draws is the page's
business. Nothing here draws or computes.
"""

from __future__ import annotations

from typing import List, Mapping, Sequence, Tuple

import streamlit as st


def panel_layout(options: Mapping[str, str], key: str, *,
                 default: Sequence[str] = (), per_row: int = 2,
                 max_panels: int = 12) -> Tuple[List[str], int]:
    """The panels to draw, in order, and how many to a row.

    *options* are ``{plot key: label}``; the panels start as *default*.
    Keep *options* the same from one sample to the next — a choice whose
    labels change is reset — and say in the panel when a sample has
    nothing for it. Returns ``(keys, per_row)``.
    """
    keys = list(options)
    if not keys:
        return [], per_row
    default = [k for k in default if k in options] or keys[:1]

    a, b, _ = st.columns([1, 1, 4])
    n = int(a.number_input("panels", 1, max_panels, len(default),
                           key=f"{key}_n"))
    per_row = int(b.number_input("per row", 1, 4, min(per_row, n),
                                 key=f"{key}_per_row"))
    chosen = []
    for row in range(0, n, 4):
        for i, column in zip(range(row, min(row + 4, n)), st.columns(4)):
            start = default[i] if i < len(default) else keys[i % len(keys)]
            chosen.append(column.selectbox(f"panel {i + 1}", keys,
                                           index=keys.index(start),
                                           format_func=options.get,
                                           key=f"{key}_{i}"))
    return chosen, per_row


def panel_grid(n: int, per_row: int) -> list:
    """*n* containers, *per_row* to a row."""
    boxes = []
    per_row = max(1, int(per_row))
    for start in range(0, n, per_row):
        boxes += list(st.columns(per_row))[:min(per_row, n - start)]
    return boxes


__all__ = ["panel_layout", "panel_grid"]
