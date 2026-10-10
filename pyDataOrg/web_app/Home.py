#!/usr/bin/env python3
"""
pyDataOrg web app — navigation entry point.

Run with::

    streamlit run pyDataOrg/web_app/Home.py

or the ``viz`` console command.

The app used to be a flat list of fourteen pages, most of them one X-ray
scattering technique each. It is now a five-step workflow plus a tools section,
with technique chosen *inside* the Visualize page from the modality registry.
Adding a technique therefore changes no page.

Navigation is declared here with ``st.navigation``, which also means the
``pages/`` directory is no longer auto-discovered — the older scattering pages
remain on disk and can still be run directly, but they do not clutter the
sidebar. Scattering visualisation proper lives in **a scattering package**.
"""

from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="pyDataOrg",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

from pyDataOrg.web_app.components.floating_button import (     # noqa: E402
    floating_sidebar_toggle,
)
from pyDataOrg.web_app.components.security import (            # noqa: E402
    current_user, format_allowed_roots, initialize_security_context,
    is_admin, require_authentication,
)
from pyDataOrg.core.pathmap import display_path                # noqa: E402
from pyDataOrg.web_app.state import sidebar_status             # noqa: E402

initialize_security_context()
require_authentication()

HERE = Path(__file__).resolve().parent
VIEWS = HERE / "views"
PAGES = HERE / "pages"


def view(name: str, title: str, icon: str, default: bool = False):
    return st.Page(VIEWS / name, title=title, icon=icon, default=default)


def tool(name: str, title: str, icon: str):
    """Mount a retained general-purpose tool from the old pages folder."""
    return st.Page(PAGES / name, title=title, icon=icon)


sections = {
    "Workflow": [
        view("overview.py", "Overview", "🔬", default=True),
        # Notebooks 10 → 11 → 12 with buttons: simulate, build, use.
        view("demo.py", "Demo", "🎓"),
        view("project.py", "Project", "📁"),
        view("structure.py", "Structure", "🌳"),
        view("explore.py", "Explore & Filter", "🔎"),
        view("visualize.py", "Visualize", "📈"),
        view("analyze.py", "Analyze", "🧪"),
        view("compare.py", "Compare", "📊"),
    ],
}

# General-purpose utilities that survived the consolidation. Each is optional:
# a missing file must not take the whole app down.
TOOLS = [
    ("8_🎯_Universal_Plotter.py", "Universal Plotter", "🎯"),
    ("7_🧪_Test_Data_Generator.py", "Test Data Generator", "🧪"),
    ("8_Data_Manager.py", "Data Manager", "🔧"),
]
tools = [tool(name, title, icon) for name, title, icon in TOOLS
         if (PAGES / name).exists()]
if tools:
    sections["Tools"] = tools

navigation = st.navigation(sections, position="sidebar")

# ---------------------------------------------------------------------------
# Sidebar chrome, drawn for every page
# ---------------------------------------------------------------------------

with st.sidebar:
    if st.session_state.get("user_mode"):
        if st.session_state.get("secure_mode"):
            identity = current_user()
            if identity:
                role = "admin" if is_admin() else "user"
                st.caption(f"Signed in as **{identity}** ({role})")
            st.caption(f"🔒 Secure mode — allowed: `{format_allowed_roots()}`")
        else:
            st.caption("🔒 Restricted to `"
                       + display_path(st.session_state["user_start_dir"],
                                      max_up=0) + "`")

sidebar_status()
floating_sidebar_toggle()

navigation.run()
