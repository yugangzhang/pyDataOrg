#!/usr/bin/env python3
"""
Plot control panels — the knobs, in one place, for every group.

The Visualize page draws four kinds of thing, and all four want most of the
same controls: a colour map or palette, scales and limits, labels, a figure
size, and a choice of rendering engine. Writing those panels once and
returning a plain settings object keeps the page readable and means a control
added here appears everywhere it applies.

Each function returns a frozen dataclass rather than a dict, so a typo in a
field name fails loudly instead of silently reverting to a default.

**Two engines.** *Interactive* builds a Plotly figure — rotate a volume, zoom
a shoulder, read a pixel under the cursor. *Static* builds the matplotlib
figure from :mod:`NanoOrganizer.viz.plots`, which is the one to use for a
figure going into a paper. Volumes default to interactive because a projection
is not a substitute for turning the thing around; everything else defaults to
static, because that is what most people want to keep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

import streamlit as st

from NanoOrganizer.viz import plots

#: Matplotlib colormaps offered, and the Plotly colorscale that matches each.
#:
#: The ``_r`` suffixes are not decoration. Plotly's ``Greys`` runs white to
#: black and ``RdBu`` runs red to blue — both the opposite way round from the
#: matplotlib colormaps of the same name. Without the reversal, switching a
#: TEM micrograph from static to interactive turns the particles from dark to
#: bright, which looks like a different sample rather than a different
#: renderer. Verified by comparing endpoint colours, not by eye.
COLORMAPS: Dict[str, str] = {
    "viridis": "Viridis", "plasma": "Plasma", "inferno": "Inferno",
    "magma": "Magma", "cividis": "Cividis", "turbo": "Turbo",
    "jet": "Jet", "hot": "Hot", "gray": "Greys_r", "bone": "ice",
    "coolwarm": "RdBu_r", "seismic": "RdBu_r", "RdYlBu": "RdYlBu",
}

#: Named line colours for a per-curve override.
NAMED_COLORS: Dict[str, str] = {
    "palette": "", "blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a",
    "yellow": "#eda100", "magenta": "#e87ba4", "green": "#008300",
    "violet": "#4a3aa7", "red": "#e34948", "black": "#0b0b0b",
    "grey": "#8a8a84",
}

MARKER_NAMES = ("none", "circle", "square", "diamond", "triangle up",
                "triangle down", "cross", "x", "star", "pentagon", "hexagon")

DASH_NAMES = ("solid", "dashed", "dash-dot", "dotted", "none")

LEGEND_POSITIONS = ("top right", "top left", "bottom right", "bottom left",
                    "outside")

INTERACTIVE = "Interactive (rotate, zoom, hover)"
STATIC = "Static (publication figure)"

#: Matplotlib marker and line-style codes, for the static engine.
MPL_MARKERS = {"none": "", "circle": "o", "square": "s", "diamond": "D",
               "triangle up": "^", "triangle down": "v", "cross": "P",
               "x": "X", "star": "*", "pentagon": "p", "hexagon": "h"}
MPL_DASHES = {"solid": "-", "dashed": "--", "dash-dot": "-.", "dotted": ":",
              "none": "None"}


# ---------------------------------------------------------------------------
# Settings objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurveStyle:
    engine: str = STATIC
    color_name: str = "palette"
    marker: str = "none"
    marker_size: float = 7.0
    dash: str = "solid"
    line_width: float = 2.0
    opacity: float = 1.0
    logx: bool = False
    logy: bool = False
    xlim: Optional[Tuple[float, float]] = None
    ylim: Optional[Tuple[float, float]] = None
    show_grid: bool = True
    show_legend: bool = True
    legend_position: str = "top right"
    title: str = ""
    xlabel: str = ""
    ylabel: str = ""
    width: Optional[int] = None
    height: int = 520

    @property
    def interactive(self) -> bool:
        return self.engine == INTERACTIVE

    @property
    def colors(self) -> Optional[Tuple[str, ...]]:
        """One repeated colour, or None to use the categorical palette."""
        hex_code = NAMED_COLORS.get(self.color_name, "")
        return (hex_code,) if hex_code else None


@dataclass(frozen=True)
class ImageStyle:
    engine: str = STATIC
    cmap: str = "viridis"
    log_intensity: bool = False
    percentile: float = 99.5
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    equal_aspect: bool = True
    reverse_y: bool = True
    show_colorbar: bool = True
    as_surface: bool = False
    title: str = ""
    width: Optional[int] = None
    height: int = 620

    @property
    def interactive(self) -> bool:
        return self.engine == INTERACTIVE

    @property
    def colorscale(self) -> str:
        return COLORMAPS.get(self.cmap, "Viridis")


@dataclass(frozen=True)
class VolumeStyle:
    engine: str = INTERACTIVE
    mode: str = "isosurface"
    cmap: str = "viridis"
    opacity: float = 0.6
    level: Optional[float] = None
    surface_count: int = 12
    max_points: int = 25000
    budget: int = 60
    slice_fractions: Tuple[float, float, float] = (0.5, 0.5, 0.5)
    # Flat modes
    axis: int = 0
    projection: str = "single slice"
    slab_thickness: int = 16
    slab_centre: int = 0
    height: int = 650

    @property
    def interactive(self) -> bool:
        return self.engine == INTERACTIVE

    @property
    def colorscale(self) -> str:
        return COLORMAPS.get(self.cmap, "Viridis")


@dataclass(frozen=True)
class SeriesStyle:
    """A stack of curves coloured by a value (:func:`~NanoOrganizer.viz.
    plots.plot_series`): which rows, which colours, and the axes."""

    rows: Tuple[int, ...] = ()
    cmap: str = "coolwarm"
    color_range: str = "shown"
    legend: bool = False
    legend_format: str = "{:.3g}"
    legend_fontsize: float = 8.0
    xlim: Optional[Tuple[float, float]] = None
    ylim: Optional[Tuple[float, float]] = None
    logx: bool = False
    logy: bool = False
    title: str = ""
    figsize: Tuple[float, float] = (7.0, 4.4)

    @property
    def plot_options(self) -> Dict[str, Any]:
        """The keywords :func:`plot_series` takes."""
        return dict(y_index_list=list(self.rows), cmap=self.cmap,
                    color_range=self.color_range, legend=self.legend,
                    legend_format=self.legend_format,
                    legend_fontsize=self.legend_fontsize, xlim=self.xlim,
                    ylim=self.ylim, logx=self.logx, logy=self.logy)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def axis_limits(key: str, label: str,
                default: Optional[Tuple[float, float]] = None
                ) -> Optional[Tuple[float, float]]:
    """Axis limits, set or left to the data; *default* starts them set."""
    on = st.checkbox(f"set {label} limits", value=default is not None,
                     key=f"{key}_on")
    low_default, high_default = default or (0.0, 1.0)
    left, right = st.columns(2)
    low = left.number_input(f"{label} min", value=float(low_default),
                            key=f"{key}_lo", format="%g", disabled=not on)
    high = right.number_input(f"{label} max", value=float(high_default),
                              key=f"{key}_hi", format="%g", disabled=not on)
    if not on:
        return None
    if high <= low:
        st.caption(f"⚠️ {label} max must exceed min — left to the data.")
        return None
    return (float(low), float(high))


def figure_size(key: str, default: Tuple[float, float] = (7.0, 4.4)
                ) -> Tuple[float, float]:
    """Width and height in inches — the shape of the figure and, as it is
    drawn to the page's width, the size of its text."""
    left, right = st.columns(2)
    width = left.number_input("width (in)", 2.0, 30.0, float(default[0]), 0.5,
                              key=f"{key}_w")
    height = right.number_input("height (in)", 1.5, 20.0, float(default[1]),
                                0.5, key=f"{key}_h")
    return (float(width), float(height))


