#!/usr/bin/env python3
"""
Choose the campaign the Campaign and Next-experiments pages read.

A registered :class:`~pyDataOrg.campaign.Campaign` (a project plugin's, or
the demo's) by name — the app plugin's ``defaults["campaign"]`` first — or
one built on the spot from the open organizer's columns: pick the inputs,
pick the goals and which way each should go. Returns the spec and its table.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import pandas as pd
import streamlit as st

from pyDataOrg import campaign as C
from pyDataOrg import plugins as _plugins

BUILD = "➕ build from columns"


def _default_name() -> str:
    app = _plugins.PLUGINS.get(os.environ.get("PYDATAORG_APP", "").strip())
    return str(app.defaults.get("campaign", "")) if app else ""


def _numeric_columns(table: pd.DataFrame):
    names = []
    for column in table.columns:
        if column == "sample_id":
            continue
        values = pd.to_numeric(table[column], errors="coerce")
        if values.notna().sum() >= 2 and values.nunique() > 1:
            names.append(column)
    return names


def pick_campaign(workbench, key: str = "org_campaign"
                  ) -> Tuple[Optional[C.Campaign], pd.DataFrame]:
    """A campaign chooser in the sidebar; returns ``(spec, frame)``.

    The choice is shared by every page that calls this with the same *key*.
    ``(None, empty)`` when nothing usable is chosen yet.
    """
    names = C.list_campaigns()
    default = _default_name()
    ordered = ([default] if default in names else []) + \
        [n for n in names if n != default] + [BUILD]

    with st.sidebar:
        st.markdown("**Campaign**")
        chosen = st.selectbox("Campaign", ordered, key=f"{key}_name",
                              label_visibility="collapsed")
    if chosen != BUILD:
        spec = C.get_campaign(chosen)
        if spec.description:
            st.caption(spec.description)
        return spec, spec.table(workbench)

    table = workbench.table(all_samples=True)
    numeric = _numeric_columns(table)
    if not numeric:
        st.info("The sample table has no numeric columns to build a campaign "
                "from yet.", icon="📭")
        return None, pd.DataFrame()
    with st.expander("Build a campaign from the sample table", expanded=True):
        inputs = st.multiselect("Inputs — what was chosen", numeric,
                                key=f"{key}_inputs",
                                help="Recipe variables, compositions, set-points.")
        goals = st.multiselect("Goals", [n for n in numeric if n not in inputs],
                               key=f"{key}_goals")
        lower = st.multiselect("…of which lower is better", goals,
                               key=f"{key}_lower")
        times = [c for c in table.columns
                 if c.endswith(("_at", "date", "time", "timestamp"))]
        when = st.selectbox("Time column (for progress)", [""] + times,
                            key=f"{key}_when")
    if not inputs or not goals:
        st.info("Pick at least one input and one goal.", icon="👆")
        return None, pd.DataFrame()
    spec = C.from_columns(
        table, inputs, [C.Objective(g, maximize=g not in lower) for g in goals],
        name="built here", when=when)
    return spec, spec.frame(table)


__all__ = ["pick_campaign", "BUILD"]
