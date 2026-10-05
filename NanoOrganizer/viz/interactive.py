#!/usr/bin/env python3
"""
Interactive Plotly figures — the ones you need to *handle* rather than read.

:mod:`NanoOrganizer.viz.plots` draws matplotlib figures, which is what you want
for a figure that will end up in a paper. This module is for the other case:
a volume you need to rotate before you can see the pore network, a spectrum
whose shoulder you want to zoom into, an image whose pixel value under the
cursor is the question.

Everything here returns a ``plotly.graph_objects.Figure``, so it renders in a
notebook (``fig.show()``), in Streamlit (``st.plotly_chart``), or to a
self-contained HTML file (``fig.write_html``) without the caller caring which.

Plotly is an extra::

    pip install "nanoorganizer[web]"

It is imported lazily and only when one of these functions is called, so the
package still works without it — you lose the interactive figures, not the
analysis.

The 3D entry point is :func:`volume_figure`. Four ways to look at a volume:

``isosurface``
    A surface at one value. The right default: it shows shape, and it is the
    only mode in which a pore is visibly a hole rather than a dim patch.
``volume``
    Translucent direct rendering. Shows the interior, at the cost of every
    surface being partly see-through — which is also why nothing in it has a
    reliable depth.
``points``
    One marker per voxel above a threshold, subsampled. The cheapest mode and
    the most responsive on a large array.
``slices``
    Three orthogonal planes you can slide through the volume. Not a rendering
    at all — a way of reading values off the array, which the other three
    cannot do.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from NanoOrganizer.viz.plots import CATEGORICAL, GRID, INK, INK_SOFT

#: Plotly colorscale names this module is known to accept. ``Bone`` is not
#: among them — Plotly has no such scale and asking for one raises, so the
#: nearest equivalent is ``ice``.
COLORSCALES = ("Viridis", "Plasma", "Inferno", "Magma", "Cividis", "Turbo",
               "Jet", "Hot", "Greys", "Greys_r", "ice", "RdBu", "RdBu_r",
               "Electric", "Rainbow")

#: Marker symbols, by the name a user would look for.
MARKERS = {"none": None, "circle": "circle", "square": "square",
           "diamond": "diamond", "triangle up": "triangle-up",
           "triangle down": "triangle-down", "cross": "cross", "x": "x",
           "star": "star", "pentagon": "pentagon", "hexagon": "hexagon"}

#: Line styles, by name.
DASHES = {"solid": "solid", "dashed": "dash", "dash-dot": "dashdot",
          "dotted": "dot", "none": None}

#: Volume render modes, in the order they are offered.
VOLUME_MODES = ("isosurface", "volume", "points", "slices")

#: Beyond this many voxels a volume is strided down before rendering. Browsers
#: do not fail gracefully on a 128³ translucent volume; they lock the tab.
MAX_VOXELS = 60 ** 3


def _plotly():
    """Import Plotly, or explain how to get it."""
    try:
        import plotly.graph_objects as go
    except ImportError as exc:                 # pragma: no cover - extra
        raise ImportError(
            "Interactive figures need Plotly. Install it with "
            "`pip install \"nanoorganizer[web]\"` or `pip install plotly`. "
            "The matplotlib figures in NanoOrganizer.viz.plots need nothing "
            "extra."
        ) from exc
    return go


def _layout(fig, *, title: str = "", xlabel: str = "", ylabel: str = "",
            width: Optional[int] = None, height: int = 520,
            show_legend: bool = True, show_grid: bool = True,
            legend_position: str = "top right"):
    """Apply the house style: recessive axes, ink-coloured text, no chartjunk."""
    anchors = {
        "top right": dict(x=0.99, y=0.99, xanchor="right", yanchor="top"),
        "top left": dict(x=0.01, y=0.99, xanchor="left", yanchor="top"),
        "bottom right": dict(x=0.99, y=0.01, xanchor="right", yanchor="bottom"),
        "bottom left": dict(x=0.01, y=0.01, xanchor="left", yanchor="bottom"),
        "outside": dict(x=1.02, y=1.0, xanchor="left", yanchor="top"),
    }
    def axis(label: str) -> dict:
        return dict(showgrid=show_grid, gridcolor=GRID, zeroline=False,
                    linecolor=GRID, ticks="outside", tickcolor=GRID,
                    tickfont=dict(color=INK_SOFT, size=11),
                    title=dict(text=label,
                               font=dict(color=INK_SOFT, size=12)))

    fig.update_layout(
        title=dict(text=title, font=dict(color=INK, size=14), x=0.0, xanchor="left"),
        xaxis=axis(xlabel),
        yaxis=axis(ylabel),
        showlegend=show_legend,
        legend=dict(bgcolor="rgba(255,255,255,0.75)", borderwidth=0,
                    font=dict(color=INK_SOFT, size=11),
                    **anchors.get(legend_position, anchors["top right"])),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=70, r=30, t=50 if title else 20, b=55),
        height=height, hovermode="closest",
    )
    if width:
        fig.update_layout(width=width, autosize=False)
    return fig


def _apply_scales(fig, *, logx: bool, logy: bool,
                  xlim: Optional[Tuple[float, float]] = None,
                  ylim: Optional[Tuple[float, float]] = None):
    """Log scales and limits.

    Plotly ranges are in *log units* on a log axis — passing data units there
    is a classic way to get an empty plot, so the conversion happens here once.
    """
    if logx:
        fig.update_xaxes(type="log")
    if logy:
        fig.update_yaxes(type="log")

    if xlim and None not in xlim:
        low, high = float(xlim[0]), float(xlim[1])
        if logx:
            if low <= 0 or high <= 0:
                return fig
            low, high = np.log10(low), np.log10(high)
        fig.update_xaxes(range=[low, high])
    if ylim and None not in ylim:
        low, high = float(ylim[0]), float(ylim[1])
        if logy:
            if low <= 0 or high <= 0:
                return fig
            low, high = np.log10(low), np.log10(high)
        fig.update_yaxes(range=[low, high])
    return fig


# ---------------------------------------------------------------------------
# Curves
# ---------------------------------------------------------------------------

def curves_figure(curves: Sequence[Tuple[str, np.ndarray, np.ndarray]], *,
                  colors: Optional[Sequence[str]] = None,
                  marker: str = "none",
                  marker_size: float = 7.0,
                  dash: str = "solid",
                  line_width: float = 2.0,
                  opacity: float = 1.0,
                  logx: bool = False, logy: bool = False,
                  xlim: Optional[Tuple[float, float]] = None,
                  ylim: Optional[Tuple[float, float]] = None,
                  xlabel: str = "", ylabel: str = "", title: str = "",
                  show_legend: bool = True, show_grid: bool = True,
                  legend_position: str = "top right",
                  width: Optional[int] = None, height: int = 520,
                  colorbar_values: Optional[Sequence[float]] = None,
                  colorbar_label: str = "",
                  colorscale: str = "Viridis"):
    """Draw ``[(label, x, y), …]`` as an interactive line plot.

    Pass *colorbar_values* — one number per curve, a time or a temperature —
    to colour the curves continuously along *colorscale* and show a colour bar
    instead of a legend. That is the right encoding for a series where the
    curves are ordered; a categorical palette is right when they are not.
    """
    go = _plotly()
    fig = go.Figure()

    sampled = _ramp(colorbar_values, colorscale) if colorbar_values is not None else None
    palette = list(colors) if colors else list(CATEGORICAL)

    for index, (label, x, y) in enumerate(curves):
        if sampled is not None:
            colour = sampled[index]
            show_this = False
        else:
            colour = palette[index % len(palette)]
            show_this = True

        mode = "lines"
        if MARKERS.get(marker):
            mode = "lines+markers" if DASHES.get(dash) else "markers"
        elif not DASHES.get(dash):
            mode = "markers"

        fig.add_trace(go.Scatter(
            x=np.asarray(x), y=np.asarray(y), name=str(label), mode=mode,
            line=dict(color=colour, width=line_width,
                      dash=DASHES.get(dash) or "solid"),
            marker=dict(color=colour, size=marker_size,
                        symbol=MARKERS.get(marker) or "circle"),
            opacity=opacity, showlegend=show_this,
            hovertemplate=f"<b>{label}</b><br>%{{x:.5g}}, %{{y:.5g}}<extra></extra>",
        ))

    if sampled is not None and len(curves):
        values = np.asarray(colorbar_values, dtype=float)
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers", showlegend=False,
            hoverinfo="skip",
            marker=dict(colorscale=colorscale, showscale=True,
                        cmin=float(values.min()), cmax=float(values.max()),
                        color=[float(values.min())],
                        colorbar=dict(title=dict(text=colorbar_label,
                                                 font=dict(color=INK_SOFT,
                                                           size=11)),
                                      outlinewidth=0, thickness=14)),
        ))
        show_legend = False

    _layout(fig, title=title, xlabel=xlabel, ylabel=ylabel, width=width,
            height=height, show_legend=show_legend, show_grid=show_grid,
            legend_position=legend_position)
    return _apply_scales(fig, logx=logx, logy=logy, xlim=xlim, ylim=ylim)


def _ramp(values, colorscale: str) -> List[str]:
    """One colour per value, sampled along *colorscale*."""
    from plotly.colors import sample_colorscale

    values = np.asarray(values, dtype=float)
    span = float(values.max() - values.min())
    fractions = ((values - values.min()) / span) if span > 0 else np.zeros_like(values)
    return list(sample_colorscale(colorscale, list(np.clip(fractions, 0, 1))))


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def image_figure(array: np.ndarray, *,
                 colorscale: str = "Viridis",
                 vmin: Optional[float] = None, vmax: Optional[float] = None,
                 title: str = "", xlabel: str = "", ylabel: str = "",
                 equal_aspect: bool = True, reverse_y: bool = True,
                 show_colorbar: bool = True,
                 width: Optional[int] = None, height: int = 620,
                 extent: Optional[Tuple[float, float, float, float]] = None,
                 hover_unit: str = ""):
    """Draw a 2D array as an interactive heatmap.

    *extent* is ``(x0, x1, y0, y1)`` in data units, so a calibrated micrograph
    can be read in nanometres rather than pixels.
    """
    go = _plotly()
    array = np.asarray(array, dtype=float)

    axes: Dict[str, Any] = {}
    if extent is not None:
        x0, x1, y0, y1 = extent
        axes["x"] = np.linspace(x0, x1, array.shape[1])
        axes["y"] = np.linspace(y0, y1, array.shape[0])

    fig = go.Figure(go.Heatmap(
        z=array, colorscale=colorscale, zmin=vmin, zmax=vmax,
        showscale=show_colorbar,
        colorbar=dict(outlinewidth=0, thickness=14,
                      tickfont=dict(color=INK_SOFT, size=10)),
        hovertemplate=("x %{x:.4g}<br>y %{y:.4g}<br>"
                       f"value %{{z:.5g}} {hover_unit}<extra></extra>"),
        **axes,
    ))
    _layout(fig, title=title, xlabel=xlabel, ylabel=ylabel, width=width,
            height=height, show_legend=False, show_grid=False)

    if reverse_y:
        fig.update_yaxes(autorange="reversed")
    if equal_aspect:
        # Without this a square detector image is drawn as a rectangle,
        # and every angle read off it is wrong.
        fig.update_yaxes(scaleanchor="x", scaleratio=1.0)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------

def downsample(volume: np.ndarray, max_voxels: int = MAX_VOXELS
               ) -> Tuple[np.ndarray, int]:
    """Stride *volume* down until it has at most *max_voxels*.

    Returns ``(volume, step)``. Rendering a full tomogram in a browser does
    not degrade — it hangs the tab — so this is applied by default and the
    step is reported rather than hidden.
    """
    volume = np.asarray(volume)
    step = 1
    while volume[::step, ::step, ::step].size > max_voxels:
        step += 1
    return volume[::step, ::step, ::step], step


def volume_figure(volume: np.ndarray, *,
                  mode: str = "isosurface",
                  colorscale: str = "Viridis",
                  level: Optional[float] = None,
                  opacity: float = 0.6,
                  surface_count: int = 12,
                  max_points: int = 25000,
                  slice_fractions: Tuple[float, float, float] = (0.5, 0.5, 0.5),
                  max_voxels: int = MAX_VOXELS,
                  voxel_size: float = 1.0,
                  unit: str = "voxels",
                  title: str = "",
                  width: Optional[int] = None, height: int = 650,
                  show_colorbar: bool = True):
    """Render a 3D array interactively — rotate, zoom, slice.

    Parameters
    ----------
    mode : str
        One of :data:`VOLUME_MODES`. See the module docstring for which to
        reach for.
    level : float, optional
        Iso value for ``isosurface``, and the threshold for ``points``. Left
        as None it is the midpoint between the volume's 50th and 99.5th
        percentiles — not the mean, which a mostly-empty volume drags down to
        the background.
    voxel_size, unit : float, str
        Axis calibration. The default labels the axes in voxels, which is
        honest when the file carried no calibration.
    slice_fractions : tuple of float
        Where the three planes sit in ``slices`` mode, as fractions of each
        axis. A plane fixed at the centre answers only one question.
    max_voxels, max_points : int
        Rendering budgets. Exceeded, the volume is strided down and the
        figure says by how much.
    """
    go = _plotly()
    volume = np.asarray(volume, dtype=float)
    if volume.ndim != 3:
        raise ValueError(f"expected a 3D array, got {volume.ndim}D")
    if mode not in VOLUME_MODES:
        raise ValueError(f"mode must be one of {VOLUME_MODES}, got {mode!r}")

    small, step = downsample(volume, max_voxels)
    scale = voxel_size * step
    nz, ny, nx = small.shape

    if level is None:
        level = float(0.5 * (np.percentile(small, 50) + np.percentile(small, 99.5)))

    note = f"{'×'.join(str(n) for n in volume.shape)} {unit}"
    if step > 1:
        note += f" · subsampled 1:{step}"

    if mode == "points":
        fig = _points(go, small, level, scale, colorscale, max_points,
                      opacity, show_colorbar)
    elif mode == "slices":
        fig = _ortho_slices(go, small, scale, colorscale, show_colorbar,
                            slice_fractions)
    else:
        zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
        common = dict(
            x=(xx * scale).ravel(), y=(yy * scale).ravel(),
            z=(zz * scale).ravel(), value=small.ravel(),
            colorscale=colorscale, showscale=show_colorbar,
            colorbar=dict(outlinewidth=0, thickness=14,
                          tickfont=dict(color=INK_SOFT, size=10)),
        )
        if mode == "isosurface":
            # One surface means one colour, so a colour bar beside it would
            # imply a variation that is not there.
            common["showscale"] = False
            common.pop("colorbar", None)
            fig = go.Figure(go.Isosurface(
                isomin=level, isomax=float(small.max()), opacity=opacity,
                surface_count=1, caps=dict(x_show=False, y_show=False,
                                           z_show=False),
                **common))
        else:
            # The same threshold means the same thing here: below it, do not
            # draw. Without it a noisy volume renders its own noise floor as
            # a translucent shell around whatever you came to look at.
            fig = go.Figure(go.Volume(
                isomin=level, isomax=float(small.max()),
                opacity=opacity, surface_count=surface_count,
                caps=dict(x_show=False, y_show=False, z_show=False),
                **common))

    axis = dict(backgroundcolor="white", gridcolor=GRID, showbackground=True,
                zerolinecolor=GRID, tickfont=dict(color=INK_SOFT, size=10))
    fig.update_layout(
        title=dict(text=f"{title}  ·  {note}" if title else note,
                   font=dict(color=INK, size=13), x=0.0, xanchor="left"),
        scene=dict(
            xaxis=dict(title=f"x ({unit})", **axis),
            yaxis=dict(title=f"y ({unit})", **axis),
            zaxis=dict(title=f"z ({unit})", **axis),
            aspectmode="data",      # a cube of voxels must look like a cube
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        height=height, paper_bgcolor="white", showlegend=False,
    )
    if width:
        fig.update_layout(width=width, autosize=False)
    return fig


def _points(go, volume, level, scale, colorscale, max_points, opacity,
            show_colorbar):
    """Voxels above *level* as a subsampled point cloud."""
    occupied = np.argwhere(volume >= level)
    if occupied.size == 0:
        return go.Figure()

    values = volume[tuple(occupied.T)]
    if len(occupied) > max_points:
        # Deterministic thinning: a fixed seed keeps the picture stable
        # between reruns, so a slider does not reshuffle the cloud.
        keep = np.random.default_rng(0).choice(len(occupied), max_points,
                                               replace=False)
        occupied, values = occupied[keep], values[keep]

    return go.Figure(go.Scatter3d(
        x=occupied[:, 2] * scale, y=occupied[:, 1] * scale,
        z=occupied[:, 0] * scale, mode="markers",
        marker=dict(size=2.2, color=values, colorscale=colorscale,
                    opacity=opacity, showscale=show_colorbar,
                    colorbar=dict(outlinewidth=0, thickness=14,
                                  tickfont=dict(color=INK_SOFT, size=10))),
        hovertemplate="%{x:.1f}, %{y:.1f}, %{z:.1f}<extra></extra>",
    ))


def _ortho_slices(go, volume, scale, colorscale, show_colorbar,
                  fractions=(0.5, 0.5, 0.5)):
    """Three orthogonal planes, as 3D surfaces, at *fractions* of each axis."""
    nz, ny, nx = volume.shape
    low, high = float(volume.min()), float(volume.max())
    traces = []

    def plane_index(fraction: float, n: int) -> int:
        return int(np.clip(round(float(fraction) * (n - 1)), 0, n - 1))

    z_mid = plane_index(fractions[0], nz)
    y_mid = plane_index(fractions[1], ny)
    x_mid = plane_index(fractions[2], nx)
    yy, xx = np.mgrid[0:ny, 0:nx]
    traces.append(go.Surface(
        x=xx * scale, y=yy * scale, z=np.full((ny, nx), z_mid * scale),
        surfacecolor=volume[z_mid], colorscale=colorscale,
        cmin=low, cmax=high, showscale=show_colorbar,
        colorbar=dict(outlinewidth=0, thickness=14,
                      tickfont=dict(color=INK_SOFT, size=10))))

    zz, xx = np.mgrid[0:nz, 0:nx]
    traces.append(go.Surface(
        x=xx * scale, y=np.full((nz, nx), y_mid * scale), z=zz * scale,
        surfacecolor=volume[:, y_mid, :], colorscale=colorscale,
        cmin=low, cmax=high, showscale=False))

    zz, yy = np.mgrid[0:nz, 0:ny]
    traces.append(go.Surface(
        x=np.full((nz, ny), x_mid * scale), y=yy * scale, z=zz * scale,
        surfacecolor=volume[:, :, x_mid], colorscale=colorscale,
        cmin=low, cmax=high, showscale=False))

    return go.Figure(traces)


def surface_figure(array: np.ndarray, *, colorscale: str = "Viridis",
                   title: str = "", xlabel: str = "x", ylabel: str = "y",
                   zlabel: str = "value", height: int = 620,
                   width: Optional[int] = None):
    """Draw a 2D array as a rotatable 3D surface.

    Useful for a map whose shape matters more than its values — a detector
    image is usually clearer flat, but a peak in a 2D scan is easier to judge
    in relief.
    """
    go = _plotly()
    array = np.asarray(array, dtype=float)

    fig = go.Figure(go.Surface(z=array, colorscale=colorscale,
                               colorbar=dict(outlinewidth=0, thickness=14)))
    axis = dict(backgroundcolor="white", gridcolor=GRID, showbackground=True,
                zerolinecolor=GRID, tickfont=dict(color=INK_SOFT, size=10))
    fig.update_layout(
        title=dict(text=title, font=dict(color=INK, size=13), x=0.0,
                   xanchor="left"),
        scene=dict(xaxis=dict(title=xlabel, **axis),
                   yaxis=dict(title=ylabel, **axis),
                   zaxis=dict(title=zlabel, **axis)),
        margin=dict(l=0, r=0, t=40, b=0), height=height,
        paper_bgcolor="white", showlegend=False,
    )
    if width:
        fig.update_layout(width=width, autosize=False)
    return fig


__all__ = [
    "COLORSCALES", "MARKERS", "DASHES", "VOLUME_MODES", "MAX_VOXELS",
    "curves_figure", "image_figure", "volume_figure", "surface_figure",
    "downsample",
]