def _limit_pair(key: str, label: str, data_range: Optional[Tuple[float, float]]
                ) -> Optional[Tuple[float, float]]:
    """An auto/manual pair of axis limits.

    Defaults are seeded from the data, so switching to manual starts where the
    plot already is instead of collapsing it to (0, 1).
    """
    auto = st.checkbox(f"auto {label}", value=True, key=f"{key}_auto")
    if auto:
        return None

    low_default, high_default = data_range or (0.0, 1.0)
    left, right = st.columns(2)
    low = left.number_input(f"{label} min", value=float(low_default),
                            key=f"{key}_lo", format="%.6g")
    high = right.number_input(f"{label} max", value=float(high_default),
                              key=f"{key}_hi", format="%.6g")
    if high <= low:
        st.caption(f"⚠️ {label} max must exceed min — using auto.")
        return None
    return (float(low), float(high))


def _size_controls(key: str, default_height: int) -> Tuple[Optional[int], int]:
    """Figure size, with 'fill the page' as the default."""
    custom = st.checkbox("set figure size", value=False, key=f"{key}_custom_size")
    if not custom:
        return None, default_height
    left, right = st.columns(2)
    width = left.number_input("width (px)", 300, 3000, 900, 50,
                              key=f"{key}_width")
    height = right.number_input("height (px)", 200, 2000, default_height, 20,
                                key=f"{key}_height")
    return int(width), int(height)


