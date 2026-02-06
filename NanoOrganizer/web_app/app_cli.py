#!/usr/bin/env python3
"""Console-script entry point: ``nanoorganizer`` - Main app on port 8501."""

import subprocess
import sys
from pathlib import Path


def main():
    """Launch the NanoOrganizer multi-page web app."""
    app_path = Path(__file__).resolve().parent / "Home.py"
    sys.exit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(app_path),
        "--server.headless", "true",
        "--server.port", "8501"
    ]))


if __name__ == "__main__":
    main()
