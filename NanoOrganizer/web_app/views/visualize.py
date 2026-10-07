#!/usr/bin/env python3
"""
Visualize — one page for every technique, grouped by what the data *is*.

The tabs are Curves / Images / Volumes / Correlation, which are the four
visualisation groups the modality registry defines. Technique is a selector
inside a tab, not a page of its own: UV-Vis, Raman, IR, XPS and SAXS 1D all
draw through the same code and differ only in their axis captions.

Adding a technique is a registry entry. It needs no change here.

Every tab offers two engines. **Static** is matplotlib, the figure you would
put in a paper. **Interactive** is Plotly: zoom into a shoulder, read a pixel
under the cursor, and — for volumes — turn the thing around, which no
projection substitutes for. The controls live in
``web_app/components/plot_controls.py`` so the four tabs share one vocabulary.
"""

from typing import List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from NanoOrganizer.analysis import reading
from NanoOrganizer.analysis.imaging import segment_micrograph
from NanoOrganizer.core import modality as modality_registry
from NanoOrganizer.viz import plots
from NanoOrganizer.web_app.components import plot_controls as controls
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


def interactive_available() -> bool:
    try:
        import plotly  # noqa: F401
    except ImportError:
        return False
    return True


HAS_PLOTLY = interactive_available()
if not HAS_PLOTLY:
    st.caption("Plotly is not installed, so only static figures are drawn. "
               "`pip install \"nanoorganizer[web]\"` adds the interactive ones.")


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

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
    """Choose one measurement by sample id, and by role where that differs."""
    if not measurements:
        return None

    roles = sorted({m.role for m in measurements if m.role})
    if roles and len(roles) > 1:
        role = st.selectbox("Role", ["(all)"] + roles, key=f"{key}_role",
                            help="Two measurements of the same technique on "
                                 "one sample — an as-made and a post-reaction "
                                 "scan, say.")
        if role != "(all)":
            measurements = [m for m in measurements if m.role == role]
    if not measurements:
        return None

    by_sample = {}
    for m in measurements:
        label = f"{m.sample_id} · {m.role}" if m.role else m.sample_id
        by_sample[label] = m
    label = st.selectbox("Sample", list(by_sample), key=f"{key}_sample")
    return by_sample[label]


def show_interactive(figure, fixed_width=None):
    """Render a Plotly figure.

    Note the asymmetry with ``st.pyplot``: as of Streamlit 1.50 that takes
    ``width="stretch"`` while ``st.plotly_chart`` still takes
    ``use_container_width``. Passing ``width=`` here does not fail — it is
    swallowed into Plotly's config and warns, which is worse.
    """
    st.plotly_chart(figure, use_container_width=fixed_width is None)


def show_static(fig_or_ax):
    """Render a matplotlib axes/figure and release it."""
    axes = fig_or_ax
    figure = axes[0].figure if isinstance(axes, (list, np.ndarray)) else axes.figure
    st.pyplot(figure, width="stretch")
    plt.close(figure)


def _range_of(values) -> Optional[Tuple[float, float]]:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return None
    return float(array.min()), float(array.max())


# ---------------------------------------------------------------------------
# Curves
# ---------------------------------------------------------------------------

def draw_curves(curves, style, *, colorbar_values=None, colorbar_label="",
                colorscale="Viridis"):
    """Draw ``[(label, x, y), …]`` through whichever engine is selected."""
    if style.interactive and HAS_PLOTLY:
        from NanoOrganizer.viz import interactive

        figure = interactive.curves_figure(
            curves, colors=style.colors, marker=style.marker,
            marker_size=style.marker_size, dash=style.dash,
            line_width=style.line_width, opacity=style.opacity,
            logx=style.logx, logy=style.logy, xlim=style.xlim, ylim=style.ylim,
            xlabel=style.xlabel, ylabel=style.ylabel, title=style.title,
            show_legend=style.show_legend, show_grid=style.show_grid,
            legend_position=style.legend_position,
            width=style.width, height=style.height,
            colorbar_values=colorbar_values, colorbar_label=colorbar_label,
            colorscale=colorscale)
        show_interactive(figure, style.width)
        return

    figsize = ((style.width / 100.0, style.height / 100.0)
               if style.width else (8.0, style.height / 100.0))
    colour = style.colors[0] if style.colors else None

    if colorbar_values is not None:
        _static_ramp(curves, style, colorbar_values, colorbar_label, figsize)
        return

    show_static(plots.plot_curves(
        curves, xlabel=style.xlabel, ylabel=style.ylabel, title=style.title,
        logx=style.logx, logy=style.logy, color=colour,
        linewidth=style.line_width,
        linestyle=controls.MPL_DASHES.get(style.dash, "-"),
        marker=controls.MPL_MARKERS.get(style.marker, ""),
        markersize=style.marker_size, alpha=style.opacity,
        xlim=style.xlim, ylim=style.ylim, grid=style.show_grid,
        legend=style.show_legend, figsize=figsize))