def engine_choice(key: str, default: str = STATIC) -> str:
    return st.radio("Rendering", [STATIC, INTERACTIVE],
                    index=[STATIC, INTERACTIVE].index(default),
                    horizontal=True, key=f"{key}_engine",
                    help="Interactive figures are Plotly: rotate, zoom and "
                         "hover. Static figures are matplotlib, and are the "
                         "ones to export.")


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------

def curve_controls(key: str, *, spec=None,
                   data_range: Optional[Dict[str, Tuple[float, float]]] = None,
                   default_labels: Tuple[str, str] = ("", ""),
                   ) -> CurveStyle:
    """Full control panel for a 1D plot."""
    engine = engine_choice(key)
    data_range = data_range or {}
    x_default, y_default = default_labels

    with st.expander("Plot controls", expanded=False):
        scales, style, labels = st.tabs(["Axes", "Style", "Labels & size"])

        with scales:
            left, right = st.columns(2)
            with left:
                logx = st.toggle("log x",
                                 value=bool(spec.log_x) if spec else False,
                                 key=f"{key}_logx")
                xlim = _limit_pair(f"{key}_x", "x", data_range.get("x"))
            with right:
                logy = st.toggle("log y",
                                 value=bool(spec.log_y) if spec else False,
                                 key=f"{key}_logy")
                ylim = _limit_pair(f"{key}_y", "y", data_range.get("y"))
            show_grid = st.checkbox("grid", value=True, key=f"{key}_grid")

        with style:
            first, second, third = st.columns(3)
            color_name = first.selectbox("Colour", list(NAMED_COLORS),
                                         key=f"{key}_color",
                                         help="'palette' gives each curve its "
                                              "own colour in a fixed order.")
            marker = second.selectbox("Marker", MARKER_NAMES, key=f"{key}_marker")
            dash = third.selectbox("Line style", DASH_NAMES, key=f"{key}_dash")

            first, second, third = st.columns(3)
            line_width = first.slider("Line width", 0.5, 6.0, 2.0, 0.25,
                                      key=f"{key}_lw")
            marker_size = second.slider("Marker size", 1.0, 20.0, 7.0, 0.5,
                                        key=f"{key}_ms")
            opacity = third.slider("Opacity", 0.1, 1.0, 1.0, 0.05,
                                   key=f"{key}_alpha")

        with labels:
            title = st.text_input("Title", value="", key=f"{key}_title")
            left, right = st.columns(2)
            xlabel = left.text_input("x label", value=x_default,
                                     key=f"{key}_xlabel")
            ylabel = right.text_input("y label", value=y_default,
                                      key=f"{key}_ylabel")
            left, right = st.columns(2)
            with left:
                show_legend = st.checkbox("legend", value=True,
                                          key=f"{key}_legend")
            legend_position = right.selectbox(
                "Legend position", LEGEND_POSITIONS, key=f"{key}_legendpos",
                disabled=not show_legend)
            width, height = _size_controls(key, 520)

    return CurveStyle(
        engine=engine, color_name=color_name, marker=marker,
        marker_size=marker_size, dash=dash, line_width=line_width,
        opacity=opacity, logx=logx, logy=logy, xlim=xlim, ylim=ylim,
        show_grid=show_grid, show_legend=show_legend,
        legend_position=legend_position, title=title, xlabel=xlabel,
        ylabel=ylabel, width=width, height=height,
    )


