#!/usr/bin/env python3
"""
Plots for analysis results — one house style, used by the notebooks and the GUI.

Every function takes an :class:`~NanoOrganizer.analysis.result.AnalysisResult`
or a dataframe and returns the matplotlib ``Axes`` it drew on, so a notebook can
keep styling afterwards and a Streamlit page can hand the figure straight to
``st.pyplot``.

Colour rules, applied here rather than left to each caller:

* **Categorical hues are assigned in fixed order and never cycled.** Slot *n*
  always means the same series, so adding a curve cannot repaint the others.
* **Scatter plots cap at three categories.** Eight hues are separable when they
  sit side by side in a legend, but not when every pair must be told apart
  across a scatter; past three, the rest fold into a neutral "Other".
* **Magnitude uses one hue, light to dark** — never a rainbow. A spectrum
  series coloured by time reads as time precisely because only lightness moves.
* **A legend is always drawn for two or more series**, so identity never rests
  on colour alone.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Categorical slots, in the order they must be assigned.
CATEGORICAL = (
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
)

# Scatter and other all-pairs forms: only the first three separate reliably.
SCATTER_SLOTS = 3
OTHER_COLOR = "#8a8a84"

# One hue, light to dark, for continuous magnitude (time, temperature, index).
SEQUENTIAL = (
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
    "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
    "#184f95", "#104281", "#0d366b",
)

STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}

INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e4e3df"


def sequential_cmap(name: str = "nano_blue"):
    """The single-hue ramp as a matplotlib colormap."""
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list(name, SEQUENTIAL)


def _axes(ax=None, figsize=(7.0, 4.5)):
    import matplotlib.pyplot as plt
    if ax is not None:
        return ax
    _, ax = plt.subplots(figsize=figsize)
    return ax


def style(ax, xlabel: str = "", ylabel: str = "", title: str = ""):
    """Apply the house style: recessive axes, light grid, no chartjunk."""
    ax.set_facecolor("none")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_SOFT, labelsize=9, length=3)
    ax.grid(True, color=GRID, linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK_SOFT, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK_SOFT, fontsize=10)
    if title:
        ax.set_title(title, color=INK, fontsize=11, loc="left")
    return ax


def _legend(ax, **kwargs):
    """A legend in text ink, not series colour, with no heavy frame."""
    legend = ax.legend(frameon=False, fontsize=9, **kwargs)
    for text in legend.get_texts():
        text.set_color(INK_SOFT)
    return legend


def category_colors(labels: Sequence, scatter: bool = False
                    ) -> Tuple[Dict[Any, str], List]:
    """Map categories onto fixed slots; return ``(colors, folded)``.

    ``folded`` lists the categories that exceeded the usable number of slots
    and were collapsed into a neutral "Other" — the caller should say so.
    """
    seen = list(dict.fromkeys(labels))
    limit = SCATTER_SLOTS if scatter else len(CATEGORICAL)
    colors = {key: CATEGORICAL[i] for i, key in enumerate(seen[:limit])}
    folded = seen[limit:]
    for key in folded:
        colors[key] = OTHER_COLOR
    return colors, folded


# ---------------------------------------------------------------------------
# Kinetics
# ---------------------------------------------------------------------------

def plot_kinetics(result, axes=None, time_unit: str = "min"):
    """Two panels: the raw band traces, and ``ln(A/A0)`` with the fitted window.

    The two absorbance traces share one axis because they are the same
    quantity; the log-ratio gets its own panel rather than a second y-scale,
    which would make the two curves' crossings meaningless.
    """
    import matplotlib.pyplot as plt

    if not result.curves:
        raise ValueError(f"{result.analysis} produced no curves to plot")

    if axes is None:
        _, axes = plt.subplots(1, 2, figsize=(12.0, 4.5))
    left, right = axes

    scale = 60.0 if time_unit == "min" else 1.0
    t = np.asarray(result.curves["t_s"], dtype=float) / scale
    band_nm = result.diagnostics.get("band_nm", 400.0)
    product_nm = result.diagnostics.get("product_nm", 300.0)

    left.plot(t, result.curves["a_band"], color=CATEGORICAL[0], linewidth=2,
              label=f"{band_nm:.0f} nm (reactant)")
    left.plot(t, result.curves["a_product"], color=CATEGORICAL[1], linewidth=2,
              label=f"{product_nm:.0f} nm (product)")
    style(left, f"time ({time_unit})", "absorbance",
          f"{result.sample_id} — band traces")
    _legend(left)

    ln_ratio = np.asarray(result.curves["ln_ratio"], dtype=float)
    right.plot(t, ln_ratio, color=CATEGORICAL[0], linewidth=0,
               marker="o", markersize=3.5, alpha=0.55, label="data")

    fit_t = np.asarray(result.curves["fit_t_s"], dtype=float) / scale
    if fit_t.size:
        right.axvspan(fit_t[0], fit_t[-1], color=CATEGORICAL[0], alpha=0.07,
                      linewidth=0)
        right.plot(fit_t, result.curves["fit_ln_ratio"], color=STATUS["critical"],
                   linewidth=2, label="fitted region")

    k_app = result.values.get("k_app", float("nan"))
    r2 = result.values.get("k_app_r2", float("nan"))
    right.annotate(
        f"$k_{{app}}$ = {k_app:.3g} s$^{{-1}}$\n$R^2$ = {r2:.4f}\n"
        f"n = {result.diagnostics.get('fit_points', 0)}",
        xy=(0.97, 0.95), xycoords="axes fraction", ha="right", va="top",
        fontsize=9, color=INK_SOFT,
    )
    style(right, f"time ({time_unit})", f"ln(A/A$_0$) at {band_nm:.0f} nm",
          "pseudo-first-order fit")
    _legend(right, loc="lower left")
    return axes


# ---------------------------------------------------------------------------
# Spectra
# ---------------------------------------------------------------------------

def plot_series(x, matrix, values=None, ax=None, *, max_curves: int = 40,
                xlabel: str = "x", ylabel: str = "signal", title: str = "",
                colorbar_label: str = "", xlim=None, ylim=None,
                colorbar: bool = True, logx: bool = False, logy: bool = False,
                figsize: Optional[Tuple[float, float]] = None,
                linewidth: float = 1.1, **line_options):
    """A stack of curves coloured light-to-dark by *values*. **Kernel.**

    ``matrix`` is ``(n_curves, len(x))``; ``values`` is one number per curve —
    a time, a temperature, a dose. Only lightness carries it, so the ordering
    reads correctly for a colour-blind viewer and in greyscale, and a colour
    bar replaces a legend of forty timestamps.

    At most *max_curves* are drawn, **strided** rather than truncated: forty
    lines evenly spaced across a run say what the run did, while the first
    forty of four hundred say only what its first minute did.
    """
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    x = np.asarray(x, dtype=float)
    matrix = np.atleast_2d(np.asarray(matrix, dtype=float))
    if matrix.shape[1] != x.size:
        raise ValueError(
            f"each row must have {x.size} points, got {matrix.shape[1]}")

    values = (np.arange(matrix.shape[0], dtype=float) if values is None
              else np.asarray(values, dtype=float))
    if values.size != matrix.shape[0]:
        raise ValueError(
            f"need one value per curve: {values.size} vs {matrix.shape[0]}")

    ax = _axes(ax, figsize=figsize or (7.5, 4.8))
    step = max(1, matrix.shape[0] // max_curves)
    cmap = sequential_cmap()
    low, high = float(np.nanmin(values)), float(np.nanmax(values))
    norm = Normalize(vmin=low, vmax=high if high > low else low + 1.0)

    for index in range(0, matrix.shape[0], step):
        ax.plot(x, matrix[index], linewidth=linewidth,
                color=cmap(norm(values[index])), **line_options)

    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")

    style(ax, xlabel, ylabel, title)
    if xlim:
        ax.set_xlim(*xlim)
    if ylim:
        ax.set_ylim(*ylim)
    if colorbar:
        bar = ax.figure.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax)
        bar.set_label(colorbar_label, color=INK_SOFT, fontsize=9)
        bar.ax.tick_params(colors=INK_SOFT, labelsize=8)
        bar.outline.set_visible(False)
    return ax


def plot_spectra(result, ax=None, max_curves: int = 40,
                 xlim: Optional[Tuple[float, float]] = None,
                 colorbar: bool = True):
    """Spectra over a run. **Adapter over** :func:`plot_series`."""
    spectra = np.asarray(result.curves["spectra"], dtype=float)
    times = np.asarray(result.curves.get("t_s", np.arange(len(spectra))),
                       dtype=float)
    return plot_series(
        result.curves["wavelength"], spectra, times, ax=ax,
        max_curves=max_curves, xlabel="wavelength (nm)", ylabel="absorbance",
        title=f"{result.sample_id} — {len(spectra)} spectra",
        colorbar_label="time (s)", xlim=xlim, colorbar=colorbar)


def plot_marked_curve(x, y, ax=None, *, mark=None, width=None,
                      xlabel: str = "x", ylabel: str = "signal",
                      title: str = "", label: str = "",
                      mark_label: str = "", unit: str = ""):
    """One curve with a position and a width marked on it. **Kernel.**

    *mark* draws a vertical line; *width* shades a band of that total width
    centred on it. Both are optional, so this also serves as the plain
    single-curve plot in the house style.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape != y.shape:
        raise ValueError(f"x and y must match: {x.shape} vs {y.shape}")

    ax = _axes(ax)
    ax.plot(x, y, color=CATEGORICAL[0], linewidth=2, label=label or None)

    suffix = f" {unit}" if unit else ""
    if mark is not None and np.isfinite(mark):
        ax.axvline(float(mark), color=STATUS["critical"], linewidth=1.5,
                   linestyle="--",
                   label=mark_label or f"peak {mark:.1f}{suffix}")
        if width is not None and np.isfinite(width):
            ax.axvspan(mark - width / 2, mark + width / 2,
                       color=STATUS["critical"], alpha=0.08, linewidth=0,
                       label=f"FWHM {width:.1f}{suffix}")

    style(ax, xlabel, ylabel, title)
    if ax.get_legend_handles_labels()[0]:
        _legend(ax)
    return ax


