#!/usr/bin/env python3
"""3D Plotter — interactive 3D visualization (Plotly).

Thin page wrapper around the standalone tool in ``web/``.
"""
import runpy
from pathlib import Path

# Enforce login / access control before running the standalone tool. Without
# this a user could open the page URL directly and bypass authentication.
from NanoOrganizer.web_app.components.security import (
    initialize_security_context, require_authentication,
)
initialize_security_context()
require_authentication()

_APP = Path(__file__).resolve().parents[1].parent / "web" / "plotter_3d.py"
runpy.run_path(str(_APP), run_name="__main__")
