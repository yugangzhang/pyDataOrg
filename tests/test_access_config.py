"""Tests for the multi-user access configuration and the path allow-list."""

import hashlib
from pathlib import Path

import streamlit as st

from NanoOrganizer.core.access_config import (
    config_users, configured_extra_roots, configured_start_dir,
    load_access_config,
)
from NanoOrganizer.web_app.components.security import (
    initialize_security_context, is_path_allowed,
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write(tmp_path, body: str) -> Path:
    path = tmp_path / "pyViz.conf"
    path.write_text(body)
    return path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_missing_config_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.delenv("NANOORGANIZER_CONFIG", raising=False)
    monkeypatch.delenv("NANOORGANIZER_MODE", raising=False)
    monkeypatch.delenv("NANOORGANIZER_START_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    config = load_access_config()
    assert config.access_mode == "local"
    assert config.users == {}
    assert config.requires_authentication is False


def test_users_and_roles_parse(tmp_path):
    path = _write(tmp_path, f"""
[application]
access_mode = user
start_dir = {tmp_path}/projects

[users]
alice = admin
bob = user

[user:bob]
password_hash = {_sha256("hunter2")}
roots =
    {tmp_path}/projects/bob
    {tmp_path}/scratch
""")
    config = load_access_config(path)

    assert config.access_mode == "user"
    assert config.requires_authentication is True
    assert set(config.users) == {"alice", "bob"}

    alice = config.user("alice")
    assert alice.is_admin and alice.allowed_roots() == ("/",)

    bob = config.user("bob")
    assert not bob.is_admin
    assert bob.password_hash == _sha256("hunter2")
    assert len(bob.allowed_roots()) == 2


def test_username_placeholder_expands(tmp_path):
    path = _write(tmp_path, """
[users]
carol = user

[user:carol]
roots = /data/{username}/projects
""")
    assert load_access_config(path).roots_for("carol") == \
        ("/data/carol/projects",)


def test_roots_accept_several_separators(tmp_path):
    path = _write(tmp_path, """
[users]
dave = user

[user:dave]
roots = /a;/b
""")
    assert load_access_config(path).roots_for("dave") == ("/a", "/b")


def test_admin_with_explicit_roots_is_not_given_everything(tmp_path):
    """Listing roots for an admin means they meant to scope it."""
    path = _write(tmp_path, """
[users]
erin = admin

[user:erin]
roots = /data/erin
""")
    assert load_access_config(path).roots_for("erin") == ("/data/erin",)


def test_extra_roots_are_read(tmp_path):
    path = _write(tmp_path, f"""
[paths]
extra_roots =
    {tmp_path}/mount_a
    {tmp_path}/mount_b
""")
    assert len(configured_extra_roots(path)) == 2
    assert configured_start_dir(path, default="fallback") == "fallback"


def test_config_users_exports_the_web_app_shape(tmp_path):
    path = _write(tmp_path, f"""
[users]
frank = user

[user:frank]
password_hash = {_sha256("pw")}
roots = /data/frank
""")
    users = config_users(path)
    assert users["frank"]["password_hash"] == _sha256("pw")
    assert users["frank"]["admin"] is False
    assert users["frank"]["roots"] == ["/data/frank"]


def test_environment_overrides_the_file(tmp_path, monkeypatch):
    path = _write(tmp_path, "[application]\naccess_mode = local\n")
    monkeypatch.setenv("NANOORGANIZER_MODE", "admin")
    assert load_access_config(path).access_mode == "admin"


# ---------------------------------------------------------------------------
# The allow-list the GUI enforces
# ---------------------------------------------------------------------------

def test_allowed_roots_fence_the_browser(tmp_path, monkeypatch):
    inside = tmp_path / "allowed" / "sub"
    inside.mkdir(parents=True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    st.session_state.clear()
    monkeypatch.setenv("NANOORGANIZER_USER_MODE", "1")
    monkeypatch.setenv("NANOORGANIZER_ALLOWED_ROOTS", str(tmp_path / "allowed"))
    monkeypatch.setenv("NANOORGANIZER_START_DIR", str(tmp_path / "allowed"))
    monkeypatch.delenv("NANOORGANIZER_CONFIG", raising=False)
    monkeypatch.delenv("NANOORGANIZER_USERS_FILE", raising=False)

    initialize_security_context()

    assert is_path_allowed(inside)
    assert not is_path_allowed(outside)
    st.session_state.clear()
