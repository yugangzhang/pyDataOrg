#!/usr/bin/env python3
"""
Page controls a project's pages share, each a notebook cell's worth.

* :func:`settings` — an analysis' settings dict, starting from the kept ones;
* :func:`keep_buttons` — keep a result for this sample, or for every sample
  (``org.keep_results``);
* :func:`metadata` — ``dict_tree`` of a sample's record;
* :func:`by_sample`, :func:`axes_options` — options of the by-sample plot
  and axis limits.

They return plain values; the pages draw. Nothing here computes a result.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import streamlit as st

from pyDataOrg.analysis import batch_report, get_analysis, same_settings
from pyDataOrg.core.pathmap import display_path
from pyDataOrg.structure import dict_tree
from pyDataOrg.web_app.components.plot_controls import (
    COLORMAPS, axis_limits, figure_size,
)
from pyDataOrg.web_app.components.settings_form import (
    forget_settings, settings_code, settings_form,
)


def show(figure) -> None:
    """Put a matplotlib figure on the page and release it."""
    figure.tight_layout()
    st.pyplot(figure, width="stretch")
    plt.close(figure)


def choices(table, names: Sequence[str]) -> List[str]:
    """The columns of *names* the table has values in."""
    return [n for n in names if n in table and table[n].notna().any()]


# ---------------------------------------------------------------------------
# Settings, and keeping them
# ---------------------------------------------------------------------------

def _differ(analysis: str, a: Dict, b: Dict) -> List[str]:
    spec = get_analysis(analysis)
    a, b = spec.settings_for(a), spec.settings_for(b)
    return [k for k in a if a[k] != b.get(k)]


def settings(workbench, analysis: str, key: str, *, name: str,
             sample: str = "", modality: str = "",
             choices: Optional[Dict] = None, help: Optional[Dict] = None,
             only: Sequence[str] = (), expanded: bool = False,
             width: int = 72) -> Dict:
    """The settings of *analysis* — notebook ``name = dict(...)``.

    They start from the kept ones (the most common) and stay as set while
    the sample changes, as a notebook's dict does; **Back to the kept
    settings** resets them. The dict is shown, to paste into a notebook.
    """
    kept = workbench.kept_settings(analysis, modality=modality)
    with st.expander(f"⚙️ Settings — `{name}`", expanded=expanded):
        chosen = settings_form(analysis, key, kept, only=only,
                               choices=choices, help=help)
        st.code(settings_code(name, chosen, width=width), language="python",
                wrap_lines=True)
        st.button("Back to the kept settings", key=f"{key}_reset",
                  on_click=forget_settings, args=(analysis, key))
    changed = _differ(analysis, chosen, kept) if kept else []
    if changed:
        st.caption(f"`{name}` differs from the settings most kept results "
                   f"were made with: **{', '.join(changed)}**.")
    own = workbench.kept_settings(analysis, sample, modality=modality) \
        if sample else {}
    if own and kept and _differ(analysis, own, kept):
        st.caption(f"{sample}'s kept `{analysis}` was made with other "
                   f"settings than most "
                   f"({', '.join(_differ(analysis, own, kept))}).")
    return chosen


def is_kept(workbench, analysis: str, sample: str, chosen: Optional[Dict],
            modality: str = "") -> bool:
    """Whether *sample* has a kept result of *analysis* made with *chosen*."""
    own = workbench.kept_settings(analysis, sample, modality=modality)
    return bool(own) and same_settings(analysis, own, chosen or {})


def keep_buttons(workbench, analysis: str, sample: str, chosen: Dict, *,
                 key: str, modality: str = "", before: Optional[Dict] = None,
                 folder=None, on_keep: Optional[Callable[[], None]] = None
                 ) -> None:
    """Keep *chosen* for this sample, or for every sample *analysis* runs
    on — a file each in *folder* (default: the organizer's ``results/``),
    linked. For an analysis of another's results, *before* are the upstream
    settings, kept with it. *on_keep* runs after keeping (clear a cache,
    mark the organizer unsaved)."""
    target = f"{analysis}@{modality}" if modality else analysis
    upstream = get_analysis(analysis).results_of
    done = is_kept(workbench, analysis, sample, chosen,
                   "" if upstream else modality) and (
        not upstream or is_kept(workbench, upstream[0], sample, before,
                                modality))
    n = len(workbench.runnable(target))
    where = display_path(folder or workbench.results_dir)
    names = f"`{upstream[0]}` and `{analysis}`" if upstream else f"`{analysis}`"

    one, every, _ = st.columns([1.2, 1.6, 2])
    if one.button(f"Keep for {sample}", key=f"{key}_one", disabled=done,
                  type="primary",
                  help=f"{names} of this sample, with these settings, saved "
                       f"in {where} and linked."):
        with st.spinner(f"Keeping {sample} …"):
            workbench.keep_results(target, sample, settings=chosen,
                                   upstream=before, folder=folder)
        if on_keep is not None:
            on_keep()
        st.session_state[f"{key}_report"] = f"{sample}: kept"
        st.rerun()
    with every.popover(f"Keep for every sample ({n})"):
        st.markdown(
            f"{names} of all **{n}** samples with these settings, in "
            f"`{where}`. Samples kept with the same settings load; the "
            f"others run, and their files are replaced.")
        if st.button("Keep for every sample", key=f"{key}_all",
                     type="primary"):
            bar = st.progress(0.0)

            def progress(index, total, measurement):
                bar.progress(min(index / max(total, 1), 1.0),
                             text=f"{measurement.sample_id} "
                                  f"({index + 1}/{total})")
            tables = workbench.keep_results(target, settings=chosen,
                                            upstream=before, folder=folder,
                                            progress=progress)
            if on_keep is not None:
                on_keep()
            st.session_state[f"{key}_report"] = "\n".join(
                f"{k}: {batch_report(frame)}" for k, frame in tables.items())
            st.rerun()
    report = st.session_state.get(f"{key}_report")
    if report:
        st.code(report + "\n— Save the organizer to keep the links.",
                language=None)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

def metadata(workbench, sample: str, stages: Sequence[str], key: str, *,
             title: str = "Metadata — the record") -> None:
    """``dict_tree`` of a sample's record from one stage."""
    with st.expander(title, expanded=False):
        a, b, c, d = st.columns(4)
        stage = a.selectbox("stage", list(stages), key=f"{key}_stage")
        depth = b.number_input("depth", 1, 8, 1, key=f"{key}_depth")
        limit = c.number_input("entries per level", 1, 500, 25,
                               key=f"{key}_limit")
        width = d.number_input("characters per value", 20, 400, 80, 10,
                               key=f"{key}_width")
        try:
            record = workbench.metadata(sample, stage)
        except KeyError as exc:
            st.caption(str(exc).strip("'\""))
            return
        st.code(dict_tree(record, depth=int(depth), limit=int(limit),
                          width=int(width), name=f"{sample} · {stage}"),
                language=None)


# ---------------------------------------------------------------------------
# Plot options
# ---------------------------------------------------------------------------

def _pick(column, label: str, options: List[str], value: str, key: str):
    return column.selectbox(label, options,
                            index=options.index(value) if value in options
                            else 0, key=key)


def axes_options(key: str, *, xlim=None, ylim=None
                 ) -> Tuple[Optional[Tuple[float, float]],
                            Optional[Tuple[float, float]]]:
    """x and y limits, side by side."""
    left, right = st.columns(2)
    with left:
        xlim = axis_limits(f"{key}_x", "x", xlim)
    with right:
        ylim = axis_limits(f"{key}_y", "y", ylim)
    return xlim, ylim


def apply_axes(ax, xlim, ylim, logy: bool = False) -> None:
    """Display settings onto an Axes — limits and a log scale."""
    if logy:
        ax.set_yscale("log")
    if xlim:
        ax.set_xlim(*xlim)
    if ylim:
        ax.set_ylim(*ylim)


def by_sample(table, key: str, *, ys: List[str], xs: List[str],
              extras: List[str], y: str, x: str = "sample", color: str = "",
              size: str = "", errors: Optional[Dict[str, str]] = None,
              ylabels: Optional[Dict[str, str]] = None,
              figsize: Tuple[float, float] = (9.0, 4.6)):
    """What :func:`pyDataOrg.viz.campaign.plot_by_sample` draws: y (one or
    several), x, colour and marker size; under **Plot options** the error
    bars, colour map, labels, log y and size. Returns ``(keywords, figsize,
    logy, ylim)``, or ``None`` with no y chosen."""
    errors = errors or {}
    a, b, c, d = st.columns(4)
    chosen = a.multiselect("y", ys, default=[y] if y in ys else ys[:1],
                           key=f"{key}_y")
    x = _pick(b, "x", xs, x, f"{key}_x")
    shades = ["none"] + extras
    color = _pick(c, "colour", shades, color or "none", f"{key}_colour")
    size = _pick(d, "marker size", shades, size or "none", f"{key}_size")
    with st.expander("Plot options", expanded=False):
        e, f, g, h = st.columns(4)
        bars = ["auto", "none"] + sorted(set(errors.values()))
        bar = e.selectbox("error bars", bars, key=f"{key}_err",
                          help="auto: the error of the y shown, if it has one")
        maps = list(COLORMAPS)
        cmap = f.selectbox("colour map", maps, index=maps.index("viridis"),
                           key=f"{key}_cmap")
        label_points = g.toggle("label points", value=True, key=f"{key}_labels")
        logy = h.toggle("log y", value=False, key=f"{key}_logy")
        ylabel = st.text_input("y label (blank: the column's)", value="",
                               key=f"{key}_ylabel")
        title = st.text_input("title", value="", key=f"{key}_title")
        ylim = axis_limits(f"{key}_ylim", "y")
        figsize = figure_size(key, figsize)
    if not chosen:
        st.info("Pick a y.", icon="ℹ️")
        return None
    one = chosen[0] if len(chosen) == 1 else ""
    yerr = (errors.get(one, "") if bar == "auto"
            else "" if bar == "none" else bar)
    options = dict(y=one or chosen, x=x,
                   color="" if color == "none" else color,
                   size="" if size == "none" else size, yerr=yerr, cmap=cmap,
                   label_points=label_points, title=title,
                   ylabel=ylabel or (ylabels or {}).get(one) or None)
    return options, figsize, logy, ylim


__all__ = ["show", "choices", "settings", "is_kept", "keep_buttons",
           "metadata", "axes_options", "apply_axes", "by_sample"]
