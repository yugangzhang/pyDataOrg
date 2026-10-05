#!/usr/bin/env python3
"""Console-script entry points for NanoOrganizer web app.

Commands
--------
viz                 Secure mode: viz [port] [password]
viz-adduser         Add/update a user in the multi-user JSON store
"""

import argparse
import getpass
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from NanoOrganizer.core.access_config import (
    load_access_config,
    discover_config_path,
)

DEFAULT_PORT = 8800

# Extra directories secure mode should whitelist are site-specific, so the
# package hardcodes none. Name them either in NANOORGANIZER_EXTRA_ROOTS
# (os.pathsep-separated) or under [paths] extra_roots in pyViz.conf.
DEFAULT_DATA_ROOTS: tuple = ()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _launch_streamlit(port: int, env: Optional[dict] = None) -> int:
    app_path = Path(__file__).resolve().parent / "Home.py"
    # Bind all interfaces by default so the app is reachable via the machine's
    # hostname/IP from other computers (e.g. http://your-server:PORT). Binding
    # to 127.0.0.1 would only accept connections from the local machine.
    # Override with NANOORGANIZER_HOST=127.0.0.1 to restrict to localhost.
    source_env = env if env is not None else os.environ
    address = source_env.get("NANOORGANIZER_HOST", "0.0.0.0")
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
            "--server.address",
            address,
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

    access = load_access_config()
    # In multi-user mode (INI/JSON users configured) the shared password is
    # unused — each user logs in with their own credentials — so don't prompt.
    multi_user = bool(
        os.environ.get("NANOORGANIZER_USERS_FILE", "").strip()
        or access.users
    )

    password = args.password
    if not multi_user:
        if password is None:
            password = getpass.getpass("Set access password: ")
        if not password:
            parser.error("Password cannot be empty.")

    start_dir = Path(access.start_dir or Path.cwd()).expanduser().resolve()
    home_dir = Path.home().resolve()

    # Extra roots (e.g. a shared data mount) can be injected via the
    # NANOORGANIZER_EXTRA_ROOTS env var — os.pathsep-separated paths. Each is
    # resolved (symlinks followed) so it matches how is_path_allowed() checks.
    extra_raw = os.environ.get("NANOORGANIZER_EXTRA_ROOTS", "")
    extra_roots = [Path(p).expanduser().resolve()
                   for p in extra_raw.split(os.pathsep) if p.strip()]

    # Built-in data mounts, added only when they exist on this machine.
    for candidate in DEFAULT_DATA_ROOTS:
        path = Path(candidate).expanduser()
        if path.is_dir():
            extra_roots.append(path.resolve())

    # A private pyViz.conf may name a mount the public package cannot know
    # about; include those so single-password mode can reach them.
    for configured_root in access.extra_roots:
        path = Path(configured_root).expanduser()
        if path.is_dir():
            extra_roots.append(path.resolve())

    roots = []
    for root in (start_dir, home_dir, *extra_roots):
        if root not in roots:
            roots.append(root)

    env = os.environ.copy()
    env["NANOORGANIZER_SECURE_MODE"] = "1"
    env["NANOORGANIZER_USER_MODE"] = "1"
    env["NANOORGANIZER_START_DIR"] = str(start_dir)
    env["NANOORGANIZER_ALLOWED_ROOTS"] = os.pathsep.join(str(root) for root in roots)
    config_path = discover_config_path()
    if config_path is not None:
        env["NANOORGANIZER_CONFIG"] = str(config_path)
    if not multi_user:
        env["NANOORGANIZER_PASSWORD_HASH"] = _hash_password(password)

    sys.exit(_launch_streamlit(port, env=env))


def main_adduser():
    """Add or update a user in the multi-user JSON store.

    Usage::

        viz-adduser USERS_FILE USERNAME [--admin] [--root PATH ...]

    Prompts for a password (never echoed) and writes its SHA-256 hash. The file
    is created if missing. Point the app at it with
    NANOORGANIZER_USERS_FILE=USERS_FILE.
    """
    parser = argparse.ArgumentParser(
        prog="viz-adduser",
        description="Add or update a user in the NanoOrganizer multi-user store.",
    )
    parser.add_argument("users_file", help="Path to the JSON user store.")
    parser.add_argument("username", help="Username to add or update.")
    parser.add_argument("--admin", action="store_true",
                        help="Grant full filesystem access (ignores --root).")
    parser.add_argument("--root", action="append", default=[], metavar="PATH",
                        help="Allowed folder for this user (repeatable).")
    args = parser.parse_args()

    users_path = Path(args.users_file).expanduser()
    users = {}
    if users_path.exists():
        try:
            with open(users_path, "r", encoding="utf-8") as fh:
                users = json.load(fh)
            if not isinstance(users, dict):
                parser.error(f"{users_path} does not contain a JSON object.")
        except ValueError as exc:
            parser.error(f"Could not parse {users_path}: {exc}")

    password = getpass.getpass(f"Set password for '{args.username}': ")
    if not password:
        parser.error("Password cannot be empty.")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        parser.error("Passwords do not match.")

    key = args.username.strip().lower()
    entry = {"password": _hash_password(password)}
    if args.admin:
        entry["admin"] = True
    else:
        roots = [str(Path(r).expanduser()) for r in args.root]
        if roots:
            entry["roots"] = roots
    users[key] = entry

    users_path.parent.mkdir(parents=True, exist_ok=True)
    with open(users_path, "w", encoding="utf-8") as fh:
        json.dump(users, fh, indent=2, sort_keys=True)
        fh.write("\n")
    try:
        os.chmod(users_path, 0o600)
    except OSError:
        pass

    scope = "admin (full access)" if args.admin else (
        f"roots={entry.get('roots', [])}" if not args.admin else "")
    print(f"✓ User '{key}' saved to {users_path} ({scope}).")
    print(f"  Launch the app with NANOORGANIZER_USERS_FILE={users_path}")


if __name__ == "__main__":
    main()