SPACING_NAMES = {"linear": "evenly spaced", "log": "log spaced (dense early)",
                 "step": "every n-th", "all": "all", "listed": "listed"}


def series_controls(key: str, n_curves: int, *, spacing: str = "linear",
                    count: int = 40, cmap: str = "coolwarm",
                    color_range: str = "shown", legend: bool = False,
                    legend_format: str = "{:.3g}", legend_fontsize: float = 8.0,
                    xlim: Optional[Tuple[float, float]] = None,
                    ylim: Optional[Tuple[float, float]] = None,
                    title: str = "",
                    figsize: Tuple[float, float] = (7.0, 4.4),
                    expanded: bool = False) -> SeriesStyle:
    """Plot options for a stack of curves (``plot_series``), in an expander.

    The keywords are the starting values. ``spacing`` picks the rows
    (:func:`~NanoOrganizer.viz.plots.series_indices`), or ``"listed"`` for
    rows typed in (``0, 1, 50, -1``).
    """
    n = max(int(n_curves), 0)
    with st.expander("Plot options", expanded=expanded):
        a, b, c = st.columns([2, 1, 2])
        names = list(SPACING_NAMES)
        how = a.selectbox("curves", names, index=names.index(spacing),
                          format_func=SPACING_NAMES.get, key=f"{key}_spacing")
        many = b.number_input("every" if how == "step" else "how many",
                              min_value=1, value=int(count), step=1,
                              key=f"{key}_count",
                              disabled=how in ("all", "listed"))
        listed = c.text_input("rows (listed)", value=f"0, {max(n // 2, 0)}, -1",
                              key=f"{key}_rows", disabled=how != "listed",
                              help="Row numbers; negative counts from the end.")
        if how == "listed":
            try:
                rows = [int(r) for r in listed.replace(",", " ").split()]
                if not rows or any(not -n <= r < n for r in rows):
                    raise ValueError
            except ValueError:
                st.caption(f"⚠️ rows must be whole numbers within ±{n} — "
                           f"showing every row.")
                rows = list(range(n))
        else:
            rows = [int(r) for r in plots.series_indices(n, how, int(many))]
        st.caption(f"{len(rows)} of {n} curves")

        a, b, c, d = st.columns(4)
        maps = list(COLORMAPS) if cmap in COLORMAPS else [cmap, *COLORMAPS]
        cmap = a.selectbox("colour map", maps, index=maps.index(cmap),
                           key=f"{key}_cmap")
        spans = ["shown", "all"]
        color_range = b.selectbox(
            "colours span", spans, index=spans.index(color_range),
            key=f"{key}_span",
            help="shown: the curves drawn use the whole map; all: a curve "
                 "keeps its colour whichever rows are drawn.")
        legend = c.toggle("legend", value=legend, key=f"{key}_legend")
        legend_fontsize = d.number_input("legend size", 1.0, 20.0,
                                         float(legend_fontsize), 1.0,
                                         key=f"{key}_legend_size",
                                         disabled=not legend)
        legend_format = st.text_input("legend format", value=legend_format,
                                      key=f"{key}_legend_format",
                                      disabled=not legend,
                                      help="Python format of each curve's "
                                           "value: {:.1f} min")
        try:
            legend_format.format(1.0)
        except (ValueError, IndexError, KeyError):
            st.caption("⚠️ not a format for one number — {:.3g} used.")
            legend_format = "{:.3g}"

        left, right = st.columns(2)
        with left:
            xlim = axis_limits(f"{key}_x", "x", xlim)
            logx = st.toggle("log x", value=False, key=f"{key}_logx")
        with right:
            ylim = axis_limits(f"{key}_y", "y", ylim)
            logy = st.toggle("log y", value=False, key=f"{key}_logy")
        title = st.text_input("title", value=title, key=f"{key}_title")
        figsize = figure_size(key, figsize)

    return SeriesStyle(rows=tuple(rows), cmap=cmap, color_range=color_range,
                       legend=legend, legend_format=legend_format,
                       legend_fontsize=float(legend_fontsize), xlim=xlim,
                       ylim=ylim, logx=logx, logy=logy, title=title,
                       figsize=figsize)


