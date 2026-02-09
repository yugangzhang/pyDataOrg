#!/usr/bin/env python3
"""Console-script entry points for NanoOrganizer web app.

Commands
--------
nanoorganizer       Full access mode (port 8501)
nanoorganizer_user  Restricted user mode — locks folder browser to CWD
"""

import os
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


def main_user():
    """Launch NanoOrganizer in restricted user mode.

    The folder browser is locked to the directory where this command is run.
    Users cannot navigate above this directory.
    """
    app_path = Path(__file__).resolve().parent / "Home.py"
    env = os.environ.copy()
    env["NANOORGANIZER_USER_MODE"] = "1"
    env["NANOORGANIZER_START_DIR"] = str(Path.cwd())
    sys.exit(subprocess.call(
        [
            sys.executable, "-m", "streamlit", "run", str(app_path),
            "--server.headless", "true",
            "--server.port", "8501",
        ],
        env=env,
    ))


if __name__ == "__main__":
    main()
