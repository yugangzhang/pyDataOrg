#!/usr/bin/env python3
"""
Analyze — run an analysis on one sample, or over the whole selection.

What to analyse is chosen the way a notebook call names it,
``wb.run(key, sample, modality=…, role=…, index=…)``: the analysis, the
technique it runs on, the sample and — for a series of curves — which curve.
The page shows that curve, with the window the settings name, before
anything is fitted.

The settings controls are built from each analysis' own settings
(``settings_form``), so a newly registered analysis gets a working form with
no change here. That is the same principle as the modality registry: declare
it once, and the interface follows.
"""

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from pyDataOrg import analysis as analysis_api
from pyDataOrg.analysis import reading
from pyDataOrg.analysis.peaks import BACKGROUNDS, SHAPES, load_curve
from pyDataOrg.core import modality as modality_registry
from pyDataOrg.core.pathmap import display_path
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

# The two settings that pick a curve out of a series; the page offers them as
# "which curve", not as raw numbers in the form.
CURVE_SETTINGS = ("reduce", "index")
CURVES = {"last": "Last curve", "number": "Curve number",
          "last_decile": "Mean of the last 10 %", "mean": "Mean of all curves"}
# Allowed values of the built-in analyses' text settings.
CHOICES = {"peak_fit": {"shape": SHAPES, "background": BACKGROUNDS}}


def technique_id(measurement) -> str:
    """``uvvis``, or ``xps · b4f`` when a role tells two apart."""
    return (f"{measurement.modality} · {measurement.role}" if measurement.role
            else measurement.modality)


def technique_label(tech: str) -> str:
    modality, _, role = tech.partition(" · ")
    spec = modality_registry.get(modality)
    name = spec.label if spec else modality
    return f"{name} · {role}" if role else name


def curve_choice(settings: dict) -> str:
    """The ``CURVES`` entry a settings dict stands for."""
    reduce = settings.get("reduce", "last_decile")
    if reduce in ("last_decile", "mean"):
        return reduce
    return "last" if int(settings.get("index", -1)) < 0 else "number"


def window_of(settings: dict, x) -> tuple:
    """The x range the settings look at, if they name one."""
    if settings.get("x_range"):
        return tuple(settings["x_range"])
    low, high = settings.get("x_min"), settings.get("x_max")
    if low is None and high is None:
        return None
    x = np.asarray(x, dtype=float)
    return (float(np.nanmin(x)) if low is None else low,
            float(np.nanmax(x)) if high is None else high)


# ---------------------------------------------------------------------------
# What to analyse
# ---------------------------------------------------------------------------

with st.container(border=True):
    top = st.columns([2, 2, 1])
    key = top[0].selectbox("Analysis", available, key="org_analysis_key",
                           format_func=lambda k: specs[k].label or k)
    spec = specs[key]

    usable = [m for m in workbench.measurements() if spec.applies_to(m)]
    techniques = list(dict.fromkeys(sorted(technique_id(m) for m in usable)))
    tech = top[1].selectbox(
        "Technique", techniques, key=f"org_analysis_tech_{key}",
        format_func=technique_label,
        help="The measurements this analysis can run on. A role "
             "(`xps · b4f`) tells two of one technique apart.")
    modality, _, role = tech.partition(" · ")

    of_tech = [m for m in usable if technique_id(m) == tech]
    stages = sorted({m.stage for m in of_tech})
    if len(stages) > 1:
        stage = top[2].selectbox("Stage", stages,
                                 key=f"org_analysis_stage_{key}_{tech}")
    else:
        stage = stages[0] if stages else ""
        top[2].caption(f"Stage: **{stage or '—'}**")
    targets = [m for m in of_tech if m.stage == stage]
    st.caption(spec.description)

    by_sample = {}
    for measurement in targets:
        by_sample.setdefault(measurement.sample_id, measurement)
    row = st.columns([2, 2, 3])
    sample_id = row[0].selectbox("Sample", list(by_sample),
                                 key=f"org_analysis_sample_{tech}",
                                 help="For the preview and a single run; the "
                                      "batch runs on every sample.")
    measurement = by_sample[sample_id]

    defaults = spec.settings_for()
    kept = workbench.kept_settings(key, modality=modality)
    current = {**defaults, **{k: v for k, v in kept.items() if k in defaults}}

    # Which curve, for an analysis that takes one out of a series.
    picks_curve = all(name in defaults for name in CURVE_SETTINGS)
    series, n_curves, curve_labels = None, 1, []
    curve = {}
    if picks_curve:
        try:
            x_all, matrix, info = reading.load_curve_set(measurement,
                                                         workbench.resolver)
            series, n_curves = (x_all, matrix), matrix.shape[0]
            curve_labels = list(info.get("labels") or [])
        except Exception as exc:
            row[1].caption(f"⚠️ cannot read the curves: {exc}")

        if n_curves > 1:
            choice_key = f"org_analysis_curve_{key}_{tech}"
            choice = row[1].selectbox(
                "Curve", list(CURVES), key=choice_key,
                index=list(CURVES).index(curve_choice(current)),
                format_func=CURVES.get,
                help="Which curve of the series is analysed — the same "
                     "choice for every sample in a batch.")
            if choice == "number":
                number_key = f"org_analysis_curve_n_{key}_{tech}"
                # A sample with fewer curves than the last one chosen.
                if st.session_state.get(number_key, 0) > n_curves - 1:
                    st.session_state[number_key] = n_curves - 1
                start = int(current.get("index", -1))
                number = row[2].slider(
                    f"Curve number (of {n_curves})", 0, n_curves - 1,
                    start if 0 <= start < n_curves else n_curves - 1,
                    key=number_key)
                if number < len(curve_labels):
                    row[2].caption(f"curve {number}: {curve_labels[number]}")
                curve = {"reduce": "frame", "index": number}
            elif choice == "last":
                curve = {"reduce": "frame", "index": -1}
                row[2].caption(f"curve {n_curves - 1}"
                               + (f": {curve_labels[-1]}" if curve_labels
                                  else ""))
            else:
                curve = {"reduce": choice}
                row[2].caption(f"{n_curves} curves in {sample_id}")
        else:
            row[1].caption("One curve — nothing to choose.")
    else:
        row[1].caption(f"{len(measurement.resolve(workbench.resolver))} "
                       f"file(s) in {sample_id}")

