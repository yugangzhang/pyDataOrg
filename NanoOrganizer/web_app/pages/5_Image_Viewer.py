#!/usr/bin/env python3
"""2D Image Viewer — view .npy/.npz/detector images and stacks.

Thin page wrapper around the standalone tool in ``web/``.
"""
import runpy
from pathlib import Path

_APP = Path(__file__).resolve().parents[1].parent / "web" / "image_viewer.py"
runpy.run_path(str(_APP), run_name="__main__")
