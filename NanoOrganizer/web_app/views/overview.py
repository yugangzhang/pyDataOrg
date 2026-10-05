#!/usr/bin/env python3
"""Overview — what this app is and where to start."""

from pathlib import Path

import streamlit as st

from NanoOrganizer.core import modality as modality_registry
from NanoOrganizer.web_app.state import get_workbench

st.title("🔬 NanoOrganizer")
st.caption("Organise experimental metadata, visualise any measurement, "
           "analyse in batch, and compare across samples.")

workbench = get_workbench()

if workbench is None:
    st.info("Start on **📁 Project**: choose a folder, map its paths, and "
            "read its metadata.", icon="👈")
else:
    project = workbench.project
    report = project.availability()
    columns = st.columns(4)
    columns[0].metric("Project", project.config.name)
    columns[1].metric("Samples", len(project))
    columns[2].metric("Measurements", report["n_measurements"])
    columns[3].metric("Readable here", report["n_available"])
    if workbench.basket:
        st.caption(f"🧺 {len(workbench.basket)} samples selected — every page "
                   f"acts on these until you clear the selection.")

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("The workflow")
    st.markdown("""
Five pages, used in order. Each one hands its state to the next.

| | |
|---|---|
| **📁 Project** | Open a folder, map recorded paths onto this machine, read the metadata dicts, attach data folders |
| **🔎 Explore** | Filter the sample table down to what matters — this sets the **selection** every later page uses |
| **📈 Visualize** | Draw any measurement, grouped by *what the data is* rather than which instrument made it |
| **🧪 Analyze** | Run an analysis on one sample or the whole selection; results become new, filterable columns |
| **📊 Compare** | Plot a measured quantity against a synthesis parameter |

The loop is the point: **filter → analyse → new columns → filter again.**
""")

    st.subheader("A sample is the unit")
    st.markdown("""
Not a run. One sample is synthesised once, may be reacted several times, and is
characterised repeatedly for weeks by different instruments. Each execution is a
*stage* that keeps its own provenance; every file it owns is a *measurement*.

Paths are stored exactly as the instrument recorded them and mapped per machine,
so **data that is not mounted still browses** — it just reports as unreadable
rather than breaking the page.
""")

with right:
    st.subheader("Techniques")
    st.caption("Visualize dispatches on what the data *is*, so a new technique "
               "is a registry entry — never a new page.")

    for group in modality_registry.GROUPS:
        items = modality_registry.list_modalities(group=group)
        if items:
            with st.expander(
                f"{modality_registry.GROUP_LABELS[group]} ({len(items)})",
                expanded=False,
            ):
                for item in items:
                    st.caption(f"**{item.label}** — {item.domain}")

    st.subheader("Notebooks")
    st.caption("The same engine, driven from Jupyter. `notebook/00…05` plus "
               "`99_master`; they use the identical `Workbench` object, so the "
               "two cannot drift apart.")

    st.subheader("Docs")
    st.caption("`docs/sample_model.md` — the data model.  \n"
               "`docs/analysis.md` — the analyses and the decisions that "
               "affect the numbers.")

st.divider()
st.caption("Brookhaven National Laboratory · CFN · "
           f"NanoOrganizer {__import__('NanoOrganizer').__version__}")
