#!/usr/bin/env python3
"""
Show – draw any measurement, chosen by sample and technique.

The Visualize page dispatches on what the data *is* rather than on which
instrument made it: a measurement's modality names a ``shape``, the shape names
one of four **groups**, and the group names the figure.  That dispatch lived
only inside the Streamlit page, so a notebook could not reach it and had to
know for itself whether its data was a curve or a volume.

This module is that dispatch as library code, which is what makes
``wb.plot("CuAu05", "uvvis")`` and ``wb.plot("CuAu05", "tomo")`` the same
call::

    curve          one line per frame, coloured by time when the names say when
    image / map    a heatmap, calibrated to nm when the file carried a scale
    volume / stack a slab projection (static) or a rotatable render (interactive)
    correlation    g₂ curves, or a two-time map

The page keeps its own widget layer — the sliders and colour pickers of
``web_app/components/plot_controls.py`` have no meaning in a notebook — but the
decisions that affect the *numbers* are here: which frames a time or a
temperature selects, how a many-frame series is strided down, where an image's
display range comes from, and how a volume is projected.

Both engines are here on purpose.  **static** is matplotlib — the figure that
goes in the paper.  **interactive** is Plotly — zoom a shoulder, read a pixel,
turn a tomogram around.  Neither is a wrapper around the other; they return
different objects (an ``Axes`` and a ``go.Figure``) and the caller is told
which by what it asked for.

Every ``*_figure`` here draws where it is told: ``ax=`` for static,
``fig=`` (with ``row=``/``col=`` for a subplot grid) for interactive, and
returns what it drew on. The data steps they share — :func:`curve_data`,
:func:`image_display`, :func:`project_volume` — draw nothing, so their numbers
can be had without a figure.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from NanoOrganizer.analysis import reading
from NanoOrganizer.viz import plots

STATIC = "static"
INTERACTIVE = "interactive"

#: How to collapse a many-frame measurement into one curve.
REDUCERS = ("all", "last", "first", "mean", "max", "sum")


# ---------------------------------------------------------------------------
# Selecting the frames to draw
# ---------------------------------------------------------------------------

def frames(measurement, resolver, **grammar):
    """One row per file: index, name, and the ``t_s``/``T_c`` the name admits.

    See :func:`NanoOrganizer.analysis.frames.frame_table`.
    """
    from NanoOrganizer.analysis import frames as _frames

    return _frames.frame_table(measurement, resolver, **grammar)


def select_frame(measurement, resolver, *, frame=None, t=None, T=None,
                    file: str = "", n_available: int = 0) -> int:
    """Resolve a frame selector to a plain index.

    ``frame=`` alone needs no filename parsing, which matters: most data has
    no grammar at all and must still be addressable by position.
    """
    from NanoOrganizer.analysis import frames as _frames

    if t is None and T is None and not file:
        index = int(frame or 0)
        if n_available and not -n_available <= index < n_available:
            raise IndexError(f"frame {index} of {n_available}")
        return index % n_available if n_available else index

    return _frames.pick_frame(frames(measurement, resolver), frame=frame,
                              t=t, T=T, file=file)


def _times_from_names(measurement, resolver, n_rows: int):
    """Times parsed from filenames, or None if they do not describe the rows.

    The count has to match and every value has to be finite: a partial clock
    would colour some curves by time and the rest by nothing, which reads as
    data rather than as a gap.
    """
    rows = frames(measurement, resolver)
    if len(rows) != n_rows:
        return None
    values = np.array([r["t_s"] for r in rows], dtype=float)
    if not np.all(np.isfinite(values)) or np.all(values == values[0]):
        return None
    return values


def curve_data(measurement, resolver, *, frame=None, t=None, T=None,
               file: str = "", reduce: str = "", crop=None, max_curves: int = 200
               ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Read a measurement as ``(x, Y, info)`` and apply a frame selection.

    ``Y`` keeps two dimensions whatever is asked for — one row when a single
    frame or a reducer was named — so a caller never has to branch on how many
    curves came back.
    """
    x, matrix, info = reading.load_curve_set(measurement, resolver,
                                             max_curves=max_curves, crop=crop)
    info = dict(info)
    labels = list(info.get("labels") or
                  [f"frame {i}" for i in range(matrix.shape[0])])
    times = info.get("t_s")

    if times is None:
        # A folder of two-column files is read as independent curves, so the
        # loader has no clock to report — but the filenames may still carry
        # one, and a series ordered in time should be coloured by it rather
        # than given a legend of forty filenames.
        times = _times_from_names(measurement, resolver, matrix.shape[0])
        if times is not None:
            info["t_s"] = times

    wants_one = frame is not None or t is not None or T is not None or file
    if wants_one:
        if t is not None and T is None and not file and times is not None:
            # The loader already carries the clock; trusting it beats
            # re-parsing filenames, and it is right even when nothing matched
            # a grammar because the times came from inside the files.
            index = int(np.argmin(np.abs(np.asarray(times, dtype=float)
                                         - float(t))))
        else:
            index = select_frame(measurement, resolver, frame=frame, t=t,
                                    T=T, file=file,
                                    n_available=matrix.shape[0])
        if not -matrix.shape[0] <= index < matrix.shape[0]:
            raise IndexError(f"frame {index} of {matrix.shape[0]}")
        info["labels"] = [labels[index]]
        if times is not None:
            info["t_s"] = np.asarray(times)[[index]]
        info["frame"] = index
        return x, matrix[[index]], info

    if reduce and reduce != "all":
        if reduce not in REDUCERS:
            raise ValueError(f"reduce must be one of {REDUCERS}, got {reduce!r}")
        collapsed = {
            "last": lambda m: m[-1], "first": lambda m: m[0],
            "mean": lambda m: m.mean(axis=0), "max": lambda m: m.max(axis=0),
            "sum": lambda m: m.sum(axis=0),
        }[reduce](matrix)
        info["labels"] = [f"{measurement.sample_id} ({reduce})"]
        info["t_s"] = None
        info["reduced"] = reduce
        return x, collapsed[None, :], info

    info["labels"] = labels
    return x, matrix, info


