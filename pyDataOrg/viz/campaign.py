#!/usr/bin/env python3
"""
Figures for a campaign and its optimisation. **Drawing only.**

Every function takes ``ax=None``: given an ``Axes`` it draws there and
nowhere else, given nothing it makes a figure; it returns what it drew on.
Nothing here ranks, fits or proposes — it draws a campaign frame (see
:mod:`pyDataOrg.campaign`), a mask or a surrogate surface someone else
computed. Never ``plt.show()`` inside.

Two keywords run through all of them:

*labels*
    ``{column: axis label}`` — :attr:`Campaign.labels` — so axes read
    "ligand : metal (mol/mol)" rather than the column name.
*short*
    turns a sample id into the text printed beside its point
    (default: unchanged). A project with ids like ``Sample000042`` passes
    ``short=lambda s: s[-3:].lstrip("0")``.

=====================  ====================================================
by sample              :func:`plot_by_sample`
input space            :func:`plot_design_map`
trade-offs             :func:`plot_pareto`
progress               :func:`plot_progress`
the model              :func:`plot_surrogate`, :func:`plot_surrogate_line`,
                       :func:`plot_parity`
=====================  ====================================================
"""

from __future__ import annotations

from typing import Callable, Mapping, Optional, Sequence, Tuple

import numpy as np

MARKERS = ("o", "s", "^", "D", "v", "P", "X")


def _axes(ax=None, figsize=(6.4, 4.4)):
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=figsize)
    return ax


def _label(name: str, labels: Optional[Mapping[str, str]]) -> str:
    return (labels or {}).get(name, name)


def _colours(cmap: str, n: int):
    import matplotlib.pyplot as plt

    palette = plt.get_cmap(cmap)
    if palette.N <= 20:                       # a qualitative map: cycle it
        return [palette(i % palette.N) for i in range(n)]
    return [palette(v) for v in np.linspace(0.0, 1.0, max(n, 2))]


def _is_number(column) -> bool:
    """True when every value present reads as a number, whatever the dtype."""
    import pandas as pd

    present = column.notna()
    converted = pd.to_numeric(column, errors="coerce")
    return bool(present.any()) and int(converted.notna().sum()) == int(present.sum())


def plot_by_sample(frame, y, x: str = "sample", ax=None, *, color: str = "",
                   size: str = "", yerr: str = "", cmap: str = "viridis",
                   sizes: Tuple[float, float] = (20.0, 220.0),
                   label_points: bool = True, colorbar: bool = True,
                   title: str = "", ylabel: Optional[str] = None,
                   markersize: float = 45.0,
                   labels: Optional[Mapping[str, str]] = None,
                   short: Callable[[str], str] = str):
    """One number per sample against the sample or any column, with up to
    two more columns shown as colour and marker size.

    *frame* has a ``sample`` column and the columns named.

    * *x* — ``"sample"`` puts the samples along the axis in the frame's
      order; a number column makes a scatter, each point labelled with its
      sample.
    * *y* — a column, or a list of them (one marker shape each, legend).
    * *color* — a number column colours by *cmap* with a colour bar; a text
      column colours by category with a legend.
    * *size* — a number column scales the marker area between *sizes*, with
      three sizes in the legend.
    * *yerr* — a column of error bars.

    Rows missing *x* or a *y* are left out; a missing *color* draws an open
    marker, a missing *size* the smallest.
    """
    import matplotlib.pyplot as plt
    import pandas as pd
    from matplotlib.colors import Normalize
    from matplotlib.lines import Line2D

    ys = [y] if isinstance(y, str) else list(y)
    ax = _axes(ax, (8.0, 4.2))

    def numbers(column):
        return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)

    categorical = x == "sample" or not _is_number(frame[x])
    where = np.arange(len(frame), dtype=float) if categorical else numbers(x)
    samples = frame["sample"].astype(str).to_numpy()
    handles = []

    norm = palette = None
    if color and _is_number(frame[color]):
        shade = numbers(color)
        palette = plt.get_cmap(cmap)
        finite = shade[np.isfinite(shade)]
        low, high = (finite.min(), finite.max()) if finite.size else (0.0, 1.0)
        norm = Normalize(low, high if high > low else low + 1.0)
        colours = [palette(norm(v)) if np.isfinite(v) else "white" for v in shade]
    elif color:
        groups = frame[color].astype(str).to_numpy()
        lookup = dict(zip(dict.fromkeys(groups),
                          _colours("tab10", len(set(groups)))))
        colours = [lookup[g] for g in groups]
        handles += [Line2D([], [], ls="", marker="o", color=c, label=g)
                    for g, c in lookup.items()]
    else:
        colours = None

    if size:
        scale = numbers(size)
        finite = scale[np.isfinite(scale)]
        low, high = (finite.min(), finite.max()) if finite.size else (0.0, 1.0)

        def area(v):
            frac = (v - low) / (high - low) if high > low else 0.5
            return sizes[0] + np.clip(frac, 0, 1) * (sizes[1] - sizes[0])
        areas = np.where(np.isfinite(scale), area(scale), sizes[0])
        for v in np.unique(np.round([low, (low + high) / 2, high], 3)):
            handles.append(Line2D([], [], ls="", marker="o", color="0.6",
                                  markersize=np.sqrt(area(v)),
                                  label=f"{_label(size, labels)} {v:.3g}"))
    else:
        areas = np.full(len(frame), markersize)

    for k, column in enumerate(ys):
        values = numbers(column)
        keep = np.isfinite(values) & np.isfinite(where)
        if yerr and len(ys) == 1:
            ax.errorbar(where[keep], values[keep], yerr=numbers(yerr)[keep],
                        fmt="none", ecolor="0.5", elinewidth=1, capsize=2,
                        zorder=1)
        own = _colours("tab10", len(ys))[k]
        ax.scatter(where[keep], values[keep], s=areas[keep],
                   c=[colours[i] for i in np.flatnonzero(keep)] if colours
                   else [own], marker=MARKERS[k % len(MARKERS)],
                   edgecolors="k", linewidths=0.4, zorder=2)
        if len(ys) > 1:
            handles.insert(k, Line2D([], [], ls="",
                                     marker=MARKERS[k % len(MARKERS)],
                                     color="0.4" if colours else own,
                                     label=_label(column, labels)))
        if label_points and not categorical:
            for xi, yi, s in zip(where[keep], values[keep], samples[keep]):
                ax.annotate(short(s), (xi, yi), textcoords="offset points",
                            xytext=(4, 4), fontsize=7)

    if norm is not None and colorbar:
        mappable = plt.cm.ScalarMappable(norm=norm, cmap=palette)
        plt.colorbar(mappable, ax=ax, label=_label(color, labels), pad=0.02)
    if categorical:
        ax.set_xticks(where)
        ax.set_xticklabels([short(s) for s in frame[x].astype(str)],
                           rotation=90, fontsize=7)
    ax.set_xlabel("sample" if x == "sample" else _label(x, labels))
    ax.set_ylabel(_label(ys[0], labels) if ylabel is None and len(ys) == 1
                  else (ylabel or ""))
    if handles:
        ax.legend(handles=handles, fontsize=8, frameon=False)
    if title:
        ax.set_title(title, loc="left")
    ax.margins(x=0.04)
    return ax