def image_controls(key: str, *,
                   data_range: Optional[Tuple[float, float]] = None,
                   allow_surface: bool = True) -> ImageStyle:
    """Full control panel for a 2D image or map."""
    engine = engine_choice(key)

    with st.expander("Plot controls", expanded=False):
        scaling, appearance = st.tabs(["Scaling", "Appearance"])

        with scaling:
            left, right = st.columns(2)
            cmap = left.selectbox("Colormap", list(COLORMAPS), key=f"{key}_cmap")
            log_intensity = right.toggle(
                "log intensity", key=f"{key}_log",
                help="For scattering, where the useful range spans decades.")

            percentile = st.slider(
                "Contrast percentile", 90.0, 100.0, 99.5, 0.1,
                key=f"{key}_pct",
                help="Clip the display range to this percentile. A few hot "
                     "pixels otherwise flatten everything else.")
            manual = _limit_pair(f"{key}_v", "value", data_range)

        with appearance:
            left, right = st.columns(2)
            with left:
                equal_aspect = st.checkbox("equal aspect", value=True,
                                           key=f"{key}_aspect")
                show_colorbar = st.checkbox("colour bar", value=True,
                                            key=f"{key}_cbar")
            with right:
                reverse_y = st.checkbox(
                    "origin at top", value=True, key=f"{key}_originy",
                    help="Image convention. Turn off for a map whose y axis "
                         "is a physical quantity.")
                as_surface = st.checkbox(
                    "draw as a 3D surface", value=False,
                    key=f"{key}_surface", disabled=not allow_surface,
                    help="Relief rather than colour — easier for judging a "
                         "peak, harder for reading a position.") \
                    if allow_surface else False
            title = st.text_input("Title", value="", key=f"{key}_title")
            width, height = _size_controls(key, 620)

    return ImageStyle(
        engine=engine, cmap=cmap, log_intensity=log_intensity,
        percentile=percentile,
        vmin=manual[0] if manual else None,
        vmax=manual[1] if manual else None,
        equal_aspect=equal_aspect, reverse_y=reverse_y,
        show_colorbar=show_colorbar, as_surface=bool(as_surface),
        title=title, width=width, height=height,
    )


