#!/usr/bin/env python3
"""Console-script entry point: ``nanoorganizer-multi``."""

import subprocess
import sys
from pathlib import Path


def main():
    """Launch the Multi-Axes Plotter."""
    app_path = Path(__file__).resolve().parent / "multi_axes_plotter.py"
    sys.exit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.headless", "true"
    ]))


if __name__ == "__main__":
    main()