def plot_design_map(frame, x: str, y: str = "", ax=None, *, color: str = "",
                    cmap: str = "viridis", label_points: bool = True,
                    proposals=None, colorbar: bool = True,
                    title: str = "campaign in input space",
                    labels: Optional[Mapping[str, str]] = None,
                    short: Callable[[str], str] = str):
    """The campaign in input space, coloured by a result.

    Filled circles have the result; open circles were made but not (yet)
    measured; stars are *proposals* (a frame with the same columns). With
    no *y*, the inputs are on x and the result itself is on y — the one-
    variable form of the same picture.
    """
    import matplotlib.pyplot as plt

    ax = _axes(ax, (6.8, 4.8))
    one_d = not y
    y_name = color if one_d else y
    xs = frame[x].astype(float).to_numpy()
    ys = frame[y_name].astype(float).to_numpy() if y_name in frame else \
        np.full(xs.size, np.nan)
    cs = frame[color].astype(float).to_numpy() if color in frame else \
        np.full(xs.size, np.nan)
    have = np.isfinite(cs) & np.isfinite(xs) & np.isfinite(ys)
    made = ~have & np.isfinite(xs) & (one_d | np.isfinite(ys))
    if made.any():
        base = np.where(np.isfinite(ys), ys, np.nanmin(ys) if have.any() else 0)
        ax.scatter(xs[made], base[made], s=40, facecolors="none",
                   edgecolors="0.55", label="no result yet")
    if have.any():
        points = ax.scatter(xs[have], ys[have], c=cs[have], cmap=cmap, s=60,
                            edgecolors="k", linewidths=0.4)
        if colorbar and not one_d:
            plt.colorbar(points, ax=ax, label=_label(color, labels), pad=0.02)
    if label_points and "sample" in frame:
        for xi, yi, s in zip(xs[have], ys[have], frame["sample"].to_numpy()[have]):
            ax.annotate(short(str(s)), (xi, yi), textcoords="offset points",
                        xytext=(3, 3), fontsize=7)
    if proposals is not None and len(proposals):
        py = proposals[f"{y_name}_pred"] if one_d and \
            f"{y_name}_pred" in proposals else (
                proposals[y] if not one_d else np.full(len(proposals),
                                                       np.nanmax(ys) if have.any() else 0))
        ax.scatter(proposals[x], py, marker="*", s=220, color="tab:red",
                   edgecolors="k", linewidths=0.5, label="proposed", zorder=5)
    ax.set_xlabel(_label(x, labels))
    ax.set_ylabel(_label(y_name, labels))
    ax.set_title(title, loc="left")
    ax.margins(0.08)
    if made.any() or proposals is not None:
        ax.legend(fontsize=8, loc="lower right", bbox_to_anchor=(1.0, 1.0),
                  ncol=2, frameon=False, borderaxespad=0.2)
    return ax


