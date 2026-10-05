#!/usr/bin/env python3
"""
Visualize — one page for every technique, grouped by what the data *is*.

The tabs are Curves / Images / Volumes / Correlation, which are the four
visualisation groups the modality registry defines. Technique is a selector
inside a tab, not a page of its own: UV-Vis, Raman, IR, XPS and SAXS 1D all
draw through the same code and differ only in their axis captions.

Adding a technique is a registry entry. It needs no change here.
"""

from typing import List, Optional

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from NanoOrganizer.analysis import reading
from NanoOrganizer.core import modality as modality_registry
from NanoOrganizer.viz import plots
from NanoOrganizer.web_app.state import basket_label, require_workbench

workbench = require_workbench()
project = workbench.project

st.title("📈 Visualize")
st.caption(f"Drawing from **{basket_label(workbench)}**. "
           f"Change the selection on **Explore**.")

groups = modality_registry.groups_present(
    {m.modality for m in workbench.measurements()})
if not groups:
    st.info("No measurements in the current selection.", icon="📭")
    st.stop()

COLORMAPS = ["viridis", "magma", "inferno", "plasma", "cividis", "gray",
             "bone", "coolwarm", "turbo"]


def modality_choice(group: str, key: str):
    """Technique and stage selectors for one group; returns the measurements."""
    present = sorted({m.modality for m in workbench.measurements(group=group)})
    labels = {k: (modality_registry.get(k).label if modality_registry.get(k)
                  else k) for k in present}

    left, right = st.columns(2)
    chosen = left.selectbox("Technique", present, key=f"{key}_modality",
                            format_func=lambda k: labels[k])

    stages = sorted({m.stage for m in workbench.measurements(modality=chosen)
                     if m.stage})
    stage = ""
    if len(stages) > 1:
        stage = right.selectbox("Stage", ["(all)"] + stages, key=f"{key}_stage")
        stage = "" if stage == "(all)" else stage
    elif stages:
        right.caption(f"Stage: **{stages[0]}**")

    return chosen, workbench.measurements(modality=chosen, stage=stage)


def pick_measurement(measurements, key: str):
    """Choose one measurement by sample id."""
    if not measurements:
        return None
    by_sample = {m.sample_id: m for m in measurements}
    sample_id = st.selectbox("Sample", list(by_sample), key=f"{key}_sample")
    return by_sample[sample_id]


def show(fig_or_ax):
    """Render a matplotlib axes/figure and release it."""
    axes = fig_or_ax
    figure = axes[0].figure if isinstance(axes, (list, np.ndarray)) else axes.figure
    st.pyplot(figure, width="stretch")
    plt.close(figure)


# ---------------------------------------------------------------------------
# Curves
# ---------------------------------------------------------------------------

