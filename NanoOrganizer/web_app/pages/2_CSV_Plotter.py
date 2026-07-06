#!/usr/bin/env python3
"""Enhanced CSV/NPZ Plotter — full per-curve styling.

Thin page wrapper that runs the standalone tool in ``web/`` so the two stay
in sync. Exposed here so it appears in the multi-page sidebar.
"""
import runpy
from pathlib import Path

_APP = Path(__file__).resolve().parents[1].parent / "web" / "csv_plotter_enhanced.py"
runpy.run_path(str(_APP), run_name="__main__")