def plot_pareto(frame, objectives, ax=None, *, front=None, proposals=None,
                references=None, highlight: Sequence[str] = (),
                label_points: bool = True,
                labels: Optional[Mapping[str, str]] = None,
                short: Callable[[str], str] = str,
                title: str = "performance trade-off"):
    """Two objectives against each other, with the Pareto front.

    *objectives* are two :class:`~pyDataOrg.campaign.Objective`; *front* is
    the mask from :func:`~pyDataOrg.campaign.pareto_mask` (computed by the
    caller, not here). *proposals* may carry ``<name>_pred`` and
    ``<name>_sd`` columns, drawn as predictions with error bars.
    *references* (a frame) are drawn as labelled diamonds — a benchmark to
    beat, not part of the front.
    """
    ax = _axes(ax, (6.6, 4.8))
    (ox, oy) = objectives[:2]
    xs = frame[ox.name].astype(float).to_numpy()
    ys = frame[oy.name].astype(float).to_numpy()
    ok = np.isfinite(xs) & np.isfinite(ys)
    ax.scatter(xs[ok], ys[ok], s=40, color="0.6", edgecolors="k",
               linewidths=0.3, label="measured")
    if front is not None:
        front = np.asarray(front, bool) & ok
        order = np.argsort(xs[front])
        ax.plot(xs[front][order], ys[front][order], "-o", color="tab:red",
                ms=7, lw=1.4, label="Pareto front")
    if label_points and "sample" in frame:
        for xi, yi, s in zip(xs[ok], ys[ok], frame["sample"].to_numpy()[ok]):
            weight = "bold" if s in highlight else "normal"
            ax.annotate(short(str(s)), (xi, yi), textcoords="offset points",
                        xytext=(3, 3), fontsize=7, fontweight=weight)
    if proposals is not None and len(proposals) and \
            f"{ox.name}_pred" in proposals:
        ax.errorbar(proposals[f"{ox.name}_pred"], proposals[f"{oy.name}_pred"],
                    xerr=proposals.get(f"{ox.name}_sd"),
                    yerr=proposals.get(f"{oy.name}_sd"),
                    fmt="*", ms=14, color="tab:blue", ecolor="tab:blue",
                    elinewidth=0.8, capsize=2, label="proposed (predicted ± sd)")
    if references is not None and len(references):
        rx = references[ox.name].astype(float).to_numpy()
        ry = references[oy.name].astype(float).to_numpy()
        ax.scatter(rx, ry, marker="D", s=60, color="#eda100", edgecolors="k",
                   label="reference")
        for xi, yi, s in zip(rx, ry, references["sample"].to_numpy()):
            ax.annotate(str(s), (xi, yi), textcoords="offset points",
                        xytext=(-4, 6), fontsize=7, ha="right")
    ax.set_xlabel(ox.label(labels))
    ax.set_ylabel(oy.label(labels))
    ax.set_title(title, loc="left")
    ax.legend(fontsize=8, loc="best")
    return ax


def plot_progress(values, best, ax=None, *, name: str = "",
                  sample_labels: Optional[Sequence[str]] = None,
                  labels: Optional[Mapping[str, str]] = None,
                  short: Callable[[str], str] = str):
    """A result in the order it was measured, with the running best.

    *values* in chronological order (see
    :func:`~pyDataOrg.campaign.chronological`); *best* from
    :func:`~pyDataOrg.campaign.best_so_far`.
    """
    ax = _axes(ax, (7.0, 4.0))
    order = np.arange(1, len(values) + 1)
    ax.plot(order, values, "o", color="tab:blue", ms=5, label="each sample")
    ax.step(order, best, where="post", color="tab:red", lw=1.6,
            label="best so far")
    if sample_labels is not None and len(sample_labels) <= 40:
        ax.set_xticks(order)
        ax.set_xticklabels([short(str(s)) for s in sample_labels],
                           rotation=90, fontsize=7)
    ax.set_xlabel("samples, in the order they were measured")
    ax.set_ylabel(_label(name, labels) if name else "value")
    ax.set_title("campaign progress", loc="left")
    ax.legend(fontsize=8, loc="lower right")
    return ax


