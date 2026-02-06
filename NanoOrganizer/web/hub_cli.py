#!/usr/bin/env python3
"""Console-script entry point: ``nanoorganizer-hub``."""

import subprocess
import sys
from pathlib import Path


def main():
    """Launch the NanoOrganizer Hub."""
    app_path = Path(__file__).resolve().parent / "hub.py"
    sys.exit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.headless", "true",
        "--server.port", "8501"
    ]))


if __name__ == "__main__":
    main()
