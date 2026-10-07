#!/usr/bin/env python3
"""
Project — open a folder, map its paths, read its metadata.

The first page of the workflow and the only one that writes to disk. Everything
downstream reads the store this page builds.
"""

import glob as _glob
from pathlib import Path

import streamlit as st

from NanoOrganizer.core import modality as modality_registry
from NanoOrganizer.core.pathmap import display_path, is_relative, suggest_aliases
from NanoOrganizer.core.schema import flatten_dict
from NanoOrganizer.web_app.components.folder_browser import folder_picker
from NanoOrganizer.web_app.state import (
    close_workbench, get_workbench, new_in_session, open_in_session,
)

st.title("📁 Project")
st.caption(
    "A project is a folder of samples: authored metadata in `MetaData/`, "
    "data under `<Modality>Data/<SampleID>/`, and a store in `.nanoorganizer/`. "
    "Data that lives somewhere else entirely is **linked**, further down the "
    "page — the folder below only has to hold the store."
)

workbench = get_workbench()

# ---------------------------------------------------------------------------
# Open
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.subheader("Open or create")

    mode = st.radio(
        "What are you starting from", ["An existing project", "Nothing yet"],
        horizontal=True, key="nano_open_mode",
        captions=[
            "A folder with `MetaData/`, data folders, or a store written "
            "earlier — including one a notebook saved.",
            "No project: an empty organizer you fill by linking data from "
            "wherever it already lives.",
        ],
    )

    default_root = (str(workbench.project.store_path)
                    if workbench and workbench.project.single_file
                    else str(workbench.project.root) if workbench else "")
    root = folder_picker("nano_project_root", label="Project folder or .json",
                         default=default_root,
                         help="A project folder — or the path to a single "
                              "`.json` organizer, the kind `Organizer(...)` "
                              "writes in a notebook.")
    st.caption(
        "A folder is a project: `MetaData/`, data underneath, a store in "
        "`.nanoorganizer/`. A path ending in **`.json`** is a single-document "
        "organizer instead — one file naming data that lives anywhere."
    )

    if mode == "An existing project":
        left, middle, right = st.columns([1, 1, 2])
        reingest = left.toggle("Read metadata", value=True, key="nano_reingest",
                               help="Read MetaData/*.py. Turn off to reload the "
                                    "saved store only.")
        attach = middle.toggle("Attach data folders", value=True,
                               key="nano_attach",
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
    else:
        left, right = st.columns([2, 1])
        new_name = left.text_input(
            "Name it", key="nano_new_name", placeholder="Cu-Au CO2RR library",
            help="Shown in the sidebar and saved with the store.")
        if right.button("Create organizer", type="primary", width="stretch",
                        disabled=not root):
            try:
                new_in_session(root, name=new_name.strip())
                st.success(f"Created an empty organizer in {Path(root).name}. "
                           f"Link data into it below.")
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

    from NanoOrganizer.demo import demo_root

    target = st.text_input(
        "Write it to",
        value=display_path(demo_root("Showcase" if kind == "Multimodal showcase"
                                     else "QuickDemo")),
        key="nano_demo_root",
        help="Must be empty, or a demo project this button made earlier. "
             "Generated data goes under one parent so a few runs cannot "
             "scatter directories across your home folder; set "
             "$NANOORGANIZER_DEMO_ROOT to move it.")

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
            [{"recorded prefix": display_path(alias.prefix, max_up=0),
              "resolves to": ", ".join(display_path(c, max_up=0)
                                       for c in alias.candidates),
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
        row[0].code(f"{display_path(item['prefix'], max_up=0)}  →  "
                    f"{display_path(item['candidates'][0], max_up=0)}")
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
        # A source inside the project is recorded relative to it; one
        # outside is shown relative to where the app runs.
        st.dataframe(
            [{"file": Path(s["path"]).name, "adapter": s.get("adapter", ""),
              "path": display_path(s["path"])}
             for s in project.config.metadata_sources],
            width="stretch", hide_index=True,
        )
    else:
        st.caption("No sources recorded yet.")

    meta_dir = project.root / "MetaData"
    found = sorted(meta_dir.glob("*.py")) if meta_dir.is_dir() else []
    known = {project.resolver.anchor(s["path"])
             for s in project.config.metadata_sources}
    new = [p for p in found if project.resolver.anchor(p) not in known]

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
# Samples and the conditions they were made under
# ---------------------------------------------------------------------------

def _set_dotted(params: dict, column: str, value):
    """Write ``value`` at a dotted path, building the dicts on the way down."""
    keys = column.split(".")
    target = params
    for key in keys[:-1]:
        nested = target.get(key)
        if not isinstance(nested, dict):
            nested = {}
            target[key] = nested
        target = nested
    target[keys[-1]] = value


def _drop_dotted(params: dict, column: str):
    """Remove a dotted path, and any dict it leaves empty."""
    keys = column.split(".")
    chain = [params]
    for key in keys[:-1]:
        nested = chain[-1].get(key)
        if not isinstance(nested, dict):
            return
        chain.append(nested)
    chain[-1].pop(keys[-1], None)
    for level in range(len(chain) - 1, 0, -1):
        if not chain[level]:
            chain[level - 1].pop(keys[level - 1], None)


with st.container(border=True):
    st.subheader("Samples and their conditions")
    st.caption(
        "Links give the organizer files; this gives it columns. Without a "
        "parameter to filter on, *show me the gold-rich ones* has nothing to "
        "ask about. Edit the grid and **Apply** — these become dotted columns "
        "like `synthesis.au_fraction` everywhere downstream."
    )

    # Offer the stage that actually carries parameters first. A project whose
    # stages sort to put an empty one at the top would otherwise open on a
    # blank grid and look like it had lost everything.
    def _richness(stage_id: str) -> tuple:
        count = sum(len(flatten_dict(sample.stage(stage_id).params))
                    for sample in project if sample.stage(stage_id) is not None)
        return (-count, stage_id)

    stages = sorted({s for sample in project for s in sample.stages},
                    key=_richness) or ["synthesis"]
    head = st.columns([2, 2, 1])
    stage_name = head[0].selectbox(
        "Stage", stages + ["➕ new stage…"], key="nano_param_stage",
        help="One execution in a sample's history. Most organizers only ever "
             "need 'synthesis'.")
    if stage_name == "➕ new stage…":
        stage_name = head[1].text_input("New stage name", value="",
                                        key="nano_param_newstage").strip()

    new_param = head[2].text_input(
        "Add a parameter", key="nano_param_newcol", placeholder="au_fraction",
        help="Adds an empty column to the grid below.")

    if not len(project):
        st.caption("No samples yet. Add one below, or link some data.")

    # The grid's own columns. An authored record often repeats `sample_id`
    # inside its parameters; a duplicate column is an error in st.data_editor,
    # and editing the copy would not change the identity anyway.
    RESERVED = ("sample_id", "status")

    columns: list = []
    shadowed: list = []
    for sample in project:
        stage = sample.stage(stage_name) if stage_name else None
        if stage is not None:
            for column in flatten_dict(stage.params):
                if column in RESERVED:
                    if column not in shadowed:
                        shadowed.append(column)
                    continue
                if column not in columns:
                    columns.append(column)
    if shadowed:
        st.caption(f"Not shown: `{'`, `'.join(shadowed)}` — the record repeats "
                   f"a field the grid already owns. It is kept, untouched.")

    extra = st.session_state.setdefault("nano_param_extra_cols", [])
    if new_param and new_param not in RESERVED and new_param not in columns \
            and new_param not in extra:
        extra.append(new_param)
    for column in extra:
        if column not in columns:
            columns.append(column)

    rows = []
    for sample in project:
        stage = sample.stage(stage_name) if stage_name else None
        flat = flatten_dict(stage.params) if stage is not None else {}
        row = {"sample_id": sample.sample_id,
               "status": stage.status if stage is not None else ""}
        row.update({column: flat.get(column) for column in columns})
        rows.append(row)

    import pandas as pd

    grid = pd.DataFrame(rows, columns=["sample_id", "status"] + columns)
    edited = st.data_editor(
        grid, width="stretch", hide_index=True, num_rows="dynamic",
        key="nano_param_editor",
        disabled=[] if stage_name else ["sample_id"],
        column_config={
            "sample_id": st.column_config.TextColumn(
                "sample_id", required=True,
                help="Add a row to create a sample — a synthesis that failed "
                     "has no files and is still a result."),
            "status": st.column_config.TextColumn(
                "status", help="done / error / aborted. A stage that records "
                               "a failure is excluded from `ok` filters."),
        },
    )

    left, right = st.columns([1, 1])
    if left.button("Apply changes", type="primary", width="stretch",
                   disabled=not stage_name):
        try:
            seen = []
            for record in edited.to_dict("records"):
                sample_id = str(record.get("sample_id") or "").strip()
                if not sample_id:
                    continue
                seen.append(sample_id)
                fields = {}
                status = record.get("status")
                if isinstance(status, str) and status.strip():
                    fields["status"] = status.strip()

                stage = project.set_params(sample_id, stage=stage_name,
                                           **fields)
                for column in columns:
                    value = record.get(column)
                    if value is None or (isinstance(value, float)
                                         and value != value) or value == "":
                        _drop_dotted(stage.params, column)
                    else:
                        _set_dotted(stage.params, column, value)

            removed = [s for s in project.sample_ids() if s not in seen]
            for sample_id in removed:
                project.remove_sample(sample_id)

            st.session_state["nano_param_extra_cols"] = []
            note = f", removed {len(removed)}" if removed else ""
            st.success(f"Applied to {len(seen)} sample(s){note}.")
            st.rerun()
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    right.caption("Deleting a row removes the sample and its links. "
                  "No file is touched.")

# ---------------------------------------------------------------------------
# Linking data that lives elsewhere
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.subheader("Link data from anywhere")
    st.caption(
        "Attaching data folders above needs the `<Modality>Data/<SampleID>/` "
        "layout under the project root. This does not: point it at the "
        "microscope's share or a beamline mount and the files stay where they "
        "are. Nothing is copied — the path is recorded as given, and the mount "
        "it sits on becomes an alias so the store still moves."
    )

    existing = project.sample_ids()
    NEW = "➕ new sample…"

    chosen_sample = st.selectbox(
        "Sample", ([NEW] + existing) if existing else [NEW],
        key="nano_link_sample",
        help="The sample this data belongs to. A new id creates the sample.")
    sample_id = chosen_sample
    if chosen_sample == NEW:
        sample_id = st.text_input("New sample id", key="nano_link_new_id",
                                  placeholder="CuAu05").strip()

    left, right = st.columns(2)
    # Options are the registry *keys*, not the Modality objects: a widget's
    # value has to survive a session-state round trip as a plain string.
    options = [m.key for m in modality_registry.list_modalities()]
    labels = {m.key: f"{m.label} · {m.key} ({m.group})"
              for m in modality_registry.list_modalities()}
    picked_key = left.selectbox(
        "Technique", options, key="nano_link_modality",
        format_func=lambda k: labels.get(k, k),
        help="What the data is. The group decides how it will be drawn.")
    picked = modality_registry.get(picked_key)

    source_kind = right.radio(
        "Source", ["Folder", "Pattern or file"], horizontal=True,
        key="nano_link_kind",
        help="A folder is listed now — an auditable snapshot. A pattern is "
             "re-expanded every time the data is read, so frames written "
             "later appear; that is the one to use while a run is going.")

    if source_kind == "Folder":
        folder = folder_picker("nano_link_folder", label="Data folder",
                               help="The folder holding this sample's files.")
        live = st.toggle(
            "Keep it live", value=False, key="nano_link_live",
            help="Record a glob instead of today's file list.")
        glob_pattern = ""
        if live:
            glob_pattern = st.text_input(
                "Pattern inside the folder", value="*", key="nano_link_glob")
        source = folder
    else:
        source = st.text_input(
            "Path or glob", key="nano_link_pattern",
            placeholder="/mnt/data/beamline/2024_3/CuAu05_*.dat",
            help="Absolute, or relative to the project folder — a relative "
                 "link travels with the project when the folder moves."
        ).strip()
        folder, live, glob_pattern = "", False, ""

    columns = st.columns(3)
    link_stage = columns[0].text_input("Stage", value="characterization",
                                       key="nano_link_stage")
    link_role = columns[1].text_input(
        "Role", value="", key="nano_link_role",
        help="Only needed for a second measurement of the same technique on "
             "the same sample — an as-made and a post-reaction scan, say.")
    widen = columns[2].text_input(
        "Extra extensions", value="", key="nano_link_ext",
        placeholder=".dat, .txt",
        help="Link files this technique does not normally claim.")

    # Say what will happen before it happens: a link that silently matches
    # nothing is the failure mode worth spending a preview on.
    # Inside the project, record it relative to the project: the link then
    # travels with the folder, and names nobody's home directory.
    if source and not is_relative(source):
        try:
            source = Path(source).expanduser().relative_to(
                project.root).as_posix()
        except ValueError:
            pass

    preview = []
    if source:
        try:
            # A relative source means relative to the project, as link() reads it.
            anchored = project.resolver.anchor(source)
            probe = Path(anchored).expanduser()
            if source_kind == "Folder" and probe.is_dir():
                if live:
                    preview = sorted(probe.glob(glob_pattern or "*"))
                else:
                    suffixes = tuple(
                        e.strip().lower() if e.strip().startswith(".")
                        else "." + e.strip().lower()
                        for e in widen.split(",") if e.strip()
                    ) or picked.extensions
                    preview = [p for p in sorted(probe.glob("*"))
                               if p.is_file() and
                               (not suffixes or p.suffix.lower() in suffixes)]
            elif any(c in source for c in "*?["):
                preview = sorted(_glob.glob(anchored))
            elif probe.exists():
                preview = [probe]
        except OSError:
            preview = []

    if source:
        if preview:
            st.caption(f"Matches **{len(preview)} file(s)** — "
                       f"{', '.join(Path(str(p)).name for p in preview[:3])}"
                       f"{' …' if len(preview) > 3 else ''}")
        else:
            st.caption("Nothing matches here yet. A pattern that resolves "
                       "later is still a valid link; a folder that is empty "
                       "is not.")

    if st.button("🔗 Link", type="primary", width="stretch",
                 disabled=not (sample_id and source)):
        try:
            extensions = [e.strip() if e.strip().startswith(".")
                          else "." + e.strip()
                          for e in widen.split(",") if e.strip()] or None
            if source_kind == "Folder" and live:
                measurement = project.link_folder(
                    sample_id, picked.key, source,
                    pattern=glob_pattern or "*", stage=link_stage.strip(),
                    role=link_role.strip())
            else:
                measurement = project.link(
                    sample_id, picked.key, source, stage=link_stage.strip(),
                    role=link_role.strip(), extensions=extensions)
            found = len(measurement.resolve(project.resolver))
            st.success(f"Linked {measurement.measurement_id} — "
                       f"{found} file(s) readable here.")
            st.rerun()
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    links = [m for m in project.measurements() if m.meta.get("linked")]
    if links:
        with st.expander(f"Linked measurements ({len(links)})", expanded=False):
            st.dataframe(
                [{"sample": m.sample_id, "technique": m.modality,
                  "stage": m.stage, "role": m.role,
                  "files": len(m.resolve(project.resolver)),
                  "recorded": display_path(m.pattern or
                                           (m.paths[0] if m.paths else "")),
                  "live": bool(m.pattern)}
                 for m in links],
                width="stretch", hide_index=True,
            )
            drop = st.selectbox(
                "Remove one", ["(none)"] + [m.measurement_id for m in links],
                key="nano_unlink_pick")
            if st.button("Unlink", disabled=drop == "(none)"):
                sample, _, _ = drop.partition(":")
                target = next(m for m in links if m.measurement_id == drop)
                project.unlink(sample, modality=target.modality,
                               stage=target.stage, role=target.role)
                st.success(f"Removed {drop}.")
                st.rerun()

    with st.expander("Link a whole campaign from a table", expanded=False):
        st.caption(
            "One row per measurement: `sample_id`, `modality`, `source`, and "
            "optionally `stage`, `role`, `aux`. Any other column becomes "
            "metadata. This is the same table **Export links** below writes, "
            "so the round trip is: export, fix it in a spreadsheet, re-import."
        )
        uploaded = st.file_uploader("CSV of links", type=["csv", "tsv"],
                                    key="nano_link_csv")
        if uploaded is not None:
            import pandas as pd

            try:
                incoming = pd.read_csv(
                    uploaded, sep="\t" if uploaded.name.endswith(".tsv") else ",")
                st.dataframe(incoming.head(10), width="stretch",
                             hide_index=True)
                st.caption(f"{len(incoming)} row(s).")
                if st.button("Link every row", key="nano_link_csv_go"):
                    made = project.link_table(incoming)
                    st.success(f"Linked {len(made)} measurement(s).")
                    st.rerun()
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    st.caption("Linking changes the in-memory store. **Save** at the bottom "
               "of the page to keep it.")

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
                {"measurement": m["measurement_id"],
                 "missing": display_path(m["missing"][0])}
                for sample in report["samples"] for m in sample["measurements"]
                if not m["available"] and m["missing"]
            ]
            if rows:
                st.dataframe(rows, width="stretch", hide_index=True)
            else:
                st.caption("Everything resolves.")
    else:
        st.caption("No samples yet — read a metadata file, link some data, "
                   "or add a sample above.")

# ---------------------------------------------------------------------------
# Save and export
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.subheader("Save and export")
    st.caption(
        "Saving writes `.nanoorganizer/project.json` (aliases, sources) and "
        "`samples.json` (the store) into the project folder. Nothing else is "
        "written, and the data itself is never touched or copied."
    )

    left, right = st.columns([1, 1])
    if left.button("💾 Save project", type="primary", width="stretch"):
        try:
            path = project.save()
            st.success(f"Saved to {display_path(path)}")
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
    if right.button("Close project", width="stretch"):
        close_workbench()
        st.rerun()

    st.caption(
        "**Exports** are for taking the organizer somewhere else. The links "
        "CSV is the one that comes back: edit it in a spreadsheet and feed it "
        "to *Link a whole campaign from a table* above, or to "
        "`wb.link_table()` in a notebook."
    )

    import json as _json

    exports = st.columns(3)
    try:
        links = project.links_table()
        if links:
            import pandas as pd

            exports[0].download_button(
                "⬇️ Links (CSV)", pd.DataFrame(links).to_csv(index=False),
                file_name=f"{project.config.name or 'organizer'}_links.csv",
                mime="text/csv", width="stretch",
                help="One row per measurement — re-importable.")
        else:
            exports[0].caption("No links to export.")

        if len(project):
            exports[1].download_button(
                "⬇️ Sample table (CSV)",
                project.to_dataframe().to_csv(index=False),
                file_name=f"{project.config.name or 'organizer'}_samples.csv",
                mime="text/csv", width="stretch",
                help="Parameters and derived values, one row per sample. For "
                     "reading elsewhere — this one does not come back.")

        exports[2].download_button(
            "⬇️ Store (JSON)",
            _json.dumps({"project": project.config.to_dict(),
                         "samples": [s.to_dict()
                                     for s in project.sorted_samples()]},
                        indent=2, default=str),
            file_name=f"{project.config.name or 'organizer'}_store.json",
            mime="application/json", width="stretch",
            help="The whole organizer — links, parameters and derived values.")
    except Exception as exc:
        st.error(f"Export failed — {type(exc).__name__}: {exc}", icon="🚫")
