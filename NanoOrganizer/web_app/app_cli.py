#!/usr/bin/env python3
"""Console-script entry points for NanoOrganizer web app.

Commands
--------
viz                 Secure mode: viz [port] [password]
"""

import argparse
import getpass
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

DEFAULT_PORT = 5647


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _launch_streamlit(port: int, env: Optional[dict] = None) -> int:
    app_path = Path(__file__).resolve().parent / "Home.py"
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.headless",
            "true",
            "--server.port",
            str(port),
        ],
        env=env,
    )


def _validate_port(port: int) -> int:
    if not (1 <= port <= 65535):
        raise ValueError("Port must be between 1 and 65535.")
    return port


def main():
    """Launch the NanoOrganizer multi-page web app."""
    sys.exit(_launch_streamlit(DEFAULT_PORT))


def main_user():
    """Launch NanoOrganizer in restricted user mode.

    The folder browser is locked to the directory where this command is run.
    Users cannot navigate above this directory.
    """
    start_dir = Path.cwd().resolve()
    env = os.environ.copy()
    env["NANOORGANIZER_USER_MODE"] = "1"
    env["NANOORGANIZER_START_DIR"] = str(start_dir)
    env["NANOORGANIZER_ALLOWED_ROOTS"] = str(start_dir)
    sys.exit(_launch_streamlit(DEFAULT_PORT, env=env))


def main_secure():
    """Launch secure mode via `viz [port] [password]`."""
    parser = argparse.ArgumentParser(
        prog="viz",
        description=(
            "Launch NanoOrganizer in secure mode with password protection and "
            "filesystem restrictions."
        ),
    )
    parser.add_argument(
        "port",
        nargs="?",
        type=int,
        default=DEFAULT_PORT,
        help=f"Streamlit port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "password",
        nargs="?",
        help="Access password. If omitted, you will be prompted securely.",
    )

    args = parser.parse_args()

    try:
        port = _validate_port(args.port)
    except ValueError as exc:
        parser.error(str(exc))

    password = args.password
    if password is None:
        password = getpass.getpass("Set access password: ")
    if not password:
        parser.error("Password cannot be empty.")

    start_dir = Path.cwd().resolve()
    home_dir = Path.home().resolve()

    roots = []
    for root in (start_dir, home_dir):
        if root not in roots:
            roots.append(root)

    env = os.environ.copy()
    env["NANOORGANIZER_SECURE_MODE"] = "1"
    env["NANOORGANIZER_USER_MODE"] = "1"
    env["NANOORGANIZER_START_DIR"] = str(start_dir)
    env["NANOORGANIZER_ALLOWED_ROOTS"] = os.pathsep.join(str(root) for root in roots)
    env["NANOORGANIZER_PASSWORD_HASH"] = _hash_password(password)

    sys.exit(_launch_streamlit(port, env=env))


if __name__ == "__main__":
    main()