def _static_ramp(curves, style, values, label, figsize):
    """Matplotlib version of a colour-ramped series, with its colour bar."""
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    values = np.asarray(values, dtype=float)
    cmap = plots.sequential_cmap()
    norm = Normalize(vmin=float(values.min()), vmax=float(values.max()))

    figure, ax = plt.subplots(figsize=figsize)
    for (_, x, y), value in zip(curves, values):
        ax.plot(x, y, linewidth=style.line_width,
                linestyle=controls.MPL_DASHES.get(style.dash, "-"),
                marker=controls.MPL_MARKERS.get(style.marker, ""),
                markersize=style.marker_size, alpha=style.opacity,
                color=cmap(norm(value)))
    if style.logx:
        ax.set_xscale("log")
    if style.logy:
        ax.set_yscale("log")
    if style.xlim:
        ax.set_xlim(*style.xlim)
    if style.ylim:
        ax.set_ylim(*style.ylim)

    plots.style(ax, style.xlabel, style.ylabel, style.title)
    ax.grid(style.show_grid, color=plots.GRID, linewidth=0.8, alpha=0.9)
    bar = figure.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax)
    bar.set_label(label, color=plots.INK_SOFT, fontsize=9)
    bar.outline.set_visible(False)
    bar.ax.tick_params(colors=plots.INK_SOFT, labelsize=8)
    st.pyplot(figure, width="stretch")
    plt.close(figure)


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

    x_label = spec.x_label if spec else "x"
    y_label = spec.y_label if spec else "signal"

    if mode == "Compare samples":
        reduce = st.selectbox(
            "One curve per sample from", ["last frame", "mean of all frames",
                                          "first frame"],
            key="nano_curve_reduce")
        curves, problems = [], []
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
            label = (f"{measurement.sample_id} · {measurement.role}"
                     if measurement.role else measurement.sample_id)
            curves.append((label, x, y))

        if problems:
            st.warning("Skipped — " + "; ".join(problems[:3]), icon="⚠️")
        if not curves:
            st.error("Nothing could be read.", icon="🚫")
            return

        style = controls.curve_controls(
            "nano_curve_cmp", spec=spec,
            data_range={"x": _range_of(np.concatenate([c[1] for c in curves])),
                        "y": _range_of(np.concatenate([c[2] for c in curves]))},
            default_labels=(x_label, y_label))
        draw_curves(curves, style)
        return

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

    style = controls.curve_controls(
        "nano_curve_one_style", spec=spec,
        data_range={"x": _range_of(x), "y": _range_of(matrix)},
        default_labels=(x_label, y_label))

    if matrix.shape[0] == 1:
        draw_curves([(measurement.sample_id, x, matrix[0])], style)
        return

    labels = info.get("labels") or [f"frame {i}" for i in range(matrix.shape[0])]
    max_curves = st.slider("Curves to draw", 2, min(200, matrix.shape[0]),
                           min(40, matrix.shape[0]), key="nano_curve_maxn")
    step = max(1, matrix.shape[0] // max_curves)
    indices = list(range(0, matrix.shape[0], step))

    times = info.get("t_s")
    curves = [(str(labels[i]) if i < len(labels) else f"frame {i}",
               x, matrix[i]) for i in indices]

    if times is not None:
        draw_curves(curves, style,
                    colorbar_values=[float(times[i]) for i in indices],
                    colorbar_label="time (s)")
    else:
        draw_curves(curves, style)

    if times is not None:
        band = st.number_input(
            "Trace one band over time (x value)",
            value=float(np.median(x)), key="nano_curve_band")
        index = int(np.argmin(np.abs(x - band)))
        trace_style = controls.CurveStyle(
            engine=style.engine, xlabel="time (min)",
            ylabel=f"signal at {x[index]:.1f}",
            title=f"{measurement.sample_id} — band trace",
            marker="circle", height=380)
        draw_curves([(f"{x[index]:.1f}", np.asarray(times) / 60.0,
                      matrix[:, index])], trace_style)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def draw_image(array, style, *, title: str = "", xlabel: str = "",
               ylabel: str = "", extent=None, unit: str = ""):
    """Draw a 2D array through whichever engine is selected."""
    display = np.asarray(array, dtype=float)
    if style.log_intensity:
        positive = display[display > 0]
        floor = float(positive.min()) if positive.size else 1.0
        display = np.log10(np.clip(display, floor, None))

    if style.vmin is not None and style.vmax is not None:
        low, high = style.vmin, style.vmax
    else:
        low = float(np.nanpercentile(display, 100.0 - style.percentile))
        high = float(np.nanpercentile(display, style.percentile))

    heading = style.title or title

    if style.interactive and HAS_PLOTLY:
        from NanoOrganizer.viz import interactive

        if style.as_surface:
            figure = interactive.surface_figure(
                display, colorscale=style.colorscale, title=heading,
                xlabel=xlabel or "x", ylabel=ylabel or "y",
                height=style.height, width=style.width)
        else:
            figure = interactive.image_figure(
                display, colorscale=style.colorscale, vmin=low, vmax=high,
                title=heading, xlabel=xlabel, ylabel=ylabel,
                equal_aspect=style.equal_aspect, reverse_y=style.reverse_y,
                show_colorbar=style.show_colorbar, extent=extent,
                width=style.width, height=style.height, hover_unit=unit)
        show_interactive(figure, style.width)
        return

    size = ((style.width / 100.0, style.height / 100.0) if style.width
            else (6.5, style.height / 100.0))
    figure, ax = plt.subplots(figsize=size)
    image = ax.imshow(display, cmap=style.cmap, vmin=low, vmax=high,
                      interpolation="nearest",
                      origin="upper" if style.reverse_y else "lower",
                      extent=extent,
                      aspect="equal" if style.equal_aspect else "auto")
    if extent is None:
        ax.set_xticks([])
        ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    if heading:
        ax.set_title(heading, color=plots.INK, fontsize=10, loc="left")
    if xlabel:
        ax.set_xlabel(xlabel, color=plots.INK_SOFT, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, color=plots.INK_SOFT, fontsize=10)
    if style.show_colorbar:
        bar = figure.colorbar(image, ax=ax, fraction=0.046)
        bar.outline.set_visible(False)
        bar.ax.tick_params(colors=plots.INK_SOFT, labelsize=8)
    st.pyplot(figure, width="stretch")
    plt.close(figure)


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

    style = controls.image_controls("nano_image_style",
                                    data_range=_range_of(array))

    spec = modality_registry.get(chosen)
    scale = info.get("nm_per_pixel")
    extent = None
    axis_label = ""
    if scale:
        # Calibrated: label the axes in nanometres rather than pixels, so a
        # distance read off the plot means something.
        height_px, width_px = array.shape
        extent = (0.0, width_px * scale, height_px * scale, 0.0)
        axis_label = "nm"

    caption = f"{info['file']} — {array.shape[1]}×{array.shape[0]} px"
    if scale:
        caption += (f", {scale:.3f} nm/px "
                    f"({array.shape[1] * scale / 1000:.3f} µm wide)")

    draw_image(array, style, title=caption,
               xlabel=axis_label or (spec.x_label if spec else ""),
               ylabel=axis_label or (spec.y_label if spec else ""),
               extent=extent)

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
                    # Two calls: segment (analysis), then draw what it found.
                    segmentation = segment_micrograph(
                        measurement, workbench.resolver, image_index=index,
                        min_contrast_frac=contrast)
                    show_static(plots.plot_segmentation(segmentation))
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

    style = controls.volume_controls("nano_vol", volume.shape,
                                     value_range=_range_of(volume))

    if style.interactive and HAS_PLOTLY:
        from NanoOrganizer.viz import interactive

        budget = style.budget ** 3
        _, step = interactive.downsample(volume, budget)
        if step > 1:
            st.caption(
                f"Rendering every {step}th voxel "
                f"({'×'.join(str(n // step) for n in volume.shape)}). "
                f"Raise **Detail** for more, at the cost of responsiveness.")
        with st.spinner("Building the 3D figure…"):
            figure = interactive.volume_figure(
                volume, mode=style.mode, colorscale=style.colorscale,
                level=style.level, opacity=style.opacity,
                surface_count=style.surface_count, max_voxels=budget,
                slice_fractions=style.slice_fractions,
                height=style.height, title=measurement.sample_id)
        show_interactive(figure)
        st.caption("Drag to rotate · scroll to zoom · double-click to reset.")
        return

    axis, n_planes = style.axis, volume.shape[style.axis]
    if style.projection == "single slice":
        plane = np.take(volume, style.slab_centre, axis=axis)
        title = f"plane {style.slab_centre} along axis {axis}"
    else:
        low = max(style.slab_centre - style.slab_thickness // 2, 0)
        high = min(low + style.slab_thickness, n_planes)
        block = np.take(volume, range(low, high), axis=axis)
        reducer = block.mean if style.projection == "mean projection" else block.max
        plane = reducer(axis=axis)
        kind = "mean" if style.projection == "mean projection" else "max"
        title = (f"{kind} of planes {low}–{high - 1} along axis {axis}"
                 if high - low < n_planes else f"{kind} along axis {axis}")

    flat = controls.ImageStyle(engine=controls.STATIC, cmap=style.cmap,
                               title=title, height=620)
    draw_image(plane, flat)


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
        style = controls.image_controls("nano_corr_style",
                                        data_range=_range_of(array))
        draw_image(array, style,
                   title=f"{measurement.sample_id} — two-time correlation",
                   xlabel=spec.x_label, ylabel=spec.y_label)
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

    style = controls.curve_controls(
        "nano_corr_curve", spec=spec,
        data_range={"x": _range_of(np.concatenate([c[1] for c in curves])),
                    "y": _range_of(np.concatenate([c[2] for c in curves]))},
        default_labels=(spec.x_label if spec else "lag time",
                        spec.y_label if spec else "g₂"))
    draw_curves(curves, style)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

RENDER = {"curve": render_curves, "image": render_images,
          "volume": render_volumes, "correlation": render_correlation}

tabs = st.tabs([modality_registry.GROUP_LABELS[g] for g in groups])
for tab, group in zip(tabs, groups):
    with tab:
        RENDER[group]()