def volume_controls(key: str, shape: Sequence[int], *,
                    value_range: Optional[Tuple[float, float]] = None,
                    ) -> VolumeStyle:
    """Full control panel for a 3D volume.

    Defaults to the interactive engine: a projection answers "what is in
    there", but only rotation answers "what shape is it".
    """
    engine = engine_choice(key, default=INTERACTIVE)
    interactive = engine == INTERACTIVE

    with st.expander("Plot controls", expanded=True):
        if interactive:
            left, middle, right = st.columns(3)
            mode = left.selectbox(
                "Render as", ["isosurface", "volume", "points", "slices"],
                key=f"{key}_mode",
                help="isosurface: a surface at one value — start here. "
                     "volume: translucent, shows the interior. "
                     "points: one marker per voxel, the most responsive. "
                     "slices: three planes you can read values off.")
            cmap = middle.selectbox("Colormap", list(COLORMAPS),
                                    key=f"{key}_cmap")
            opacity = right.slider("Opacity", 0.05, 1.0, 0.6, 0.05,
                                   key=f"{key}_opacity")

            low, high = value_range or (0.0, 1.0)
            level = None
            if mode in ("isosurface", "points", "volume"):
                level = st.slider(
                    "Threshold", float(low), float(high),
                    float(low + 0.5 * (high - low)),
                    key=f"{key}_level",
                    help="Voxels below this are not drawn. The single "
                         "control that decides what the structure looks "
                         "like — move it before believing any of it.")

            fractions = (0.5, 0.5, 0.5)
            if mode == "slices":
                z_col, y_col, x_col = st.columns(3)
                fractions = (
                    z_col.slider("z plane", 0.0, 1.0, 0.5, 0.02,
                                 key=f"{key}_fz"),
                    y_col.slider("y plane", 0.0, 1.0, 0.5, 0.02,
                                 key=f"{key}_fy"),
                    x_col.slider("x plane", 0.0, 1.0, 0.5, 0.02,
                                 key=f"{key}_fx"),
                )

            left, right = st.columns(2)
            budget = left.select_slider(
                "Detail", options=[32, 40, 48, 56, 64, 80],
                value=48, key=f"{key}_budget",
                help="Largest edge rendered, in voxels. A browser does not "
                     "slow down gracefully on a big volume — it locks up.")
            surface_count = right.slider("Shells (volume mode)", 4, 25, 12,
                                         key=f"{key}_shells",
                                         disabled=mode != "volume")
            height = st.slider("Figure height (px)", 400, 1100, 650, 50,
                               key=f"{key}_height")
            return VolumeStyle(engine=engine, mode=mode, cmap=cmap,
                               opacity=opacity, level=level,
                               surface_count=surface_count, budget=budget,
                               slice_fractions=fractions, height=height)

        left, middle, right = st.columns(3)
        axis = left.selectbox(
            "Slice along", [0, 1, 2], key=f"{key}_axis",
            format_func=lambda a: f"axis {a} ({shape[a]} planes)")
        cmap = middle.selectbox("Colormap", list(COLORMAPS), key=f"{key}_cmap2")
        projection = right.selectbox(
            "Show", ["single slice", "mean projection", "max projection"],
            key=f"{key}_projection")

        n_planes = int(shape[axis])
        thickness, centre = n_planes, n_planes // 2
        if projection == "single slice":
            centre = st.slider("Plane", 0, n_planes - 1, n_planes // 2,
                               key=f"{key}_plane")
            thickness = 1
        else:
            # Projecting the full depth of a dense sample saturates:
            # everything is in front of something.
            left, right = st.columns(2)
            thickness = left.slider("Slab thickness (planes)", 1, n_planes,
                                    min(16, n_planes), key=f"{key}_thickness")
            centre = right.slider("Slab centre", 0, n_planes - 1,
                                  n_planes // 2, key=f"{key}_centre")

        return VolumeStyle(engine=engine, cmap=cmap, axis=int(axis),
                           projection=projection, slab_thickness=int(thickness),
                           slab_centre=int(centre))


__all__ = [
    "CurveStyle", "ImageStyle", "VolumeStyle", "SeriesStyle", "COLORMAPS",
    "NAMED_COLORS", "SPACING_NAMES",
    "MARKER_NAMES", "DASH_NAMES", "LEGEND_POSITIONS", "MPL_MARKERS",
    "MPL_DASHES", "INTERACTIVE", "STATIC", "engine_choice", "curve_controls",
    "image_controls", "volume_controls", "series_controls", "axis_limits",
    "figure_size",
]
