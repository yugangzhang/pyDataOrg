#!/usr/bin/env python3
"""2D Image Viewer — view .npy/.npz/detector images and stacks.

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

_APP = Path(__file__).resolve().parents[1].parent / "web" / "image_viewer.py"
runpy.run_path(str(_APP), run_name="__main__")
