#!/usr/bin/env python3
"""
Project — open a folder, map its paths, read its metadata.

The first page of the workflow and the only one that writes to disk. Everything
downstream reads the store this page builds.
"""

from pathlib import Path

import streamlit as st

from NanoOrganizer.core.pathmap import suggest_aliases
from NanoOrganizer.core.project import Project
from NanoOrganizer.web_app.components.folder_browser import folder_picker
from NanoOrganizer.web_app.state import (
    close_workbench, get_workbench, open_in_session, set_workbench,
)
from NanoOrganizer.workbench import Workbench

st.title("📁 Project")
st.caption(
    "A project is a folder of samples: authored metadata in `MetaData/`, "
    "data under `<Modality>Data/<SampleID>/`, and a store in `.nanoorganizer/`."
)

workbench = get_workbench()

# ---------------------------------------------------------------------------
# Open
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.subheader("Open a project")

    default_root = str(workbench.project.root) if workbench else ""
    root = folder_picker("nano_project_root", label="Project folder",
                         default=default_root,
                         help="The folder holding MetaData/ and the data folders.")

    left, middle, right = st.columns([1, 1, 2])
    reingest = left.toggle("Read metadata", value=True, key="nano_reingest",
                           help="Read MetaData/*.py. Turn off to reload the "
                                "saved store only.")
    attach = middle.toggle("Attach data folders", value=True, key="nano_attach",
                           help="Link <Modality>Data/<SampleID>/ folders.")

    if right.button("Open project", type="primary", width="stretch",
                    disabled=not root):
        try:
            with st.spinner("Opening…"):
                open_in_session(root, ingest=reingest, attach=attach)
            st.success(f"Opened {Path(root).name}")
            st.rerun()
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

# ---------------------------------------------------------------------------
# Or generate one
# ---------------------------------------------------------------------------

with st.expander("No project yet? Generate an example one", expanded=workbench is None):
    st.caption(
        "Writes a complete synthetic campaign to disk and opens it. Nothing is "
        "downloaded and nothing is hidden: everything in it is generated from "
        "one control variable per sample, and `NanoOrganizer.demo` tells you "
        "what that variable was so you can check what the analyses recover."
    )

    kind = st.radio(
        "Which one", ["Multimodal showcase", "Quick demo"], horizontal=True,
        key="nano_demo_kind",
        captions=[
            "A Cu–Au alloy library for CO₂ reduction, seen by 15 techniques "
            "across 4 stages — curves, images, a tomogram and a correlation "
            "function, with a sparse measurement matrix and one failed run.",
            "Six samples, UV-Vis and TEM only. A few seconds to build.",
        ],
    )

    target = st.text_input(
        "Write it to", value=str(Path.home() / "NanoOrganizerDemo"),
        key="nano_demo_root",
        help="Must be empty, or a demo project this button made earlier.")

    if st.button("Generate and open", width="stretch", disabled=not target):
        from NanoOrganizer import demo

        try:
            with st.spinner("Generating…"):
                if kind == "Quick demo":
                    made = demo.build_demo_project(target)
                else:
                    made = demo.build_showcase_project(target)
                open_in_session(str(made), ingest=True, attach=True)
            st.success(f"Built and opened {Path(made).name}")
            st.rerun()
        except FileExistsError as exc:
            st.error(str(exc), icon="🚫")
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

if workbench is None:
    st.info("Open a project above, or generate an example one.", icon="👆")
    st.stop()

project = workbench.project

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

report = project.availability()
columns = st.columns(4)
columns[0].metric("Samples", report["n_samples"])
columns[1].metric("Measurements", report["n_measurements"])
columns[2].metric("Readable here", report["n_available"])
columns[3].metric("Not mounted", report["n_unresolved"],
                  delta=None if not report["n_unresolved"] else "needs an alias",
                  delta_color="off")

if report["n_unresolved"]:
    st.warning(
        f"{report['n_unresolved']} measurements cannot be read on this machine. "
        f"That is a normal state — the metadata still browses — but analysis "
        f"needs the files. Add a path alias below.",
        icon="⚠️",
    )

