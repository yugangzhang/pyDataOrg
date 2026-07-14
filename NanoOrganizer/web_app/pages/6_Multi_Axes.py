#!/usr/bin/env python3
"""Multi-Axes Plotter — publication-ready multi-panel figures.

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

_APP = Path(__file__).resolve().parents[1].parent / "web" / "multi_axes_plotter.py"
runpy.run_path(str(_APP), run_name="__main__")
