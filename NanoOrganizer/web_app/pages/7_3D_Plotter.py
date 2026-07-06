#!/usr/bin/env python3
"""3D Plotter — interactive 3D visualization (Plotly).

Thin page wrapper around the standalone tool in ``web/``.
"""
import runpy
from pathlib import Path

_APP = Path(__file__).resolve().parents[1].parent / "web" / "plotter_3d.py"
runpy.run_path(str(_APP), run_name="__main__")