# ---------------------------------------------------------------------------
# Path aliases
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.subheader("Path aliases")
    st.caption(
        "Metadata records the paths the instrument saw. They are kept exactly "
        "as written and mapped onto this machine here, so the store stays "
        "portable."
    )

    if project.config.path_aliases:
        st.dataframe(
            [{"recorded prefix": alias.prefix,
              "resolves to": ", ".join(alias.candidates),
              "note": alias.label}
             for alias in project.config.path_aliases],
            width="stretch", hide_index=True,
        )
    else:
        st.caption("None set.")

    left, right = st.columns(2)
    prefix = left.text_input("Recorded prefix", key="nano_alias_prefix",
                             placeholder="/instrument/share/spectra_share")
    local = right.text_input("Local path", key="nano_alias_local",
                             placeholder="/mnt/instrument/spectra")

    add, suggest = st.columns([1, 1])
    if add.button("Add alias", width="stretch",
                  disabled=not (prefix and local)):
        project.add_alias(prefix, [local])
        st.success("Alias added.")
        st.rerun()

    if suggest.button("Suggest aliases", width="stretch",
                      help="Match recorded path components against local trees. "
                           "Review before trusting — directory names repeat."):
        recorded = [m.pattern or (m.paths[0] if m.paths else "")
                    for m in project.measurements()]
        roots = ["/mnt", "/media", str(Path.home())]
        found = suggest_aliases([r for r in recorded if r],
                                [r for r in roots if Path(r).is_dir()])
        if found:
            st.session_state["nano_alias_suggestions"] = [
                {"prefix": a.prefix, "candidates": list(a.candidates),
                 "label": a.label} for a in found]
        else:
            st.info("Nothing matched. Set the alias by hand.")

    for index, item in enumerate(st.session_state.get("nano_alias_suggestions", [])):
        row = st.columns([4, 1])
        row[0].code(f"{item['prefix']}  →  {item['candidates'][0]}")
        if row[1].button("Use", key=f"nano_use_alias_{index}"):
            project.add_alias(item["prefix"], item["candidates"], item["label"])
            st.session_state.pop("nano_alias_suggestions", None)
            st.rerun()

# ---------------------------------------------------------------------------
# Metadata sources
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.subheader("Metadata")
    st.caption(
        "Authored `.py` dicts are the source of truth and are never edited. "
        "Re-reading merges onto the same sample ids rather than duplicating."
    )

    if project.config.metadata_sources:
        st.dataframe(
            [{"file": Path(s["path"]).name, "adapter": s.get("adapter", ""),
              "path": s["path"]} for s in project.config.metadata_sources],
            width="stretch", hide_index=True,
        )
    else:
        st.caption("No sources recorded yet.")

    meta_dir = project.root / "MetaData"
    found = sorted(meta_dir.glob("*.py")) if meta_dir.is_dir() else []
    known = {s["path"] for s in project.config.metadata_sources}
    new = [p for p in found if str(p) not in known]

    if new:
        st.caption(f"{len(new)} file(s) in MetaData/ not yet read:")
        chosen = st.multiselect("Read these", [p.name for p in new],
                                default=[p.name for p in new],
                                key="nano_new_sources")
        if st.button("Ingest", disabled=not chosen):
            for path in new:
                if path.name in chosen:
                    try:
                        ids = project.ingest(path)
                        st.success(f"{path.name}: {len(ids)} samples")
                    except Exception as exc:
                        st.error(f"{path.name}: {type(exc).__name__}: {exc}")
            st.rerun()

    left, right = st.columns(2)
    if left.button("Re-read all sources", width="stretch",
                   disabled=not project.config.metadata_sources):
        result = project.reingest()
        st.success(f"Re-read {len(result)} source(s).")
        st.rerun()
    if right.button("Attach data folders", width="stretch"):
        created = project.attach_folders()
        st.success(f"Attached {len(created)} measurement(s).")
        st.rerun()

# ---------------------------------------------------------------------------
# Contents
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.subheader("What is in it")

    if len(project):
        frame = project.to_dataframe(level="measurement")
        if not frame.empty:
            counts = (frame.groupby(["modality_label", "group", "stage"])
                      .size().reset_index(name="measurements"))
            st.dataframe(counts, width="stretch", hide_index=True)

        with st.expander("Unreadable measurements", expanded=False):
            rows = [
                {"measurement": m["measurement_id"], "missing": m["missing"][0]}
                for sample in report["samples"] for m in sample["measurements"]
                if not m["available"] and m["missing"]
            ]
            if rows:
                st.dataframe(rows, width="stretch", hide_index=True)
            else:
                st.caption("Everything resolves.")
    else:
        st.caption("No samples yet — read a metadata file above.")

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

left, right = st.columns([3, 1])
with left:
    if st.button("💾 Save project", type="primary"):
        path = project.save()
        st.success(f"Saved to {path}")
with right:
    if st.button("Close", width="stretch"):
        close_workbench()
        st.rerun()

st.caption(
    "Saving writes `.nanoorganizer/project.json` (aliases, sources) and "
    "`samples.json` (the store). The authored metadata is untouched."
)
