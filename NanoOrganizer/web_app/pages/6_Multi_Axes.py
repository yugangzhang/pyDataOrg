#!/usr/bin/env python3
"""Multi-Axes Plotter — publication-ready multi-panel figures.

Thin page wrapper around the standalone tool in ``web/``.
"""
import runpy
from pathlib import Path

_APP = Path(__file__).resolve().parents[1].parent / "web" / "multi_axes_plotter.py"
runpy.run_path(str(_APP), run_name="__main__")
