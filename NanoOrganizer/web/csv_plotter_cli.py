#!/usr/bin/env python3
"""Console-script entry point: ``nanoorganizer-csv``."""

import subprocess
import sys
from pathlib import Path


def main():
    """Launch the CSV Plotter app."""
    app_path = Path(__file__).resolve().parent / "csv_plotter.py"
    sys.exit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.headless", "true"
    ]))


if __name__ == "__main__":
    main()
