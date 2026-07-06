#!/usr/bin/env python3
"""Data Manager — create projects and organize metadata.

Thin page wrapper around the standalone tool in ``web/``.
"""
import runpy
from pathlib import Path

_APP = Path(__file__).resolve().parents[1].parent / "web" / "data_manager.py"
runpy.run_path(str(_APP), run_name="__main__")
