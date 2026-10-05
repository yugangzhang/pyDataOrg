#!/usr/bin/env python3
"""
Explore & Filter — the table, and the basket every other page reads.

One row per sample: authored parameters as dotted columns, derived values
beside them. Filtering here sets the selection that Visualize, Analyze and
Compare all act on.
"""

import numpy as np
import pandas as pd
import streamlit as st

from NanoOrganizer.web_app.state import basket_label, require_workbench

workbench = require_workbench()
project = workbench.project

st.title("🔎 Explore & Filter")
st.caption(
    "Narrow the project to the samples you care about. The selection carries "
    "over to every other page."
)

table = project.to_dataframe()
if table.empty:
    st.info("No samples in this project yet.", icon="📭")
    st.stop()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

NUMERIC = [c for c in table.columns
           if pd.api.types.is_numeric_dtype(table[c]) and table[c].notna().any()]
BOOLEAN = [c for c in table.columns if pd.api.types.is_bool_dtype(table[c])]
CATEGORICAL = [
    c for c in table.columns
    if c not in NUMERIC and c not in BOOLEAN
    and 1 <= table[c].nunique(dropna=True) <= 30
]

if "nano_filters" not in st.session_state:
    st.session_state["nano_filters"] = []

with st.container(border=True):
    st.subheader("Build a filter")

    kind = st.radio("Filter on", ["Number", "Category", "Flag", "Expression"],
                    horizontal=True, key="nano_filter_kind")

    if kind == "Number" and NUMERIC:
        column = st.selectbox("Column", NUMERIC, key="nano_num_col")
        values = table[column].dropna()
        low, high = float(values.min()), float(values.max())
        if low == high:
            st.caption(f"Every sample has {column} = {low:g}; nothing to filter.")
        else:
            chosen = st.slider("Range", low, high, (low, high),
                               key="nano_num_range")
            if st.button("Add filter", key="nano_add_num"):
                st.session_state["nano_filters"].append(
                    {"kind": "range", "column": column, "value": chosen})
                st.rerun()

    elif kind == "Category" and CATEGORICAL:
        column = st.selectbox("Column", CATEGORICAL, key="nano_cat_col")
        options = sorted(str(v) for v in table[column].dropna().unique())
        chosen = st.multiselect("Keep", options, default=options,
                                key="nano_cat_values")
        if st.button("Add filter", key="nano_add_cat", disabled=not chosen):
            st.session_state["nano_filters"].append(
                {"kind": "isin", "column": column, "value": chosen})
            st.rerun()

    elif kind == "Flag" and BOOLEAN:
        column = st.selectbox("Column", BOOLEAN, key="nano_bool_col")
        wanted = st.radio("Keep samples where", [True, False], horizontal=True,
                          format_func=lambda v: "yes" if v else "no",
                          key="nano_bool_value")
        if st.button("Add filter", key="nano_add_bool"):
            st.session_state["nano_filters"].append(
                {"kind": "eq", "column": column, "value": wanted})
            st.rerun()

    elif kind == "Expression":
        st.caption("Pandas query syntax. Column names contain dots, so wrap "
                   "them in backticks.")
        expression = st.text_input(
            "Expression", key="nano_expr",
            placeholder="`synthesis.conditions.temperature_C` >= 5")
        if st.button("Add filter", key="nano_add_expr", disabled=not expression):
            try:
                table.query(expression)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
            else:
                st.session_state["nano_filters"].append(
                    {"kind": "query", "column": "", "value": expression})
                st.rerun()
    else:
        st.caption(f"No {kind.lower()} columns in this project.")

# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

