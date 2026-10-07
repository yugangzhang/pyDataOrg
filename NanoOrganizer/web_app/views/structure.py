#!/usr/bin/env python3
"""
Structure — drill into a folder, a metadata file or an archive, one layer at a time.

Before you can organise a dataset you have to understand its shape. This page
answers that question for anything: a directory tree, a JSON record, an HDF5
file, a saved ``.npz``, a Python metadata module. Click a thing, see what is
inside it, click again.

It reads **structure, not data** — shapes and dtypes come from file headers, so
a 4 GB tomogram is described without being opened. Long values are truncated.
Nothing here loads a dataset into memory, and nothing here plots.

The traversal itself is :mod:`NanoOrganizer.structure`, which works the same
way from a notebook::

    from NanoOrganizer.structure import tree
    print(tree("~/Repos/OrgDemo/Showcase", depth=3))
"""

from pathlib import Path

import streamlit as st

from NanoOrganizer import structure as S
from NanoOrganizer.core.pathmap import display_path
from NanoOrganizer.web_app.components.folder_browser import folder_picker
from NanoOrganizer.web_app.components.security import (
    is_path_allowed, is_restricted_mode,
)
from NanoOrganizer.web_app.state import get_workbench

st.title("🌳 Structure")
st.caption(
    "Understand a dataset's layout before organising it. Folders, JSON, HDF5, "
    "`.npz` and metadata modules all open the same way — pick a thing, see "
    "what is inside it, keep going."
)

ADDRESS = "nano_structure_address"
workbench = get_workbench()


def go(address: str) -> None:
    st.session_state[ADDRESS] = str(address)


# ---------------------------------------------------------------------------
# Where to start
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.subheader("Start from")

    shortcuts = []
    if workbench is not None:
        root = Path(workbench.project.root)
        shortcuts.append(("📁 Project root", str(root)))
        if (root / "MetaData").is_dir():
            shortcuts.append(("🔑 MetaData", str(root / "MetaData")))
        store = root / ".nanoorganizer" / "samples.json"
        if store.is_file():
            shortcuts.append(("🗃️ Saved store", str(store)))

    if shortcuts:
        columns = st.columns(len(shortcuts) + 1)
        for column, (label, target) in zip(columns, shortcuts):
            if column.button(label, key=f"nano_struct_jump_{target}",
                             width="stretch"):
                go(target)
                st.rerun()
        columns[-1].caption("…or any path below")

    chosen = folder_picker("nano_structure_pick", label="Folder",
                           default=st.session_state.get(ADDRESS, ""),
                           help="Any folder. To open a single file, paste its "
                                "full path instead.")
    typed = st.text_input(
        "…or an exact path or address", value="",
        key="nano_structure_typed",
        placeholder="/data/run.h5::entry/instrument",
        help="A file path, optionally followed by :: and a path inside the "
             "file. That is the same address the breadcrumbs produce.")

    left, right = st.columns([1, 3])
    if left.button("Open", type="primary", width="stretch",
                   disabled=not (typed or chosen)):
        go(typed.strip() or chosen)
        st.rerun()

address = st.session_state.get(ADDRESS, "")
if not address:
    st.info("Choose a folder or paste a path to begin.", icon="👆")
    st.stop()

# The browser must not become a way around the allowed-roots rule.
outer, _ = S.split_address(address)
if is_restricted_mode() and not is_path_allowed(outer, allow_nonexistent=True):
    st.error("That path is outside the folders this account may browse.",
             icon="🔒")
    st.stop()

# ---------------------------------------------------------------------------
# Where you are
# ---------------------------------------------------------------------------

trail = S.breadcrumbs(address)
st.markdown("**Path**")
crumbs = st.columns(min(len(trail), 10))
for column, (label, target) in zip(crumbs, trail[-10:]):
    if column.button(label or "/", key=f"nano_crumb_{target}",
                     width="stretch", help=target):
        go(target)
        st.rerun()

node = S.describe(address)
if node.kind == "error":
    st.error(f"{node.name} — {node.detail}", icon="🚫")
    st.stop()

st.caption(f"{node.icon} **{node.name}** · {node.detail}" if node.detail
           else f"{node.icon} **{node.name}**")
# Shown relative to where the app runs; the address itself stays absolute.
inner = address.split("::", 1)[1] if "::" in address else ""
st.code(display_path(outer) + (f"::{inner}" if inner else ""), language=None)

if outer.suffix.lower() == ".py":
    st.warning(
        "Reading a Python metadata module **runs the code in it**. Only open "
        "modules you or your collaborators wrote.", icon="⚠️")

# ---------------------------------------------------------------------------
# What is inside
# ---------------------------------------------------------------------------

show_hidden = st.toggle(
    "Show hidden entries", value=False, key="nano_structure_hidden",
    help="Dot-files and __pycache__. They are counted in the folder summary "
         "either way, never silently dropped.")

entries = S.children(address, show_hidden=show_hidden)
if not entries:
    st.info("Nothing inside this one — it is a leaf.", icon="🍃")
else:
    left, right = st.columns([3, 1])
    needle = left.text_input("Filter", value="", key="nano_structure_filter",
                             placeholder="substring of a name")
    right.metric("Items", len(entries))

    if needle:
        lowered = needle.lower()
        entries = [e for e in entries
                   if lowered in e.name.lower() or lowered in e.detail.lower()]
        if not entries:
            st.caption("Nothing matches that filter.")

    with st.container(border=True):
        for index, child in enumerate(entries):
            name_column, detail_column = st.columns([2, 3])
            if child.expandable and child.address:
                if name_column.button(child.label, key=f"nano_child_{index}",
                                      width="stretch"):
                    go(child.address)
                    st.rerun()
            else:
                name_column.markdown(child.label)
            detail_column.caption(child.detail or "—")

# ---------------------------------------------------------------------------
# The shape of it, several layers down
# ---------------------------------------------------------------------------

with st.expander("Preview several layers at once", expanded=False):
    left, right = st.columns(2)
    depth = left.slider("Depth", 1, 5, 2, key="nano_structure_depth")
    width = right.slider("Items per layer", 3, 30, 10,
                         key="nano_structure_width")

    with st.spinner("Walking…"):
        text = S.tree(address, depth=depth, limit=width,
                      show_hidden=show_hidden)
    st.code(text, language=None)
    st.download_button("Download this tree", text,
                       file_name=f"{Path(str(outer)).name or 'structure'}.txt",
                       mime="text/plain", key="nano_structure_download")
    st.caption("The same text comes from "
               "`NanoOrganizer.structure.tree(address, depth=…)` in a notebook.")
