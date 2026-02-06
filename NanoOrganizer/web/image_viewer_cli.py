#!/usr/bin/env python3
"""Console-script entry point: ``nanoorganizer-img``."""

import subprocess
import sys
from pathlib import Path


def main():
    """Launch the 2D Image Viewer."""
    app_path = Path(__file__).resolve().parent / "image_viewer.py"
    sys.exit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.headless", "true"
    ]))


if __name__ == "__main__":
    main()
