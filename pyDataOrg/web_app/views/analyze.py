#!/usr/bin/env python3
"""
Analyze — run an analysis on one sample, or over the whole selection.

The settings controls are built from each analysis' own settings
(``settings_form``), so a newly registered analysis gets a working form with
no change here. That is the same principle as the modality registry: declare
it once, and the interface follows.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from pyDataOrg import analysis as analysis_api
from pyDataOrg.viz import plots
from pyDataOrg.web_app.components.settings_form import settings_form
from pyDataOrg.web_app.state import (
    basket_label, require_workbench, show_message, show_result_values,
)

workbench = require_workbench()
project = workbench.project

st.title("🧪 Analyze")
st.caption(
    "Derived values are written back onto each sample, which is what makes "
    "them filterable on **Explore** and plottable on **Compare**."
)

available = workbench.analyses()
if not available:
    st.info("Nothing in the current selection can be analysed.", icon="📭")
    st.stop()

specs = {key: analysis_api.get_analysis(key) for key in available}
key = st.selectbox("Analysis", available, key="org_analysis_key",
                   format_func=lambda k: specs[k].label or k)
spec = specs[key]
st.caption(spec.description)

# ---------------------------------------------------------------------------
# Settings, built from the analysis itself
# ---------------------------------------------------------------------------

with st.expander("Settings", expanded=False):
    options = settings_form(key, f"org_opt_{key}")

# ---------------------------------------------------------------------------
# Plot dispatch
# ---------------------------------------------------------------------------

def draw(result) -> None:
    """Draw a result the way its analysis says to (``Analysis.plot``)."""
    painter = analysis_api.get_analysis(result.analysis).plot
    if painter is None:
        return
    try:
        drawn = painter(result)
    except Exception as exc:
        st.warning(f"Could not plot: {exc}", icon="⚠️")
        return
    first = drawn[0] if isinstance(drawn, (tuple, list)) else drawn
    first = first.flat[0] if hasattr(first, "flat") else first
    figure = first.figure
    st.pyplot(figure, width="stretch")
    plt.close(figure)


# ---------------------------------------------------------------------------
# Single sample
# ---------------------------------------------------------------------------

single, batch, current = st.tabs(["One sample",
                                   f"Batch — {basket_label(workbench)}",
                                   "Up to date?"])

with single:
    candidates = [
        sample_id for sample_id in workbench.active
        if any(spec.applies_to(m)
               for m in project.get_sample(sample_id).measurements)
    ]
    if not candidates:
        st.caption("No sample in the selection has data for this analysis.")
    else:
        left, right = st.columns([3, 1])
        sample_id = left.selectbox("Sample", candidates, key="org_single_sample")
        write_back = right.toggle(
            "write result", value=False, key="org_single_write",
            help="Off by default — an exploratory run should not change the "
                 "results table.")

        if st.button("Run", type="primary", key="org_run_single"):
            try:
                with st.spinner("Running…"):
                    result = workbench.run(key, sample_id, write=write_back,
                                           **options)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
            else:
                st.session_state["org_last_result"] = result

        result = st.session_state.get("org_last_result")
        if result is not None and result.sample_id in candidates:
            show_message(result)
            show_result_values(result)
            draw(result)
            with st.expander("Diagnostics", expanded=False):
                st.caption(
                    "What the numbers above depend on. A fit window, an R² and "
                    "a point count are part of the measurement, not decoration."
                )
                st.json({k: (list(v) if isinstance(v, tuple) else v)
                         for k, v in result.diagnostics.items()
                         if not isinstance(v, (list, dict))
                         or k == "per_image"}, expanded=False)

# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

with batch:
    st.caption(
        f"Runs over every matching measurement in the selection and writes the "
        f"scalars back. Failures are shown, not skipped."
    )
    left, right = st.columns([1, 3])
    write_back = left.toggle("write results", value=True, key="org_batch_write")

    if right.button("Run batch", type="primary", key="org_run_batch"):
        progress = st.progress(0.0, text="starting…")

        def tick(index, total, measurement):
            progress.progress(min(index / max(total, 1), 1.0),
                              text=f"{measurement.sample_id} "
                                   f"({index + 1}/{total})")

        try:
            frame = analysis_api.batch(
                project, key, sample_ids=workbench.active,
                write=write_back, progress=tick, **options)
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        else:
            progress.empty()
            st.session_state[f"org_batch_{key}"] = frame

    frame = st.session_state.get(f"org_batch_{key}")
    if frame is not None and len(frame):
        n_ok = int(frame["ok"].sum())
        if n_ok == len(frame):
            st.success(f"{n_ok}/{len(frame)} succeeded.")
        else:
            st.warning(f"{n_ok}/{len(frame)} succeeded — "
                       f"{len(frame) - n_ok} failed.", icon="⚠️")
            st.dataframe(
                frame.loc[~frame["ok"], ["sample_id", "message"]],
                width="stretch", hide_index=True)

        hide = {"measurement_id", "analysis", "per_image"}
        columns = [c for c in frame.columns if c not in hide]
        st.dataframe(frame[columns], width="stretch", hide_index=True)

        st.download_button(
            "⬇️ Download results CSV", frame[columns].to_csv(index=False),
            file_name=f"{project.config.name}_{key}.csv", mime="text/csv")

# ---------------------------------------------------------------------------
# Kept results: analyse exactly what is new
# ---------------------------------------------------------------------------

with current:
    st.caption(
        "Analyses whose results are **kept** (saved as files and linked, "
        "`link=True`). New records arrive; this runs each one on the samples "
        "that have none yet, with the settings the others were kept with.")
    kept = workbench.kept_analyses()
    if not kept:
        st.info("Nothing is kept yet — run a batch with results linked "
                "(`org.batch(key, link=True)`) and it will be tracked here.",
                icon="📭")
    else:
        st.dataframe(workbench.status(kept), hide_index=True, width="stretch")
        if st.button("Analyse what is new", type="primary",
                     key="org_analyse_new"):
            progress = st.progress(0.0, text="starting…")

            def step(index, key, count):
                progress.progress(index / len(kept),
                                  text=f"{key}: {count} new samples")

            with st.spinner("Analysing…"):
                done = workbench.analyse_new(kept, progress=step)
            progress.empty()
            ran = sum(len(frame) for frame in done.values())
            st.success(f"{ran} results kept across {len(done)} analyses — "
                       f"save the project to keep the links.")

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

st.divider()
left, right = st.columns([1, 3])
if left.button("💾 Save project", type="primary", key="org_analysis_save"):
    st.success(f"Saved to {project.save()}")

derived = sorted({name for sample in project for name in sample.derived})
right.caption(
    f"**{len(derived)} derived columns** in the store: "
    + (", ".join(derived[:12]) + (" …" if len(derived) > 12 else "")
       if derived else "none yet — run a batch above.")
)