# ---------------------------------------------------------------------------
# Curves
# ---------------------------------------------------------------------------

def curve_figure(measurement, resolver, *, engine: str = STATIC,
                 frame=None, t=None, T=None, file: str = "",
                 reduce: str = "", crop=None, max_curves: int = 40,
                 color_by_time: bool = True, ax=None,
                 title: str = "", xlabel: str = "", ylabel: str = "",
                 logx: Optional[bool] = None, logy: Optional[bool] = None,
                 **options):
    """Draw a 1D measurement: one line per frame.

    With more than *max_curves* frames the series is **strided**, not
    truncated: forty lines evenly spaced across the run say what the run did,
    while the first forty of four hundred say only what its first minute did.

    When the filenames carry a clock, the lines are coloured along one hue by
    time and a colour bar replaces the legend — a legend of forty timestamps
    is not readable, and the ordering is the information.
    """
    spec = measurement.spec
    x, matrix, info = curve_data(measurement, resolver, frame=frame, t=t, T=T,
                                 file=file, reduce=reduce, crop=crop)

    labels = info.get("labels") or [f"frame {i}" for i in range(matrix.shape[0])]
    times = info.get("t_s")

    indices = list(range(matrix.shape[0]))
    if len(indices) > max_curves:
        step = max(1, len(indices) // max_curves)
        indices = indices[::step]

    curves = [(str(labels[i]), x, matrix[i]) for i in indices]
    ramp = ([float(np.asarray(times)[i]) for i in indices]
            if times is not None and color_by_time and len(curves) > 1 else None)

    xlabel = xlabel or (spec.x_label if spec else "x")
    ylabel = ylabel or (spec.y_label if spec else "signal")
    title = title or _caption(measurement, info)
    logx = (spec.log_x if spec else False) if logx is None else logx
    logy = (spec.log_y if spec else False) if logy is None else logy

    if engine == INTERACTIVE:
        from NanoOrganizer.viz import interactive

        return interactive.curves_figure(
            curves, logx=logx, logy=logy, xlabel=xlabel, ylabel=ylabel,
            title=title, colorbar_values=ramp,
            colorbar_label="time (s)" if ramp else "",
            show_legend=ramp is None, **options)

    if ramp is not None:
        # One shared axis, so the colour-ramped series is exactly what
        # plots.plot_series draws; there is no second implementation here.
        return plots.plot_series(
            x, np.vstack([c[2] for c in curves]), ramp, ax=ax,
            max_curves=len(curves), xlabel=xlabel, ylabel=ylabel, title=title,
            logx=logx, logy=logy, colorbar_label="time (s)", **options)

    return plots.plot_curves(curves, ax=ax, xlabel=xlabel, ylabel=ylabel,
                             title=title, logx=logx, logy=logy, **options)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def image_display(array, *, percentile: float = 99.0, vmin=None, vmax=None,
                  log_intensity: bool = False
                  ) -> Tuple[np.ndarray, float, float]:
    """The array as it should be shown, and its display range. Draws nothing.

    Returns ``(display, low, high)``. The range defaults to a symmetric
    *percentile* clip rather than min–max, because one hot pixel otherwise
    flattens the whole frame to grey; *vmin*/*vmax* override it. With
    *log_intensity* the display is ``log10``, floored at the smallest positive
    value so a zero pixel does not become ``-inf``.
    """
    display = np.asarray(array, dtype=float)
    if log_intensity:
        positive = display[display > 0]
        floor = float(positive.min()) if positive.size else 1.0
        display = np.log10(np.clip(display, floor, None))

    if vmin is None or vmax is None:
        low = float(np.nanpercentile(display, 100.0 - percentile))
        high = float(np.nanpercentile(display, percentile))
    else:
        low, high = float(vmin), float(vmax)
    return display, low, high


def image_figure(measurement, resolver, *, engine: str = STATIC,
                 frame=None, t=None, T=None, file: str = "",
                 percentile: float = 99.0, vmin=None, vmax=None,
                 log_intensity: bool = False, cmap: str = "viridis",
                 colorscale: str = "Viridis", equal_aspect: bool = True,
                 calibrate: bool = True, ax=None, title: str = "", **options):
    """Draw a 2D measurement as an image.

    Reads one frame, asks :func:`image_display` for the display range, and
    hands both to :func:`~NanoOrganizer.viz.plots.plot_image` (static) or
    :func:`~NanoOrganizer.viz.interactive.image_figure`. A file that carried a
    pixel calibration is drawn on nanometre axes, so a distance read off the
    picture means something.
    """
    paths = measurement.resolve(resolver)
    index = select_frame(measurement, resolver, frame=frame, t=t, T=T,
                            file=file, n_available=len(paths))
    array, info = reading.load_image(measurement, resolver, index)
    display, low, high = image_display(array, percentile=percentile,
                                       vmin=vmin, vmax=vmax,
                                       log_intensity=log_intensity)

    spec = measurement.spec
    scale = info.get("nm_per_pixel") if calibrate else None
    extent = None
    axis_label = spec.x_label if spec else ""
    if scale:
        height, width = display.shape
        extent = (0.0, width * scale, height * scale, 0.0)
        axis_label = "nm"

    title = title or f"{measurement.sample_id} — {info.get('file', '')}"

    if engine == INTERACTIVE:
        from NanoOrganizer.viz import interactive

        return interactive.image_figure(
            display, colorscale=colorscale, vmin=low, vmax=high, title=title,
            xlabel=axis_label, ylabel=axis_label, extent=extent,
            equal_aspect=equal_aspect, **options)

    return plots.plot_image(display, ax=ax, extent=extent, cmap=cmap,
                            vmin=low, vmax=high, title=title,
                            xlabel=axis_label, ylabel=axis_label,
                            equal_aspect=equal_aspect, **options)


# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------

def project_volume(volume, *, axis: int = 0,
                   projection: str = "max projection",
                   slab: Optional[int] = None, centre: Optional[int] = None
                   ) -> Tuple[np.ndarray, str]:
    """Collapse a 3D array to the plane a static figure shows. Draws nothing.

    Returns ``(plane, detail)``, where *detail* says what was done —
    ``"max of planes 40–87"`` — so a figure title can carry it.
    *projection* is ``"single slice"`` (the plane at *centre*), or a ``mean``
    or ``max`` projection through *slab* planes centred on it; *slab* defaults
    to the whole depth.
    """
    volume = np.asarray(volume)
    if volume.ndim != 3:
        raise ValueError(f"expected a 3D array, got shape {volume.shape}")

    n_planes = volume.shape[axis]
    centre = n_planes // 2 if centre is None else int(centre)
    slab = n_planes if slab is None else int(slab)

    if projection == "single slice":
        plane = np.take(volume, min(max(centre, 0), n_planes - 1), axis=axis)
        return plane, f"plane {centre} of {n_planes}"

    low = max(centre - slab // 2, 0)
    high = min(low + slab, n_planes)
    block = np.take(volume, range(low, high), axis=axis)
    kind = "mean" if projection.startswith("mean") else "max"
    plane = block.mean(axis=axis) if kind == "mean" else block.max(axis=axis)
    detail = (f"{kind} through all {n_planes} planes" if high - low >= n_planes
              else f"{kind} of planes {low}–{high - 1}")
    return plane, detail


def volume_figure(measurement, resolver, *, engine: str = STATIC,
                  mode: str = "isosurface", axis: int = 0,
                  projection: str = "max projection", slab: Optional[int] = None,
                  centre: Optional[int] = None, level=None,
                  cmap: str = "viridis", colorscale: str = "Viridis",
                  ax=None, title: str = "", **options):
    """Draw a 3D measurement.

    Static gives a **slab projection** — a mean or max through part of the
    stack, from :func:`project_volume` — because a single plane through a
    150 nm aggregate shows one accident of where the plane fell.  Interactive
    gives the real thing: an isosurface, a translucent volume, points or
    orthogonal slices, rotatable. ``level`` is a control and not a constant,
    since that one number decides what the structure appears to be.
    """
    volume, info = reading.load_volume(measurement, resolver)
    title = title or (f"{measurement.sample_id} — "
                      f"{'×'.join(str(n) for n in volume.shape)}")

    if engine == INTERACTIVE:
        from NanoOrganizer.viz import interactive

        return interactive.volume_figure(volume, mode=mode, level=level,
                                         colorscale=colorscale, title=title,
                                         **options)

    plane, detail = project_volume(volume, axis=axis, projection=projection,
                                   slab=slab, centre=centre)
    options.setdefault("figsize", (6.0, 5.4))
    return plots.plot_image(plane, ax=ax, cmap=cmap,
                            title=f"{title} · {detail} along axis {axis}",
                            **options)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def result_figure(result, *, engine: str = STATIC, ax=None, title: str = "",
                  xlabel: str = "", ylabel: str = "", **options):
    """Draw a stored :class:`AnalysisResult`: the fit over its data.

    A fit with residuals gets the two-panel treatment, because a fitted line
    drawn over data is persuasive whatever it does and the residuals are where
    the lie shows. Anything else is drawn as whatever curves it carries.
    """
    curves = {k: np.asarray(v) for k, v in result.curves.items()}
    x = curves.get("x")
    if x is None:
        raise ValueError(
            f"{result.analysis} result for {result.sample_id} has no 'x' "
            f"curve to plot against; it has: {', '.join(curves) or 'nothing'}")

    diagnostics = result.diagnostics or {}
    xlabel = xlabel or diagnostics.get("x_label") or (
        f"x ({diagnostics['x_unit']})" if diagnostics.get("x_unit") else "x")
    ylabel = ylabel or diagnostics.get("y_label") or "signal"
    r2 = result.values.get("fit_r2")
    title = title or (
        f"{result.sample_id} — {result.analysis}"
        + (f", R² = {r2:.4f}" if isinstance(r2, float) else ""))

    has_fit = "y" in curves and "y_fit" in curves

    if engine == INTERACTIVE:
        from NanoOrganizer.viz import interactive

        drawn = [(name, x, y) for name, y in curves.items()
                 if name != "x" and y.shape == x.shape]
        return interactive.curves_figure(drawn, xlabel=xlabel, ylabel=ylabel,
                                         title=title, **options)

    if has_fit:
        # The fit layout whether or not an Axes was supplied: drawing the
        # residual as one more line beside the data, just because the caller
        # chose where the figure goes, would hide the panel that matters.
        return plots.plot_fit(
            x, curves["y"], curves["y_fit"], curves.get("residual"), ax=ax,
            xlabel=xlabel, ylabel=ylabel, title=title, **options)

    drawn = [(name, x, y) for name, y in curves.items()
             if name != "x" and y.shape == x.shape]
    return plots.plot_curves(drawn, ax=ax, xlabel=xlabel, ylabel=ylabel,
                             title=title, **options)


def figure(measurement, resolver, *, engine: str = STATIC, **options):
    """Draw *measurement* with whatever figure its group calls for.

    Returns a matplotlib ``Axes`` for ``engine="static"`` and a Plotly
    ``Figure`` for ``engine="interactive"``.  Unknown keywords go to the
    group's own function, so ``level=`` reaches a volume and ``percentile=``
    reaches an image without this function knowing about either.
    """
    if engine not in (STATIC, INTERACTIVE):
        raise ValueError(
            f"engine must be {STATIC!r} or {INTERACTIVE!r}, got {engine!r}")

    spec = measurement.spec
    group = measurement.group

    if measurement.modality == "fit":
        # A stored result is a bundle, not an array: reading it as one would
        # pick whichever curve happened to be longest.
        from NanoOrganizer.analysis import store as _store

        paths = measurement.resolve(resolver)
        if not paths:
            raise FileNotFoundError(
                f"No file resolves for {measurement.measurement_id}")
        return result_figure(_store.load_result(paths[0]), engine=engine,
                             **options)

    if group == "image" or (spec is not None and spec.shape == "twotime"):
        return image_figure(measurement, resolver, engine=engine, **options)
    if group == "volume":
        return volume_figure(measurement, resolver, engine=engine, **options)
    return curve_figure(measurement, resolver, engine=engine, **options)


def overlay(measurements: Sequence, resolver, *, engine: str = STATIC,
            reduce: str = "last", crop=None, ax=None, title: str = "",
            xlabel: str = "", ylabel: str = "", label_role: bool = True,
            skipped: Optional[List[str]] = None, **options):
    """One curve per measurement — the across-samples comparison plot.

    Each many-frame measurement is collapsed by *reduce* first, because the
    comparison is between samples and forty frames of each would bury it.
    Measurements that cannot be read are **skipped and reported** through the
    *skipped* list rather than taking the figure down: a campaign always has
    one sample whose files are on a mount that is not up today.
    """
    curves: List[Tuple[str, np.ndarray, np.ndarray]] = []
    spec = None

    for measurement in measurements:
        try:
            x, matrix, _ = curve_data(measurement, resolver,
                                      reduce=reduce or "last", crop=crop)
        except Exception as exc:                        # noqa: BLE001
            if skipped is not None:
                skipped.append(f"{measurement.sample_id}: "
                               f"{type(exc).__name__}: {exc}")
            continue
        spec = spec or measurement.spec
        name = (f"{measurement.sample_id} · {measurement.role}"
                if label_role and measurement.role else measurement.sample_id)
        curves.append((name, x, matrix[0]))

    if not curves:
        raise ValueError("none of the selected measurements could be read")

    xlabel = xlabel or (spec.x_label if spec else "x")
    ylabel = ylabel or (spec.y_label if spec else "signal")
    logx = spec.log_x if spec else False
    logy = spec.log_y if spec else False

    if engine == INTERACTIVE:
        from NanoOrganizer.viz import interactive

        return interactive.curves_figure(curves, xlabel=xlabel, ylabel=ylabel,
                                         title=title, logx=logx, logy=logy,
                                         **options)
    return plots.plot_curves(curves, ax=ax, xlabel=xlabel, ylabel=ylabel,
                             title=title, logx=logx, logy=logy, **options)


def _caption(measurement, info: Dict[str, Any]) -> str:
    """A title that says what was drawn, not just which sample it came from."""
    spec = measurement.spec
    name = spec.label if spec else measurement.modality
    parts = [f"{measurement.sample_id} — {name}"]
    if measurement.role:
        parts.append(measurement.role)
    labels = info.get("labels") or []
    if info.get("reduced"):
        parts.append(str(info["reduced"]))
    elif info.get("frame") is not None and labels:
        parts.append(str(labels[0]))
    elif len(labels) > 1:
        parts.append(f"{len(labels)} frames")
    return " · ".join(parts)


__all__ = [
    # drawing — ax= (static) or fig= (interactive) in, the same out
    "figure", "curve_figure", "image_figure", "volume_figure", "overlay",
    "result_figure",
    # data steps — no figure
    "curve_data", "image_display", "project_volume", "frames", "select_frame",
    "STATIC", "INTERACTIVE", "REDUCERS",
]
