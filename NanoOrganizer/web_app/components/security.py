#!/usr/bin/env python3
"""Security and access-control helpers for the Streamlit web app."""

import hashlib
import hmac
import os
from pathlib import Path
from typing import Iterable, List, Tuple, Union

import streamlit as st


ENV_SECURE_MODE = "NANOORGANIZER_SECURE_MODE"
ENV_USER_MODE = "NANOORGANIZER_USER_MODE"
ENV_START_DIR = "NANOORGANIZER_START_DIR"
ENV_ALLOWED_ROOTS = "NANOORGANIZER_ALLOWED_ROOTS"
ENV_PASSWORD_HASH = "NANOORGANIZER_PASSWORD_HASH"


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


def initialize_security_context() -> None:
    """Initialize security-related session keys from environment variables."""
    secure_mode = _env_flag(ENV_SECURE_MODE)
    user_mode = _env_flag(ENV_USER_MODE)

    start_dir = Path(
        os.environ.get(ENV_START_DIR, str(Path.cwd()))
    ).expanduser().resolve(strict=False)

    if secure_mode:
        raw_roots = os.environ.get(ENV_ALLOWED_ROOTS, "")
        env_roots = [p for p in raw_roots.split(os.pathsep) if p.strip()]
        allowed_roots = _normalize_roots(env_roots or [start_dir])
        # Keep legacy pages in restricted behavior while secure mode is active.
        user_mode = True
    elif user_mode:
        allowed_roots = [start_dir]
    else:
        allowed_roots = []

    st.session_state["secure_mode"] = secure_mode
    st.session_state["user_mode"] = user_mode
    st.session_state["user_start_dir"] = str(start_dir)
    st.session_state["allowed_roots"] = [str(p) for p in allowed_roots]


def is_restricted_mode() -> bool:
    """True when path restrictions should be enforced."""
    initialize_security_context()
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


def require_authentication() -> None:
    """Gate UI until the configured secure-mode password is entered."""
    initialize_security_context()

    if not st.session_state.get("secure_mode"):
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
