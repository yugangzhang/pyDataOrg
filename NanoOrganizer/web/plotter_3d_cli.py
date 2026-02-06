#!/usr/bin/env python3
"""Console-script entry point: ``nanoorganizer-3d``."""

import subprocess
import sys
from pathlib import Path


def main():
    """Launch the 3D Plotter app."""
    app_path = Path(__file__).resolve().parent / "plotter_3d.py"
    sys.exit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.headless", "true"
    ]))


if __name__ == "__main__":
    main()