# ---------------------------------------------------------------------------
# Settings, built from the analysis itself
# ---------------------------------------------------------------------------

with st.expander("⚙️ Settings", expanded=True):
    # Keyed by technique: a window in nm means nothing on a curve in Å⁻¹.
    options = settings_form(
        key, f"org_opt_{key}_{tech}", current,
        only=[n for n in defaults if not (picks_curve and n in CURVE_SETTINGS)],
        choices=CHOICES.get(key))
    if kept:
        st.caption("Starting from the settings the kept results were made "
                   "with.")
options.update(curve)

# ---------------------------------------------------------------------------
# What it will run on
# ---------------------------------------------------------------------------

if picks_curve:
    try:
        x, y, picked = load_curve(
            measurement, workbench.resolver,
            index=int(options.get("index", -1)),
            reduce=options.get("reduce", "frame"), crop=options.get("crop"))
        figure, ax = plt.subplots(figsize=(9.0, 3.8))
        meta = measurement.spec
        plots.plot_picked_curve(
            x, y, ax=ax, series=series, window=window_of(options, x),
            label=picked.get("source", "") or "the curve analysed",
            xlabel=meta.x_label if meta else "x",
            ylabel=meta.y_label if meta else "signal",
            title=f"{sample_id} · {technique_label(tech)} — what "
                  f"{spec.label or key} will use",
            logx=bool(meta and meta.log_x), logy=bool(meta and meta.log_y))
        figure.tight_layout()
        st.pyplot(figure, width="stretch")
        plt.close(figure)
    except Exception as exc:
        st.caption(f"⚠️ No preview: {type(exc).__name__}: {exc}")

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

single, batch, current_tab = st.tabs([f"Run on {sample_id}",
                                      f"Batch — {basket_label(workbench)}",
                                      "Up to date?"])

with single:
    left, right = st.columns([3, 1])
    left.caption(f"{key} on `{measurement.measurement_id}`.")
    write_back = right.toggle(
        "write result", value=False, key="org_single_write",
        help="Off by default — an exploratory run should not change the "
             "results table.")

    if st.button("Run", type="primary", key="org_run_single"):
        try:
            with st.spinner("Running…"):
                result = workbench.run(key, sample_id, modality=modality,
                                       stage=stage, role=role,
                                       write=write_back, verbose=False,
                                       **options)
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        else:
            st.session_state["org_last_result"] = result

    result = st.session_state.get("org_last_result")
    if result is not None and result.analysis == key \
            and result.measurement_id == measurement.measurement_id:
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
        f"Runs on the {technique_label(tech)} measurement of every sample in "
        f"the selection, with the curve choice and settings above, and writes "
        f"the scalars back. Failures are shown, not skipped."
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
                project, key, sample_ids=workbench.active, modality=modality,
                stage=stage, role=role, write=write_back, progress=tick,
                **options)
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

with current_tab:
    st.caption(
        "Analyses whose results are **kept** (saved as files and linked, "
        "`link=True`). New records arrive; this runs each one on the samples "
        "that have none yet, with the settings the others were kept with.")
    kept_keys = workbench.kept_analyses()
    if not kept_keys:
        st.info("Nothing is kept yet — run a batch with results linked "
                "(`org.batch(key, link=True)`) and it will be tracked here.",
                icon="📭")
    else:
        st.dataframe(workbench.status(kept_keys), hide_index=True,
                     width="stretch")
        if st.button("Analyse what is new", type="primary",
                     key="org_analyse_new"):
            progress = st.progress(0.0, text="starting…")

            def step(index, key, count):
                progress.progress(index / len(kept_keys),
                                  text=f"{key}: {count} new samples")

            with st.spinner("Analysing…"):
                done = workbench.analyse_new(kept_keys, progress=step)
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
    st.success(f"Saved to {display_path(project.save())}")

derived = sorted({name for sample in project for name in sample.derived})
right.caption(
    f"**{len(derived)} derived columns** in the store: "
    + (", ".join(derived[:12]) + (" …" if len(derived) > 12 else "")
       if derived else "none yet — run a batch above.")
)