def plot_endpoint_spectrum(result, ax=None):
    """The endpoint spectrum, peak and FWHM marked.

    **Adapter over** :func:`plot_marked_curve`.
    """
    return plot_marked_curve(
        result.curves["wavelength"], result.curves["endpoint_spectrum"],
        ax=ax,
        mark=result.values.get("spr_peak_nm", float("nan")),
        width=result.values.get("spr_fwhm_nm", float("nan")),
        xlabel="wavelength (nm)", ylabel="absorbance",
        title=f"{result.sample_id} — plasmon band",
        label="endpoint spectrum", unit="nm")


# ---------------------------------------------------------------------------
# Size distribution and segmentation
# ---------------------------------------------------------------------------

def plot_distribution(values, ax=None, *, bins: int = 40, unit: str = "nm",
                      xlabel: str = "", title: str = ""):
    """A histogram with the mean and median marked. **Kernel.**

    Both are drawn because they disagree whenever unseparated clusters survive
    into the tail, and the gap between them is the honest signal that they did.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValueError("nothing to plot: no finite values")

    ax = _axes(ax)
    ax.hist(values, bins=bins, color=CATEGORICAL[0], alpha=0.85,
            edgecolor="white", linewidth=0.5)

    mean = float(values.mean())
    median = float(np.median(values))
    ax.axvline(mean, color=STATUS["critical"], linewidth=1.8,
               label=f"mean {mean:.1f} {unit}".strip())
    ax.axvline(median, color=CATEGORICAL[1], linewidth=1.8, linestyle="--",
               label=f"median {median:.1f} {unit}".strip())

    style(ax, xlabel or f"value ({unit})" if unit else "value", "count", title)
    _legend(ax)
    return ax


def plot_size_distribution(result, ax=None, bins: int = 40):
    """Pooled particle sizes. **Adapter over** :func:`plot_distribution`."""
    diameters = np.asarray(result.curves.get("diameters", []), dtype=float)
    if diameters.size == 0:
        raise ValueError("no particles were measured")

    unit = result.diagnostics.get("unit", "nm")
    return plot_distribution(
        diameters, ax=ax, bins=bins, unit=unit,
        xlabel=f"equivalent diameter ({unit})",
        title=f"{result.sample_id} — n = {diameters.size} particles "
              f"from {result.values.get('n_images', '?')} images")


def plot_outlines(image, labels, ax=None, *, window: int = 700,
                  title: str = "", color=(0.89, 0.23, 0.23)):
    """Particle outlines over the raw image. **Kernel.**

    Takes the image and its label map, so it draws any segmentation — this
    package's, scikit-image's, or one you did by hand.

    Always look at this before trusting a size distribution: over-splitting and
    film texture both produce a plausible-looking histogram.
    """
    from skimage.segmentation import find_boundaries

    image = np.asarray(image, dtype=float)
    labels = np.asarray(labels)
    if image.shape != labels.shape:
        raise ValueError(
            f"image and labels must match: {image.shape} vs {labels.shape}")

    cut = (slice(0, min(window, image.shape[0])),
           slice(0, min(window, image.shape[1])))
    tile = image[cut]
    span = float(np.ptp(tile)) or 1e-9
    normalised = (tile - tile.min()) / span
    overlay = np.dstack([normalised] * 3)
    overlay[find_boundaries(labels[cut], mode="outer")] = list(color)

    ax = _axes(ax, figsize=(6.0, 6.0))
    ax.imshow(overlay, interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    if title:
        ax.set_title(title, color=INK, fontsize=11, loc="left")
    return ax


def plot_segmentation(measurement, resolver, ax=None, image_index: int = 0,
                      window: int = 700, **options):
    """Segment a micrograph and draw it. **Adapter over** :func:`plot_outlines`.

    Reads the frame, runs the segmentation, and labels the figure with the
    file and the pixel calibration.
    """
    from NanoOrganizer.analysis.imaging import read_micrograph, segment_particles

    paths = measurement.resolve(resolver)
    if not paths:
        raise FileNotFoundError(f"no images for {measurement.measurement_id}")

    path = paths[image_index]
    image, scale, _ = read_micrograph(path)
    min_diameter = options.pop("min_diameter_nm", 2.0)
    min_area = np.pi * (0.5 * min_diameter / scale) ** 2 if scale else 20.0
    labels, info = segment_particles(image, min_area_px=int(max(min_area, 4)),
                                     **options)

    scale_text = f"{scale:.3f} nm/px" if scale else "uncalibrated"
    return plot_outlines(
        image, labels, ax=ax, window=window,
        title=f"{path.name} — {int(labels.max())} particles, {scale_text}")


# ---------------------------------------------------------------------------
# Structure–property comparison
# ---------------------------------------------------------------------------

def plot_compare(frame, x: str, y: str, color_by: str = "", ax=None,
                 yerr: str = "", label_points: bool = True,
                 logy: bool = False):
    """Scatter one derived quantity against a synthesis parameter.

    This is the plot the whole pipeline exists to produce. *color_by* is capped
    at three categories, because a scatter asks the eye to separate every pair
    of colours at once rather than just neighbouring ones; anything beyond
    three folds into "Other" and is reported in the legend.
    """
    ax = _axes(ax, figsize=(7.0, 5.0))

    work = frame.dropna(subset=[x, y]).copy()
    if work.empty:
        raise ValueError(f"no rows have both {x!r} and {y!r}")

    if color_by and color_by in work.columns:
        groups = work[color_by].astype(str)
        colors, folded = category_colors(groups.tolist(), scatter=True)
        for key in dict.fromkeys(groups):
            mask = groups == key
            name = "Other" if key in folded else key
            ax.errorbar(
                work.loc[mask, x], work.loc[mask, y],
                yerr=work.loc[mask, yerr] if yerr and yerr in work else None,
                fmt="o", markersize=9, color=colors[key], label=name,
                linestyle="none", capsize=3, elinewidth=1,
                markeredgecolor="white", markeredgewidth=1.2,
            )
        if folded:
            ax.annotate(f"{len(folded)} more folded into “Other”",
                        xy=(0.02, 0.02), xycoords="axes fraction",
                        fontsize=8, color=INK_SOFT)
        # Deduplicate the legend when several keys folded into "Other".
        handles, names = ax.get_legend_handles_labels()
        unique = dict(zip(names, handles))
        legend = ax.legend(unique.values(), unique.keys(), frameon=False,
                           fontsize=9, title=color_by)
        legend.get_title().set_color(INK_SOFT)
        legend.get_title().set_fontsize(9)
        for text in legend.get_texts():
            text.set_color(INK_SOFT)
    else:
        ax.errorbar(work[x], work[y],
                    yerr=work[yerr] if yerr and yerr in work else None,
                    fmt="o", markersize=9, color=CATEGORICAL[0],
                    linestyle="none", capsize=3, elinewidth=1,
                    markeredgecolor="white", markeredgewidth=1.2)

    if label_points and "sample_id" in work.columns and len(work) <= 20:
        for _, row in work.iterrows():
            ax.annotate(str(row["sample_id"]).replace("Sample", "S"),
                        xy=(row[x], row[y]), xytext=(6, 4),
                        textcoords="offset points", fontsize=8, color=INK_SOFT)

    if logy:
        ax.set_yscale("log")
    style(ax, x.split(".")[-1], y.split(".")[-1], f"{y.split('.')[-1]} vs "
          f"{x.split('.')[-1]}")
    return ax


def plot_curves(curves: Sequence[Tuple[str, np.ndarray, np.ndarray]], ax=None,
                xlabel: str = "", ylabel: str = "", title: str = "",
                logx: bool = False, logy: bool = False,
                color: Optional[str] = None,
                linewidth: float = 1.8, linestyle: str = "-",
                marker: str = "", markersize: float = 6.0,
                alpha: float = 1.0,
                xlim: Optional[Tuple[float, float]] = None,
                ylim: Optional[Tuple[float, float]] = None,
                grid: bool = True, legend: bool = True,
                legend_loc: str = "best",
                figsize: Optional[Tuple[float, float]] = None):
    """Overlay named 1D curves — the generic comparison plot.

    *curves* is a sequence of ``(label, x, y)``. Hues are assigned in slot
    order; past eight series the rest are drawn neutral and the caller is told,
    because a ninth generated hue would collide with one of the first eight.

    The styling arguments all default to the house style, so the common call
    stays one line. Pass *color* to draw every curve in one colour — right
    when the curves are a series rather than separate things, and the legend
    is doing no work.
    """
    ax = _axes(ax, figsize=figsize or (7.0, 4.5))
    labels = [c[0] for c in curves]
    colors, folded = category_colors(labels, scatter=False)

    for label, x, y in curves:
        ax.plot(x, y, linewidth=linewidth, linestyle=linestyle,
                marker=marker or "", markersize=markersize, alpha=alpha,
                color=color or colors[label],
                label="Other" if label in folded else label)

    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    if xlim:
        ax.set_xlim(*xlim)
    if ylim:
        ax.set_ylim(*ylim)

    style(ax, xlabel, ylabel, title)
    ax.grid(grid, color=GRID, linewidth=0.8, alpha=0.9)
    if legend and len(curves) >= 2:
        handles, names = ax.get_legend_handles_labels()
        unique = dict(zip(names, handles))
        _legend(ax, handles=list(unique.values()), labels=list(unique.keys()),
                loc=legend_loc)
    return ax


def plot_fit(x, y, y_fit, residual=None, *, axes=None, xlabel: str = "x",
             ylabel: str = "signal", title: str = "",
             data_label: str = "data", fit_label: str = "fit",
             figsize: Tuple[float, float] = (7.0, 5.6)):
    """A fitted curve over its data, with the residuals beneath. **Kernel.**

    Arrays in, ``Axes`` out — no result object, no analysis, no project — so
    any ``x, y, y_fit`` draws in the house style::

        fit = fit_peaks(x, Y[0], n_peaks=2)
        plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, xlabel="q (1/Å)")

    The residual panel is where a bad fit shows: a fitted line drawn over data
    is persuasive whatever it does, and the residual going from noise to shape
    is the thing to look at. Pass ``residual=None`` to draw the top panel only.

    See :func:`plot_peak_fit` for the version that takes an
    :class:`~NanoOrganizer.analysis.result.AnalysisResult`.
    """
    import matplotlib.pyplot as plt

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    y_fit = np.asarray(y_fit, dtype=float)
    if not (x.shape == y.shape == y_fit.shape):
        raise ValueError(
            f"x, y and y_fit must match: {x.shape}, {y.shape}, {y_fit.shape}")

    wants_residual = residual is not None
    if axes is None:
        if wants_residual:
            _, axes = plt.subplots(
                2, 1, figsize=figsize, sharex=True,
                gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})
        else:
            _, axes = plt.subplots(figsize=(figsize[0], figsize[1] * 0.75))

    pair = np.atleast_1d(axes)
    top = pair[0]
    bottom = pair[1] if wants_residual and pair.size > 1 else None

    top.plot(x, y, linewidth=0, marker="o", markersize=3, alpha=0.5,
             color=CATEGORICAL[0], label=data_label)
    top.plot(x, y_fit, linewidth=2, color=STATUS["critical"], label=fit_label)
    style(top, "" if bottom is not None else xlabel, ylabel, title)
    _legend(top)

    if bottom is not None:
        bottom.axhline(0, color=GRID, linewidth=1)
        bottom.plot(x, np.asarray(residual, dtype=float), linewidth=1.2,
                    color=INK_SOFT)
        style(bottom, xlabel, "residual")

    return axes


def plot_peak_fit(result, axes=None, **options):
    """A fitted curve over its data. **Adapter over** :func:`plot_fit`.

    Unwraps an :class:`~NanoOrganizer.analysis.result.AnalysisResult` and
    supplies the axis caption and title from its diagnostics; all the drawing
    is the kernel's.
    """
    curves = result.curves
    missing = [k for k in ("x", "y", "y_fit") if k not in curves]
    if missing:
        raise ValueError(
            f"{result.analysis} result has no {', '.join(missing)} to plot; "
            f"it carries: {', '.join(curves) or 'nothing'}")

    diagnostics = result.diagnostics or {}
    unit = diagnostics.get("x_unit", "")
    xlabel = diagnostics.get("x_label") or (f"x ({unit})" if unit else "x")
    r2 = result.values.get("fit_r2", float("nan"))

    return plot_fit(
        curves["x"], curves["y"], curves["y_fit"], curves.get("residual"),
        axes=axes, xlabel=xlabel,
        ylabel=diagnostics.get("y_label") or "signal",
        title=options.pop(
            "title",
            f"{result.sample_id} — {diagnostics.get('n_peaks', 1)} peak fit, "
            f"R\u00b2 = {r2:.4f}"),
        **options)


__all__ = [
    # house style
    "CATEGORICAL", "SEQUENTIAL", "STATUS", "sequential_cmap", "style",
    "category_colors",
    # kernels — arrays in, Axes out
    "plot_curves", "plot_fit", "plot_distribution", "plot_outlines",
    "plot_series", "plot_marked_curve",
    # adapters — AnalysisResult in
    "plot_peak_fit", "plot_size_distribution", "plot_segmentation",
    "plot_kinetics", "plot_spectra", "plot_endpoint_spectrum",
    # tables
    "plot_compare",
]
