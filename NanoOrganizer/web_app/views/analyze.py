#!/usr/bin/env python3
"""
Analyze — run an analysis on one sample, or over the whole selection.

The option controls are built by reading each analysis function's own
signature, so a newly registered analysis gets a working form with no change
here. That is the same principle as the modality registry: declare it once,
and the interface follows.
"""

import inspect
from typing import Any, Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from NanoOrganizer import analysis as analysis_api
from NanoOrganizer.viz import plots
from NanoOrganizer.web_app.state import (
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
key = st.selectbox("Analysis", available, key="nano_analysis_key",
                   format_func=lambda k: specs[k].label or k)
spec = specs[key]
st.caption(spec.description)

# ---------------------------------------------------------------------------
# Options, built from the function signature
# ---------------------------------------------------------------------------

SKIP = {"measurement", "resolver", "self"}


def option_widgets(function, prefix: str) -> Dict[str, Any]:
    """Render a control for every keyword option the analysis declares.

    Only keyword arguments with concrete defaults are offered. ``None``
    defaults are rendered behind an "override" toggle, because for these
    analyses ``None`` means "work it out from the data" — silently replacing
    that with a number would change results without anyone asking.
    """
    chosen: Dict[str, Any] = {}
    parameters = [
        p for name, p in inspect.signature(function).parameters.items()
        if name not in SKIP
        and p.kind in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD)
        and p.default is not inspect.Parameter.empty
        and not name.startswith("_")
    ]
    if not parameters:
        st.caption("No options.")
        return chosen

    columns = st.columns(3)
    for index, parameter in enumerate(parameters):
        slot = columns[index % 3]
        name, default = parameter.name, parameter.default
        widget_key = f"{prefix}_{name}"

        with slot:
            if isinstance(default, bool):
                chosen[name] = st.toggle(name, value=default, key=widget_key)
            elif isinstance(default, int) and not isinstance(default, bool):
                chosen[name] = int(st.number_input(name, value=int(default),
                                                   step=1, key=widget_key))
            elif isinstance(default, float):
                chosen[name] = float(st.number_input(
                    name, value=float(default),
                    step=abs(default) / 10 if default else 0.1,
                    format="%g", key=widget_key))
            elif isinstance(default, str):
                chosen[name] = st.text_input(name, value=default, key=widget_key)
            elif isinstance(default, tuple) and len(default) == 2 \
                    and all(isinstance(v, (int, float)) for v in default):
                low = st.number_input(f"{name} (low)", value=float(default[0]),
                                      format="%g", key=f"{widget_key}_lo")
                high = st.number_input(f"{name} (high)", value=float(default[1]),
                                       format="%g", key=f"{widget_key}_hi")
                chosen[name] = (float(low), float(high))
            elif default is None:
                if st.toggle(f"set {name}", value=False, key=f"{widget_key}_on",
                             help="Left off, the analysis decides this itself."):
                    chosen[name] = float(st.number_input(
                        name, value=0.0, format="%g", key=widget_key))
    return chosen


with st.expander("Options", expanded=False):
    options = option_widgets(spec.func, f"nano_opt_{key}")

# ---------------------------------------------------------------------------
# Plot dispatch
# ---------------------------------------------------------------------------

def draw(result) -> None:
    """Draw whatever this analysis produced, if there is a plot for it."""
    try:
        if result.analysis == "uvvis_kinetics":
            figure, axes = plt.subplots(1, 2, figsize=(12, 4.5))
            plots.plot_kinetics(result, ax=axes)
            figure.tight_layout()
        elif result.analysis == "uvvis_spectra":
            figure, axes = plt.subplots(1, 2, figsize=(13, 4.8))
            plots.plot_spectra(result, ax=axes[0], colorbar=False)
            plots.plot_endpoint_spectrum(result, ax=axes[1])
            figure.tight_layout()
        elif result.analysis == "particle_sizing":
            figure, ax = plt.subplots(figsize=(7.5, 4.5))
            plots.plot_size_distribution(result, ax=ax)
            figure.tight_layout()
        elif result.analysis == "peak_fit":
            figure, axes = plt.subplots(
                2, 1, figsize=(8, 6), sharex=True,
                gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})
            plots.plot_peak_fit(result, ax=axes)
        else:
            return
    except Exception as exc:
        st.warning(f"Could not plot: {exc}", icon="⚠️")
        return

    st.pyplot(figure, width="stretch")
    plt.close(figure)


# ---------------------------------------------------------------------------
# Single sample
# ---------------------------------------------------------------------------

single, batch = st.tabs(["One sample", f"Batch — {basket_label(workbench)}"])

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
        sample_id = left.selectbox("Sample", candidates, key="nano_single_sample")
        write_back = right.toggle(
            "write result", value=False, key="nano_single_write",
            help="Off by default — an exploratory run should not change the "
                 "results table.")

        if st.button("Run", type="primary", key="nano_run_single"):
            try:
                with st.spinner("Running…"):
                    result = workbench.run(key, sample_id, write=write_back,
                                           **options)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
            else:
                st.session_state["nano_last_result"] = result

        result = st.session_state.get("nano_last_result")
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
    write_back = left.toggle("write results", value=True, key="nano_batch_write")

    if right.button("Run batch", type="primary", key="nano_run_batch"):
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
            st.session_state[f"nano_batch_{key}"] = frame

    frame = st.session_state.get(f"nano_batch_{key}")
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
# Save
# ---------------------------------------------------------------------------

st.divider()
left, right = st.columns([1, 3])
if left.button("💾 Save project", type="primary", key="nano_analysis_save"):
    st.success(f"Saved to {project.save()}")

derived = sorted({name for sample in project for name in sample.derived})
right.caption(
    f"**{len(derived)} derived columns** in the store: "
    + (", ".join(derived[:12]) + (" …" if len(derived) > 12 else "")
       if derived else "none yet — run a batch above.")
)