filtered = table
for index, rule in enumerate(st.session_state["nano_filters"]):
    try:
        if rule["kind"] == "range":
            low, high = rule["value"]
            series = filtered[rule["column"]]
            filtered = filtered[series.between(low, high) | series.isna()]
        elif rule["kind"] == "isin":
            filtered = filtered[
                filtered[rule["column"]].astype(str).isin(rule["value"])]
        elif rule["kind"] == "eq":
            filtered = filtered[filtered[rule["column"]] == rule["value"]]
        elif rule["kind"] == "query":
            filtered = filtered.query(rule["value"])
    except Exception as exc:
        st.error(f"Filter {index + 1} failed: {exc}", icon="🚫")

if st.session_state["nano_filters"]:
    st.caption("Active filters")
    for index, rule in enumerate(list(st.session_state["nano_filters"])):
        row = st.columns([6, 1])
        if rule["kind"] == "range":
            text = f"{rule['column']} between {rule['value'][0]:g} and {rule['value'][1]:g}"
        elif rule["kind"] == "isin":
            text = f"{rule['column']} in {', '.join(rule['value'][:4])}" + \
                   (" …" if len(rule["value"]) > 4 else "")
        elif rule["kind"] == "eq":
            text = f"{rule['column']} is {rule['value']}"
        else:
            text = rule["value"]
        row[0].code(text, language=None)
        if row[1].button("✕", key=f"nano_drop_filter_{index}"):
            st.session_state["nano_filters"].pop(index)
            st.rerun()

    if st.button("Clear all filters"):
        st.session_state["nano_filters"] = []
        st.rerun()

# ---------------------------------------------------------------------------
# The selection
# ---------------------------------------------------------------------------

matched = [str(s) for s in filtered["sample_id"]]

left, middle, right = st.columns([2, 1, 1])
left.metric("Matching samples", f"{len(matched)} of {len(table)}")

if middle.button("Select these", type="primary", width="stretch",
                 disabled=not matched):
    workbench.select(matched)
    st.rerun()
if right.button("Use all samples", width="stretch"):
    workbench.clear()
    st.rerun()

st.caption(f"Pages will act on: **{basket_label(workbench)}**")

with st.expander("Pick samples by hand", expanded=False):
    manual = st.multiselect("Samples", project.sample_ids(),
                            default=workbench.basket, key="nano_manual_pick")
    if st.button("Use this selection", disabled=not manual):
        workbench.select(manual)
        st.rerun()

# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

st.subheader("Table")

search = st.text_input("Show columns containing", key="nano_col_search",
                       placeholder="temperature, derived, status …",
                       help="The table is wide; search rather than scroll.")

if search:
    needles = [t.strip().lower() for t in search.split(",") if t.strip()]
    columns = [c for c in filtered.columns
               if any(n in c.lower() for n in needles)]
else:
    # A readable default: identity, stage status, and anything derived.
    columns = [c for c in filtered.columns
               if c == "sample_id" or c.startswith("derived.")
               or c.endswith(".status") or c.startswith("has.")]

columns = ["sample_id"] + [c for c in columns if c != "sample_id"]
st.dataframe(filtered[columns], width="stretch", hide_index=True)
st.caption(f"{len(filtered)} rows × {len(columns)} of {len(table.columns)} columns")

download, _ = st.columns([1, 3])
download.download_button(
    "⬇️ Download CSV", filtered[columns].to_csv(index=False),
    file_name=f"{project.config.name}_table.csv", mime="text/csv",
    width="stretch",
)

# ---------------------------------------------------------------------------
# Measurements in the selection
# ---------------------------------------------------------------------------

with st.expander("Measurements in the selection", expanded=False):
    frame = project.to_dataframe(level="measurement",
                                 sample_ids=workbench.active)
    if frame.empty:
        st.caption("None.")
    else:
        resolver = workbench.resolver
        frame = frame.copy()
        frame["readable"] = [
            bool(project.get_sample(row.sample_id)
                 .get_measurement(row.measurement_id)
                 .resolve(resolver))
            for row in frame.itertuples()
        ]
        st.dataframe(
            frame[["sample_id", "modality_label", "group", "stage",
                   "n_paths", "readable"]],
            width="stretch", hide_index=True,
        )
