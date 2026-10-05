#!/usr/bin/env python3
"""Security and access-control helpers for the Streamlit web app."""

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import streamlit as st

from NanoOrganizer.core.access_config import (
    config_users as load_config_users,
    load_access_config,
)


ENV_SECURE_MODE = "NANOORGANIZER_SECURE_MODE"
ENV_USER_MODE = "NANOORGANIZER_USER_MODE"
ENV_START_DIR = "NANOORGANIZER_START_DIR"
ENV_ALLOWED_ROOTS = "NANOORGANIZER_ALLOWED_ROOTS"
ENV_PASSWORD_HASH = "NANOORGANIZER_PASSWORD_HASH"
# Path to a JSON user store enabling multi-user login (username + password,
# per-user allowed folders). When set, it takes precedence over the single
# shared password (ENV_PASSWORD_HASH). See load_users() for the schema.
ENV_USERS_FILE = "NANOORGANIZER_USERS_FILE"


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_roots(paths: Iterable[Union[str, Path]]) -> List[Path]:
    roots: List[Path] = []
    seen = set()
    for raw in paths:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        resolved = Path(text).expanduser().resolve(strict=False)
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            roots.append(resolved)
    return roots


def hash_password(password: str) -> str:
    """Return a SHA-256 hex digest for a plaintext password."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_users() -> Dict[str, dict]:
    """Load users from the local config and optional JSON user store.

    The INI config (``~/.config/pyViz.conf`` by default) is the preferred
    deployment format.  ``NANOORGANIZER_USERS_FILE`` remains supported as a
    migration/automation format; entries from that explicit JSON file override
    entries with the same username from the INI file.

    Schema (usernames are matched case-insensitively)::

        {
          "admin_user": {"password": "<sha256-hex>", "admin": true},
          "alice":   {"password": "<sha256-hex>",
                      "roots": ["/data/projects/alice"]}
        }

    * ``password`` — SHA-256 hex digest (use ``viz-adduser`` to generate).
    * ``admin``    — optional; admins may browse the entire filesystem.
    * ``roots``    — optional list of folders the user may browse. Admins ignore
                     this. Non-admins with no roots get no filesystem access.

    Returns an empty dict when neither source contains users.
    """
    users: Dict[str, dict] = load_config_users()

    path = os.environ.get(ENV_USERS_FILE, "").strip()
    if path:
        try:
            with open(Path(path).expanduser(), "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            for name, cfg in raw.items():
                if isinstance(cfg, dict):
                    users[str(name).strip().lower()] = cfg
    return users


def _user_roots(cfg: dict) -> List[Path]:
    """Resolve the allowed roots for a single user config entry."""
    if cfg.get("admin") and cfg.get("all_paths", True):
        # The root itself is intentional: an admin account exists to reach data
        # mounts outside $HOME. The operating system stays the real boundary.
        return _normalize_roots([Path("/")])

    return _normalize_roots(list(cfg.get("roots", []) or []))


def initialize_security_context() -> None:
    """Initialize security-related session keys from environment variables."""
    access = load_access_config()
    users = load_users()
    secure_mode = _env_flag(ENV_SECURE_MODE) or access.requires_authentication
    user_mode = _env_flag(ENV_USER_MODE) or access.access_mode in {"admin", "user"}

    start_dir = Path(
        os.environ.get(ENV_START_DIR, access.start_dir or str(Path.cwd()))
    ).expanduser().resolve(strict=False)

    multi_user = bool(secure_mode and users)

    # Single shared password (no user store): every session is the same operator
    # on the same uid, so a path whitelist buys little while getting in the way
    # of pasting a data folder. Browsing is then limited only by what the OS
    # grants the server process. Multi-user mode keeps per-user roots — that
    # separation is the whole point of it — and so does plain user mode
    # (``viz-user``), which exists to lock the browser to its launch dir.
    browse_unrestricted = bool(secure_mode and not multi_user)

    if secure_mode:
        # Keep legacy pages in restricted behavior while secure mode is active.
        user_mode = True
        if multi_user:
            # Per-user roots: derived from the logged-in user's config. Until a
            # user logs in (nano_user unset), no filesystem access is granted.
            current = st.session_state.get("nano_user", "")
            cfg = users.get(str(current).strip().lower()) if current else None
            allowed_roots = _user_roots(cfg) if cfg else []
        else:
            raw_roots = os.environ.get(ENV_ALLOWED_ROOTS, "")
            env_roots = [p for p in raw_roots.split(os.pathsep) if p.strip()]
            allowed_roots = _normalize_roots(
                env_roots or list(access.extra_roots) or [start_dir]
            )
    elif user_mode:
        raw_roots = os.environ.get(ENV_ALLOWED_ROOTS, "")
        env_roots = [p for p in raw_roots.split(os.pathsep) if p.strip()]
        allowed_roots = _normalize_roots(
            env_roots or list(access.extra_roots) or [start_dir])
    else:
        allowed_roots = []

    st.session_state["secure_mode"] = secure_mode
    st.session_state["multi_user"] = multi_user
    st.session_state["user_mode"] = user_mode
    st.session_state["browse_unrestricted"] = browse_unrestricted
    st.session_state["user_start_dir"] = str(start_dir)
    st.session_state["allowed_roots"] = [str(p) for p in allowed_roots]
    st.session_state["access_mode"] = access.access_mode
    st.session_state["config_path"] = str(access.path) if access.path else ""


def is_restricted_mode() -> bool:
    """True when path restrictions should be enforced.

    Note this is about *paths*, not authentication: single-password secure mode
    still demands the password, it just does not fence the browser afterwards.
    """
    initialize_security_context()
    if st.session_state.get("browse_unrestricted"):
        return False
    return bool(st.session_state.get("secure_mode") or st.session_state.get("user_mode"))


def get_allowed_roots() -> List[Path]:
    """Return allowed path roots for the current session."""
    initialize_security_context()
    roots = st.session_state.get("allowed_roots", [])
    return _normalize_roots(roots)


def format_allowed_roots() -> str:
    roots = get_allowed_roots()
    if not roots:
        return "(no restrictions)"
    return ", ".join(str(root) for root in roots)


def is_path_allowed(path: Union[str, Path], allow_nonexistent: bool = False) -> bool:
    """Return True if path is inside an allowed root (restricted mode only)."""
    if not is_restricted_mode():
        return True

    roots = get_allowed_roots()
    if not roots:
        return False

    try:
        candidate = Path(path).expanduser()
        resolved = candidate.resolve(strict=not allow_nonexistent)
    except FileNotFoundError:
        if not allow_nonexistent:
            return False
        try:
            resolved = Path(path).expanduser().resolve(strict=False)
        except Exception:
            return False
    except Exception:
        return False

    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def assert_path_allowed(
    path: Union[str, Path],
    *,
    allow_nonexistent: bool = False,
    path_label: str = "Path",
) -> Path:
    """Return resolved path if allowed, else raise PermissionError."""
    resolved = Path(path).expanduser().resolve(strict=False)

    if not allow_nonexistent and not resolved.exists():
        raise FileNotFoundError(f"{path_label} does not exist: {resolved}")

    if not is_path_allowed(resolved, allow_nonexistent=allow_nonexistent):
        raise PermissionError(
            f"{path_label} is outside allowed folders: {resolved}\n"
            f"Allowed: {format_allowed_roots()}"
        )
    return resolved


def allowed_rglob(base_dir: Union[str, Path], pattern: str = "*.*") -> List[str]:
    """Recursively find files under ``base_dir`` matching ``pattern``,
    dropping anything outside the caller's allowed roots.

    Used by the standalone ``web/`` tools' "Browse server" option so their file
    discovery honours the same per-user restrictions as the folder browser. In
    unrestricted mode this behaves like a plain rglob.
    """
    base = Path(base_dir).expanduser()
    if not base.exists() or not base.is_dir():
        return []
    if is_restricted_mode() and not is_path_allowed(base, allow_nonexistent=True):
        return []
    try:
        files = sorted(str(f) for f in base.rglob(pattern) if f.is_file())
    except (OSError, ValueError):
        return []
    if is_restricted_mode():
        files = [f for f in files if is_path_allowed(f)]
    return files


def filter_allowed_paths(paths: Iterable[Union[str, Path]]) -> Tuple[List[str], List[str]]:
    """Split paths into allowed and rejected lists."""
    allowed: List[str] = []
    rejected: List[str] = []
    for raw in paths:
        text = str(raw).strip()
        if not text:
            continue
        if is_path_allowed(text):
            allowed.append(str(Path(text).expanduser().resolve(strict=False)))
        else:
            rejected.append(text)
    return allowed, rejected


def current_user() -> Optional[str]:
    """Return the logged-in username (multi-user mode), else None."""
    return st.session_state.get("nano_user") or None


def is_admin() -> bool:
    """True if the logged-in user is an admin (multi-user mode)."""
    user = current_user()
    if not user:
        return False
    cfg = load_users().get(str(user).strip().lower())
    return bool(cfg and cfg.get("admin"))


def require_authentication() -> None:
    """Gate UI until the user authenticates.

    Two modes:
    * multi-user  — ``NANOORGANIZER_USERS_FILE`` set: username + password login,
      per-user allowed folders.
    * single-pass — the legacy shared ``NANOORGANIZER_PASSWORD_HASH``.
    """
    initialize_security_context()

    if not st.session_state.get("secure_mode"):
        return

    if st.session_state.get("multi_user"):
        _require_user_login()
        return

    expected_hash = os.environ.get(ENV_PASSWORD_HASH, "").strip().lower()
    if not expected_hash:
        st.error("Secure mode is enabled but no password was configured.")
        st.stop()

    if (
        st.session_state.get("nano_auth_ok")
        and st.session_state.get("nano_auth_hash") == expected_hash
    ):
        return

    st.warning("🔒 Password required")
    st.caption(f"Allowed folders: {format_allowed_roots()}")

    with st.form("nanoorganizer_auth_form", clear_on_submit=False):
        password = st.text_input("Password", type="password", key="nano_auth_password")
        submitted = st.form_submit_button("Unlock", type="primary")

    if submitted:
        provided_hash = hash_password(password or "")
        if hmac.compare_digest(provided_hash, expected_hash):
            st.session_state["nano_auth_ok"] = True
            st.session_state["nano_auth_hash"] = expected_hash
            st.session_state["nano_auth_error"] = ""
            st.session_state.pop("nano_auth_password", None)
            st.rerun()
        st.session_state["nano_auth_error"] = "Invalid password."

    if st.session_state.get("nano_auth_error"):
        st.error(st.session_state["nano_auth_error"])

    st.stop()


def _require_user_login() -> None:
    """Username + password gate for multi-user mode."""
    users = load_users()

    # Already authenticated this session and still a valid user? Let through.
    logged = st.session_state.get("nano_user")
    if logged and str(logged).strip().lower() in users:
        return

    st.warning("🔒 Sign in")

    with st.form("nanoorganizer_login_form", clear_on_submit=False):
        username = st.text_input("Username", key="nano_login_user")
        password = st.text_input("Password", type="password", key="nano_login_pass")
        submitted = st.form_submit_button("Sign in", type="primary")

    if submitted:
        key = str(username or "").strip().lower()
        cfg = users.get(key)
        expected = str(cfg.get("password", "")).strip().lower() if cfg else ""
        provided = hash_password(password or "")
        # Always run compare_digest (even when the user is unknown) so response
        # time does not reveal whether a username exists.
        ok = bool(expected) and hmac.compare_digest(provided, expected)
        if ok:
            st.session_state["nano_user"] = key
            st.session_state["nano_login_error"] = ""
            st.session_state.pop("nano_login_pass", None)
            # Recompute allowed roots for the freshly logged-in user.
            initialize_security_context()
            st.rerun()
        st.session_state["nano_login_error"] = "Invalid username or password."

    if st.session_state.get("nano_login_error"):
        st.error(st.session_state["nano_login_error"])

    st.stop()


def logout() -> None:
    """Clear the current multi-user session."""
    for k in ("nano_user", "allowed_roots"):
        st.session_state.pop(k, None)
