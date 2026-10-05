#!/usr/bin/env python3
"""
Compare — a derived quantity against a synthesis parameter.

The payoff of the whole pipeline: once analyses have written their results back
as derived columns, structure and property sit in the same table and can be
plotted against each other.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from NanoOrganizer.viz import plots
from NanoOrganizer.web_app.state import basket_label, require_workbench

workbench = require_workbench()
project = workbench.project

st.title("📊 Compare")

table = project.to_dataframe()
if table.empty:
    st.info("No samples in this project.", icon="📭")
    st.stop()

derived = [c for c in table.columns
           if c.startswith("derived.") and not c.endswith(".error")]
if not derived:
    st.info(
        "No derived values yet. Run a batch on **Analyze** first — that is "
        "what puts measured quantities into this table.",
        icon="🧪",
    )
    st.stop()

numeric = [c for c in table.columns
           if pd.api.types.is_numeric_dtype(table[c]) and table[c].notna().any()]
parameters = [c for c in numeric if not c.startswith("derived.")]
categorical = [c for c in table.columns
               if 2 <= table[c].nunique(dropna=True) <= 12
               and not pd.api.types.is_numeric_dtype(table[c])]

# ---------------------------------------------------------------------------
# Axes
# ---------------------------------------------------------------------------

with st.container(border=True):
    left, middle, right = st.columns(3)

    x_options = parameters + derived
    default_x = next((c for c in x_options if "temperature" in c.lower()),
                     x_options[0] if x_options else None)
    x = left.selectbox("X — synthesis parameter", x_options,
                       index=x_options.index(default_x) if default_x else 0,
                       key="nano_cmp_x",
                       format_func=lambda c: c.split(".")[-1])

    y = middle.selectbox("Y — measured quantity", derived, key="nano_cmp_y",
                         format_func=lambda c: c.split(".")[-1])

    color_options = ["(none)"] + categorical
    default_color = next((c for c in categorical if "batch" in c.lower()),
                         None)
    color_by = right.selectbox(
        "Colour by", color_options,
        index=color_options.index(default_color) if default_color else 0,
        key="nano_cmp_color", format_func=lambda c: c.split(".")[-1])
    color_by = "" if color_by == "(none)" else color_by

    options = st.columns(3)
    logy = options[0].toggle("log Y", key="nano_cmp_logy")
    labels = options[1].toggle("label points", value=True, key="nano_cmp_labels")
    only_selected = options[2].toggle(
        f"only the {len(workbench.basket)} selected" if workbench.basket
        else "only the selection",
        value=bool(workbench.basket), disabled=not workbench.basket,
        key="nano_cmp_selected")

frame = table if not only_selected else table[
    table["sample_id"].isin(workbench.basket)]

error_column = f"{y}.error"
yerr = error_column if error_column in frame.columns else ""

try:
    figure, ax = plt.subplots(figsize=(8, 5.2))
    plots.plot_compare(frame, x, y, color_by=color_by, ax=ax, yerr=yerr,
                       label_points=labels, logy=logy)
    figure.tight_layout()
    st.pyplot(figure, width="stretch")
    plt.close(figure)
except Exception as exc:
    st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

st.caption(
    "Colour caps at three categories and folds the rest into a neutral "
    "“Other”: a scatter asks the eye to separate every pair of colours at "
    "once, not just neighbouring ones."
)

# ---------------------------------------------------------------------------
# Is the comparison confounded?
# ---------------------------------------------------------------------------

if color_by:
    usable = frame.dropna(subset=[x, y])
    groups = usable.groupby(color_by)[y]
    sizes = groups.size()

    if usable[color_by].nunique() > 1 and len(usable) >= 2:
        spreads = [float(s.max() - s.min()) for _, s in groups if len(s) > 1]
        spread_between = float(groups.median().max() - groups.median().min())
        name = color_by.split(".")[-1]

        if not spreads:
            # Every group holds one sample. Between-group and within-group
            # variation are then the same numbers, and no amount of arithmetic
            # separates them — say so rather than staying quiet.
            st.info(
                f"Each **{name}** has only one sample here, so a difference "
                f"between groups cannot be told apart from an effect of "
                f"{x.split('.')[-1]}. Several samples per group are needed to "
                f"separate them.",
                icon="ℹ️",
            )
        else:
            spread_within = max(spreads)
            if spread_within > 0 and spread_between > spread_within:
                st.warning(
                    f"**{name} may be confounded with {x.split('.')[-1]}.** "
                    f"The spread of {y.split('.')[-1]} *between* groups "
                    f"({spread_between:.3g}) is larger than the spread "
                    f"*within* any one group ({spread_within:.3g}), so what "
                    f"looks like an effect of {x.split('.')[-1]} may be a "
                    f"difference between groups. Compare within one group "
                    f"before concluding.",
                    icon="⚠️",
                )

        with st.expander("Per-group summary", expanded=False):
            st.dataframe(
                groups.agg(n="size", median="median", min="min", max="max"),
                width="stretch")

# ---------------------------------------------------------------------------
# Table and export
# ---------------------------------------------------------------------------

st.subheader("Data behind the plot")

columns = ["sample_id", x, y] + ([color_by] if color_by else []) + \
          ([yerr] if yerr else [])
columns = list(dict.fromkeys(c for c in columns if c in frame.columns))
shown = frame[columns].dropna(subset=[x, y])
st.dataframe(shown, width="stretch", hide_index=True)
st.caption(f"{len(shown)} of {len(frame)} samples have both values.")

export = [c for c in table.columns
          if c == "sample_id" or c.startswith("derived.")
          or c in parameters or c in categorical]
st.download_button(
    "⬇️ Download results CSV", table[export].to_csv(index=False),
    file_name=f"{project.config.name}_results.csv", mime="text/csv")