def render_curves():
    chosen, measurements = modality_choice("curve", "nano_curve")
    if not measurements:
        st.caption("Nothing to draw.")
        return

    spec = modality_registry.get(chosen)
    mode = st.radio(
        "Show", ["Compare samples", "One sample in detail"],
        horizontal=True, key="nano_curve_mode",
        help="Compare draws one curve per sample; detail draws every frame of "
             "a single run, coloured by time.",
    )

    left, right = st.columns(2)
    logx = left.toggle("log x", value=spec.log_x if spec else False,
                       key="nano_curve_logx")
    logy = right.toggle("log y", value=spec.log_y if spec else False,
                        key="nano_curve_logy")

    x_label = spec.x_label if spec else "x"
    y_label = spec.y_label if spec else "signal"

    if mode == "Compare samples":
        reduce = st.selectbox(
            "One curve per sample from", ["last frame", "mean of all frames",
                                          "first frame"],
            key="nano_curve_reduce")
        curves = []
        problems = []
        for measurement in measurements:
            try:
                x, matrix, _ = reading.load_curve_set(measurement,
                                                      workbench.resolver)
            except Exception as exc:
                problems.append(f"{measurement.sample_id}: {exc}")
                continue
            if reduce == "mean of all frames":
                y = matrix.mean(axis=0)
            elif reduce == "first frame":
                y = matrix[0]
            else:
                y = matrix[-1]
            curves.append((measurement.sample_id, x, y))

        if problems:
            st.warning("Skipped — " + "; ".join(problems[:3]), icon="⚠️")
        if not curves:
            st.error("Nothing could be read.", icon="🚫")
            return

        show(plots.plot_curves(curves, xlabel=x_label, ylabel=y_label,
                               title=f"{spec.label if spec else chosen}"
                                     f" — {reduce}",
                               logx=logx, logy=logy))

    else:
        measurement = pick_measurement(measurements, "nano_curve_one")
        if measurement is None:
            return
        try:
            x, matrix, info = reading.load_curve_set(measurement,
                                                     workbench.resolver)
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
            return

        st.caption(f"{matrix.shape[0]} frames × {x.size} points "
                   f"({info.get('source', '')})")

        if matrix.shape[0] == 1:
            show(plots.plot_curves([(measurement.sample_id, x, matrix[0])],
                                   xlabel=x_label, ylabel=y_label,
                                   logx=logx, logy=logy))
            return

        max_curves = st.slider("Curves to draw", 5, min(200, matrix.shape[0]),
                               min(40, matrix.shape[0]),
                               key="nano_curve_maxn")

        from matplotlib.cm import ScalarMappable
        from matplotlib.colors import Normalize

        times = info.get("t_s", np.arange(matrix.shape[0], dtype=float))
        step = max(1, matrix.shape[0] // max_curves)
        cmap = plots.sequential_cmap()
        norm = Normalize(vmin=float(np.min(times)), vmax=float(np.max(times)))

        figure, ax = plt.subplots(figsize=(8, 4.8))
        for index in range(0, matrix.shape[0], step):
            ax.plot(x, matrix[index], linewidth=1.1,
                    color=cmap(norm(times[index])))
        if logx:
            ax.set_xscale("log")
        if logy:
            ax.set_yscale("log")
        plots.style(ax, x_label, y_label,
                    f"{measurement.sample_id} — {matrix.shape[0]} frames")
        bar = figure.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax)
        bar.set_label("time (s)" if "t_s" in info else "frame",
                      color=plots.INK_SOFT, fontsize=9)
        bar.outline.set_visible(False)
        st.pyplot(figure, width="stretch")
        plt.close(figure)

        if "t_s" in info:
            band = st.number_input(
                "Trace one band over time (x value)",
                value=float(np.median(x)), key="nano_curve_band")
            index = int(np.argmin(np.abs(x - band)))
            trace_ax = plots.plot_curves(
                [(f"{x[index]:.1f}", times / 60.0, matrix[:, index])],
                xlabel="time (min)", ylabel=f"signal at {x[index]:.1f}",
                title=f"{measurement.sample_id} — band trace")
            show(trace_ax)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def render_images():
    chosen, measurements = modality_choice("image", "nano_image")
    measurement = pick_measurement(measurements, "nano_image")
    if measurement is None:
        st.caption("Nothing to draw.")
        return

    paths = measurement.resolve(workbench.resolver)
    if not paths:
        st.error("No files resolve — check the path aliases on **Project**.",
                 icon="🚫")
        return

    index = 0
    if len(paths) > 1:
        index = st.slider("Frame", 0, len(paths) - 1, 0, key="nano_image_frame")

    try:
        array, info = reading.load_image(measurement, workbench.resolver, index)
    except Exception as exc:
        st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        return

    left, middle, right = st.columns(3)
    cmap = left.selectbox("Colormap", COLORMAPS, key="nano_image_cmap")
    log_scale = middle.toggle("log intensity", key="nano_image_log")
    percentile = right.slider("Contrast percentile", 90.0, 100.0, 99.5, 0.1,
                              key="nano_image_pct",
                              help="Clip the display range to this percentile. "
                                   "A few hot pixels otherwise flatten "
                                   "everything else.")

    display = np.asarray(array, dtype=float)
    if log_scale:
        floor = np.nanmin(display[display > 0]) if np.any(display > 0) else 1.0
        display = np.log10(np.clip(display, floor, None))

    low = float(np.nanpercentile(display, 100.0 - percentile))
    high = float(np.nanpercentile(display, percentile))

    figure, ax = plt.subplots(figsize=(6.5, 6.5))
    image = ax.imshow(display, cmap=cmap, vmin=low, vmax=high,
                      interpolation="nearest", origin="upper")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    scale = info.get("nm_per_pixel")
    caption = f"{info['file']} — {array.shape[1]}×{array.shape[0]} px"
    if scale:
        caption += f", {scale:.3f} nm/px ({array.shape[1] * scale / 1000:.3f} µm wide)"
    ax.set_title(caption, color=plots.INK, fontsize=10, loc="left")
    bar = figure.colorbar(image, ax=ax, fraction=0.046)
    bar.outline.set_visible(False)
    bar.ax.tick_params(colors=plots.INK_SOFT, labelsize=8)
    st.pyplot(figure, width="stretch")
    plt.close(figure)

    if info.get("banner_rows"):
        st.caption(f"Cropped {info['banner_rows']} rows of instrument banner "
                   f"from the bottom.")

    if chosen in {"tem", "sem", "optical"}:
        with st.expander("Check the particle segmentation", expanded=False):
            st.caption("Outlines should trace whole particles. Lines cutting "
                       "through one mean the seed spacing is too tight; specks "
                       "on the support mean the contrast floor is too low.")
            contrast = st.slider("Contrast floor", 0.0, 0.9, 0.2, 0.05,
                                 key="nano_seg_contrast")
            if st.button("Segment this frame", key="nano_seg_run"):
                try:
                    axes = plots.plot_segmentation(
                        measurement, workbench.resolver, image_index=index,
                        min_contrast_frac=contrast)
                    show(axes)
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}", icon="🚫")


# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------

def render_volumes():
    chosen, measurements = modality_choice("volume", "nano_volume")
    measurement = pick_measurement(measurements, "nano_volume")
    if measurement is None:
        st.caption("Nothing to draw.")
        return

    try:
        volume, info = reading.load_volume(measurement, workbench.resolver)
    except Exception as exc:
        st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        return

    st.caption(f"{'×'.join(str(n) for n in volume.shape)} "
               f"({info.get('source', '')})")

    left, middle, right = st.columns(3)
    axis = left.selectbox("Slice along", [0, 1, 2], key="nano_vol_axis",
                          format_func=lambda a: f"axis {a} "
                                                f"({volume.shape[a]} planes)")
    cmap = middle.selectbox("Colormap", COLORMAPS, key="nano_vol_cmap")
    projection = right.selectbox("Show", ["single slice", "mean projection",
                                          "max projection"],
                                 key="nano_vol_mode")

    n_planes = volume.shape[axis]

    if projection == "single slice":
        index = st.slider("Plane", 0, n_planes - 1, n_planes // 2,
                          key="nano_vol_slice")
        plane = np.take(volume, index, axis=axis)
        title = f"plane {index} along axis {axis}"
    else:
        # Projecting the whole depth of a dense sample saturates: everything
        # is in front of something. A slab is what actually gets looked at.
        slab, centre = st.columns(2)
        thickness = slab.slider("Slab thickness (planes)", 1, n_planes,
                                min(16, n_planes), key="nano_vol_thickness")
        middle_plane = centre.slider("Slab centre", 0, n_planes - 1,
                                     n_planes // 2, key="nano_vol_centre")
        low = max(middle_plane - thickness // 2, 0)
        high = min(low + thickness, n_planes)
        block = np.take(volume, range(low, high), axis=axis)

        reducer = block.mean if projection == "mean projection" else block.max
        plane = reducer(axis=axis)
        kind = "mean" if projection == "mean projection" else "max"
        title = (f"{kind} of planes {low}–{high - 1} along axis {axis}"
                 if high - low < n_planes else f"{kind} along axis {axis}")

    figure, ax = plt.subplots(figsize=(6.5, 6.5))
    image = ax.imshow(plane, cmap=cmap, interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, color=plots.INK, fontsize=10, loc="left")
    bar = figure.colorbar(image, ax=ax, fraction=0.046)
    bar.outline.set_visible(False)
    st.pyplot(figure, width="stretch")
    plt.close(figure)


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------

def render_correlation():
    chosen, measurements = modality_choice("correlation", "nano_corr")
    if not measurements:
        st.caption("Nothing to draw.")
        return

    spec = modality_registry.get(chosen)
    if spec is not None and spec.shape == "twotime":
        measurement = pick_measurement(measurements, "nano_corr_2t")
        if measurement is None:
            return
        try:
            array, info = reading.load_image(measurement, workbench.resolver)
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
            return
        figure, ax = plt.subplots(figsize=(6.5, 6.0))
        image = ax.imshow(array, cmap="viridis", origin="lower",
                          interpolation="nearest")
        plots.style(ax, spec.x_label, spec.y_label,
                    f"{measurement.sample_id} — two-time correlation")
        figure.colorbar(image, ax=ax, fraction=0.046).outline.set_visible(False)
        st.pyplot(figure, width="stretch")
        plt.close(figure)
        return

    curves = []
    for measurement in measurements:
        try:
            x, matrix, _ = reading.load_curve_set(measurement,
                                                  workbench.resolver)
        except Exception:
            continue
        curves.append((measurement.sample_id, x, matrix[-1]))

    if not curves:
        st.error("Nothing could be read.", icon="🚫")
        return

    show(plots.plot_curves(
        curves, xlabel=spec.x_label if spec else "lag time",
        ylabel=spec.y_label if spec else "g₂", logx=True,
        title=f"{spec.label if spec else chosen}"))


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

RENDER = {"curve": render_curves, "image": render_images,
          "volume": render_volumes, "correlation": render_correlation}

tabs = st.tabs([modality_registry.GROUP_LABELS[g] for g in groups])
for tab, group in zip(tabs, groups):
    with tab:
        RENDER[group]()
