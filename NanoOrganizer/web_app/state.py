#!/usr/bin/env python3
"""
Shared session state for the web app.

Every page works on one :class:`~NanoOrganizer.workbench.Workbench` held in
``st.session_state``, so the basket a user builds on **Explore** is the same
basket **Analyze** and **Compare** act on. That is the whole point of the
restructure: the pages are views onto one selection, not six separate tools.

The Workbench is the same object the notebooks use, so a page and a notebook
cannot drift apart in behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from NanoOrganizer.workbench import (
    Organizer, Workbench, new_organizer, open_project,
)

WORKBENCH = "nano_workbench"
LAST_ROOT = "nano_last_root"


def get_workbench() -> Optional[Workbench]:
    """The open workbench, or None if no project has been opened yet."""
    return st.session_state.get(WORKBENCH)


def set_workbench(workbench: Workbench) -> Workbench:
    st.session_state[WORKBENCH] = workbench
    st.session_state[LAST_ROOT] = str(workbench.project.root)
    return workbench


def close_workbench() -> None:
    st.session_state.pop(WORKBENCH, None)


def require_workbench() -> Workbench:
    """Return the workbench, or stop the page with a pointer to Project.

    Pages call this first. Stopping with an explanation beats rendering a page
    full of empty widgets that error the moment anything is touched.
    """
    workbench = get_workbench()
    if workbench is None:
        st.info(
            "No project is open. Go to **Project** to choose a folder and "
            "load its metadata.",
            icon="📁",
        )
        st.stop()
    return workbench


def open_in_session(root, **kwargs) -> Workbench:
    """Open a project and put it in the session."""
    return set_workbench(open_project(root, **kwargs))


def new_in_session(root, name: str = "") -> Workbench:
    """Start an empty organiser and put it in the session.

    The counterpart to :func:`open_in_session`, for the case where there is no
    project yet — only data, somewhere, waiting to be linked.  A path ending
    in ``.json`` becomes a single-document :class:`Organizer`; a folder gets
    the usual hidden store.  Either way an existing store is refused, because
    silently opening one when the user asked to create one would be the wrong
    kind of helpful.
    """
    target = Path(root).expanduser()

    if target.suffix.lower() == ".json":
        if target.exists():
            raise FileExistsError(
                f"{target.name} already exists. Open it instead, or choose "
                f"another name."
            )
        return set_workbench(Organizer(target, name=name))

    if (target / ".nanoorganizer" / "samples.json").exists():
        raise FileExistsError(
            f"{target} already holds an organizer. Open it instead, or choose "
            f"another folder."
        )
    return set_workbench(new_organizer(target, name=name))


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def sidebar_status() -> None:
    """Show the open project and current selection in the sidebar.

    Drawn on every page so the basket is never invisible — a filter applied on
    one page silently narrowing another page's results is exactly the kind of
    surprise shared state causes.
    """
    workbench = get_workbench()
    with st.sidebar:
        st.divider()
        if workbench is None:
            st.caption("No project open")
            return

        project = workbench.project
        st.caption(f"**{project.config.name}**")
        st.caption(f"{len(project)} samples · {len(project.modalities())} modalities")

        if workbench.basket:
            st.caption(f"🧺 **{len(workbench.basket)} selected**")
            with st.expander("selection", expanded=False):
                st.caption(", ".join(workbench.basket))
            if st.button("Clear selection", width="stretch",
                         key="nano_sidebar_clear"):
                workbench.clear()
                st.rerun()
        else:
            st.caption("🧺 all samples")


def basket_label(workbench: Workbench) -> str:
    """Human description of what the next action will act on."""
    if workbench.basket:
        return f"{len(workbench.basket)} selected samples"
    return f"all {len(workbench.project)} samples"


# ---------------------------------------------------------------------------
# Small shared widgets
# ---------------------------------------------------------------------------

def sample_picker(workbench: Workbench, key: str, label: str = "Sample",
                  modality: str = "", stage: str = "") -> Optional[str]:
    """Choose one sample from the basket, restricted to those with data.

    Offering a sample that has no matching measurement only produces an error
    one click later, so those are filtered out here instead.
    """
    candidates = [
        sample_id for sample_id in workbench.active
        if workbench.project.get_sample(sample_id)
        and workbench.project.get_sample(sample_id).get_measurements(
            modality=modality, stage=stage)
    ]
    if not candidates:
        st.warning(
            f"No sample in the selection has a "
            f"{modality or 'matching'} measurement"
            + (f" from the {stage} stage" if stage else "") + ".",
            icon="⚠️",
        )
        return None
    return st.selectbox(label, candidates, key=key)


def show_result_values(result, columns: int = 4) -> None:
    """Lay an AnalysisResult's scalars out as metrics."""
    items = [(name, value) for name, value in result.values.items()]
    if not items:
        return
    for start in range(0, len(items), columns):
        row = st.columns(columns)
        for slot, (name, value) in zip(row, items[start:start + columns]):
            error = result.errors.get(name)
            unit = result.units.get(name, "")
            if isinstance(value, float):
                shown = f"{value:.4g}"
            else:
                shown = str(value)
            slot.metric(
                f"{name} ({unit})" if unit else name,
                shown,
                delta=f"± {error:.2g}" if error is not None else None,
                delta_color="off",
            )


def show_message(result) -> None:
    """Surface a result's warning or failure reason, never silently."""
    if not result.ok:
        st.error(result.message or "analysis failed", icon="🚫")
    elif result.message:
        st.warning(result.message, icon="⚠️")


__all__ = [
    "WORKBENCH", "get_workbench", "set_workbench", "close_workbench",
    "require_workbench", "open_in_session", "sidebar_status", "basket_label",
    "sample_picker", "show_result_values", "show_message",
]
