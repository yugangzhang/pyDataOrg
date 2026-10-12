#!/usr/bin/env python3
"""
pyDataOrg web app — navigation entry point.

Run with::

    dataorg gui                       # password + folder fence, port 8800
    dataorg gui 8900 --app myproj     # a plugin as the app
    streamlit run pyDataOrg/web_app/Home.py

Sections:

**Workflow** — the general pages: organise, explore, draw, analyse, compare.

**Tools** — standalone utilities that need no organizer.

The general app is the public tool and loads no plugin. A project package
(see :mod:`pyDataOrg.plugins`) runs as its own app — ``dataorg gui --app
NAME`` (``PYDATAORG_APP=NAME``): its pages first under its title, then the
general ones, all on the same open organizer.

Navigation is declared here with ``st.navigation``; only this file calls
``st.set_page_config``.
"""

import os
from pathlib import Path

import streamlit as st

from pyDataOrg import plugins as _plugins

APP = os.environ.get("PYDATAORG_APP", "").strip()
# Only an app run loads plugins: the general app shows pyDataOrg alone.
if APP:
    _plugins.load_plugins()
app = _plugins.PLUGINS.get(APP) if APP else None

st.set_page_config(
    page_title=app.heading if app else "pyDataOrg",
    page_icon=app.icon if app else "🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

from pyDataOrg.web_app.components.floating_button import (         # noqa: E402
    floating_sidebar_toggle,
)
from pyDataOrg.web_app.components.security import (                # noqa: E402
    current_user, format_allowed_roots, initialize_security_context,
    is_admin, require_authentication,
)
from pyDataOrg.core.pathmap import display_path                    # noqa: E402
from pyDataOrg.web_app.state import sidebar_status                 # noqa: E402

initialize_security_context()
require_authentication()

HERE = Path(__file__).resolve().parent
VIEWS = HERE / "views"
TOOLS = HERE / "tools"


def plugin_pages(plugin):
    """The app plugin's pages, under plain URLs (``/project``)."""
    pages = []
    for page in plugin.pages:
        path = page.file()
        if not path.exists():
            continue
        pages.append(st.Page(path, title=page.title, icon=page.icon or None,
                             url_path=page.url_path or path.stem,
                             default=page.default))
    return pages


app_pages = plugin_pages(app) if app is not None else []
# From the files, not the pages: a default page reports an empty url_path.
taken = {page.url_path or page.file().stem for page in app.pages} \
    if app is not None else set()


def view(name: str, title: str, icon: str, default: bool = False):
    """A general page — under ``general_<name>`` when the app has its own."""
    stem = Path(name).stem
    return st.Page(VIEWS / name, title=title, icon=icon,
                   url_path=f"general_{stem}" if stem in taken else None,
                   default=default and app is None)


general = {
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

sections = {}
if app is not None:
    sections[app.heading] = app_pages
sections.update(general)

# Standalone utilities. Each is optional: a missing file must not take the
# whole app down.
tools = [st.Page(TOOLS / name, title=title, icon=icon)
         for name, title, icon in (
             ("universal_plotter.py", "Universal Plotter", "🎯"),
             ("test_data_generator.py", "Test Data Generator", "🧪"),
         ) if (TOOLS / name).exists()]
if tools:
    sections["Tools"] = tools

sections = {title: pages for title, pages in sections.items() if pages}
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
    for name, error in _plugins.ERRORS.items():
        st.caption(f"⚠️ plugin `{name}` did not load: "
                   f"{error.splitlines()[0]}")
    if APP and app is None and APP not in _plugins.ERRORS:
        st.caption(f"⚠️ no plugin `{APP}` is installed — showing the "
                   f"general app.")

# Only the app's hook runs: another installed plugin must not take over
# its session.
if app is not None and app.on_page is not None:
    try:
        app.on_page()
    except Exception as exc:                           # never fatal
        st.sidebar.caption(f"⚠️ `{app.name}`: {exc}")

sidebar_status()
floating_sidebar_toggle()

navigation.run()