def plot_surrogate(gx, gy, z, ax=None, *, points=None, proposals=None,
                   x: str = "", y: str = "", title: str = "",
                   cmap: str = "viridis", colorbar_label: str = "",
                   colorbar: bool = True,
                   labels: Optional[Mapping[str, str]] = None):
    """A surrogate surface (mean or sd) over two input variables.

    *gx*, *gy*, *z* are the grid and values — computed by the caller (see
    :meth:`pyDataOrg.optimize.Proposal.surface`); this only draws them.
    *points* are the measured inputs (``(n, 2)``), *proposals* a frame with
    columns *x* and *y*.
    """
    import matplotlib.pyplot as plt

    ax = _axes(ax, (6.6, 4.8))
    filled = ax.contourf(gx, gy, np.asarray(z).reshape(gx.shape), levels=20,
                         cmap=cmap)
    if colorbar:
        plt.colorbar(filled, ax=ax, label=colorbar_label, pad=0.02)
    if points is not None and len(points):
        p = np.asarray(points, dtype=float)
        ax.scatter(p[:, 0], p[:, 1], s=30, color="white", edgecolors="k",
                   linewidths=0.6, label="measured")
    if proposals is not None and len(proposals):
        ax.scatter(proposals[x], proposals[y], marker="*", s=220,
                   color="tab:red", edgecolors="k", linewidths=0.5,
                   label="proposed")
    ax.set_xlabel(_label(x, labels))
    ax.set_ylabel(_label(y, labels))
    if title:
        ax.set_title(title, loc="left")
    if points is not None or proposals is not None:
        ax.legend(fontsize=8, loc="best")
    return ax


def plot_surrogate_line(gx, mean, sd, ax=None, *, points=None, observed=None,
                        proposals=None, x: str = "", name: str = "",
                        title: str = "",
                        labels: Optional[Mapping[str, str]] = None):
    """A surrogate over one input variable: mean with a ± 2 sd band.

    *points*/*observed* are the measured inputs and values; *proposals* a
    frame with column *x* and ``<name>_pred``.
    """
    ax = _axes(ax, (6.6, 4.4))
    gx, mean, sd = (np.asarray(a, dtype=float) for a in (gx, mean, sd))
    ax.fill_between(gx, mean - 2 * sd, mean + 2 * sd, color="tab:blue",
                    alpha=0.18, lw=0, label="± 2 sd")
    ax.plot(gx, mean, color="tab:blue", lw=1.6, label="mean")
    if points is not None and observed is not None:
        ax.plot(np.asarray(points, float).ravel(), observed, "o", color="k",
                ms=5, label="measured")
    if proposals is not None and len(proposals) and f"{name}_pred" in proposals:
        ax.plot(proposals[x], proposals[f"{name}_pred"], "*", ms=14,
                color="tab:red", mec="k", mew=0.5, label="proposed")
    ax.set_xlabel(_label(x, labels))
    ax.set_ylabel(_label(name, labels))
    if title:
        ax.set_title(title, loc="left")
    ax.legend(fontsize=8, loc="best")
    return ax


def plot_parity(table, name: str, ax=None, *, score: Optional[float] = None,
                label_points: bool = True,
                labels: Optional[Mapping[str, str]] = None,
                short: Callable[[str], str] = str):
    """Leave-one-out prediction against observation for one goal.

    *table* is :attr:`pyDataOrg.optimize.CrossValidation.table`. Points on
    the diagonal were predicted from the other samples; the bars are the
    model's own ± sd.
    """
    ax = _axes(ax, (5.2, 5.0))
    observed = table[name].astype(float).to_numpy()
    predicted = table[f"{name}_pred"].astype(float).to_numpy()
    sd = table[f"{name}_sd"].astype(float).to_numpy()
    ax.errorbar(observed, predicted, yerr=sd, fmt="o", color="tab:blue",
                ecolor="0.6", elinewidth=0.8, capsize=2, ms=5)
    both = np.concatenate([observed, predicted])
    lo, hi = np.nanmin(both), np.nanmax(both)
    pad = 0.08 * (hi - lo or 1.0)
    ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], "k--", lw=1)
    ax.axhline(np.nanmean(observed), color="tab:red", lw=0.8, ls=":",
               label="campaign mean")
    if label_points and "sample" in table:
        for xv, yv, sample in zip(observed, predicted, table["sample"]):
            ax.annotate(short(str(sample)), (xv, yv), textcoords="offset points",
                        xytext=(3, 3), fontsize=7)
    ax.set_xlabel(f"observed {_label(name, labels)}")
    ax.set_ylabel("predicted (leave one out)")
    text = name
    if score is not None and np.isfinite(score):
        text += f" — error {score:.2f} × spread"
    ax.set_title(text, loc="left")
    ax.legend(fontsize=8, loc="upper left")
    return ax


__all__ = ["plot_by_sample", "plot_design_map", "plot_pareto", "plot_progress",
           "plot_surrogate", "plot_surrogate_line", "plot_parity"]
