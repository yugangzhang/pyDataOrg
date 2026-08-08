import hashlib
from pathlib import Path

import streamlit as st

from NanoOrganizer.core.access_config import load_access_config
from NanoOrganizer.core.beamline_paths import candidate_roots, swap_site
from NanoOrganizer.web_app.components.security import (
    initialize_security_context,
    is_path_allowed,
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_ini_config_parses_admin_users_and_site_paths(tmp_path, monkeypatch):
    config_path = tmp_path / "pyViz.conf"
    config_path.write_text(
        """
[application]
access_mode = user
site = off_beamline
beamline = smi
start_dir = {root}/beamline_a_remote/2026-2/pass-000000/projects/microbeam_Kim/Results

[paths]
off_beamline = {root}/{{beamline}}_remote
on_beamline = /beamline/{{beamline}}/proposals

[admin]
username = yuzhang
password_hash = {admin_hash}
all_paths = true

[users]
compact = {root}/compact, {root}/shared

[user.alice]
password_hash = {alice_hash}
paths = {root}/alice
off_beamline_paths = {root}/alice-off
beamline_paths = /beamline/alice
""".format(
            root=tmp_path,
            admin_hash=_sha256("admin-pass"),
            alice_hash=_sha256("alice-pass"),
        ),
        encoding="utf-8",
    )

    config = load_access_config(config_path)

    assert config.access_mode == "user"
    assert config.site == "offsite"
    assert config.beamline == "smi"
    assert config.start_dir.endswith("microbeam_Kim/Results")
    assert config.users["yuzhang"].admin is True
    assert config.users["yuzhang"].all_paths is True
    assert config.users["alice"].password_hash == _sha256("alice-pass")
    assert config.users["alice"].roots_for("offsite")[-1].endswith("alice-off")
    assert config.users["compact"].roots == (
        str(tmp_path / "compact"), str(tmp_path / "shared")
    )


def test_configured_off_beamline_root_and_site_swap(tmp_path, monkeypatch):
    off_root = tmp_path / "off" / "beamline_a_remote"
    on_root = tmp_path / "on" / "smi" / "proposals"
    suffix = Path("2026-2/pass-000000/projects/microbeam_Kim/Results")
    (off_root / suffix).mkdir(parents=True)
    (on_root / suffix).mkdir(parents=True)
    config_path = tmp_path / "pyViz.conf"
    config_path.write_text(
        """[paths]
off_beamline = {off}/{{beamline}}_remote
on_beamline = {on}/{{beamline}}/proposals
""".format(off=tmp_path / "off", on=tmp_path / "on"),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOORGANIZER_CONFIG", str(config_path))

    roots = candidate_roots("offsite", "smi")
    assert roots[0] == off_root
    assert roots[0].is_dir()

    off_path = off_root / suffix
    assert swap_site(off_path, "onsite") == on_root / suffix


def test_user_mode_allows_only_configured_user_roots(tmp_path, monkeypatch):
    allowed = tmp_path / "alice"
    outside = tmp_path / "private"
    allowed.mkdir()
    outside.mkdir()
    config_path = tmp_path / "pyViz.conf"
    config_path.write_text(
        """[application]
access_mode = user

[user.alice]
password_hash = {password}
paths = {allowed}
""".format(password=_sha256("alice-pass"), allowed=allowed),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOORGANIZER_CONFIG", str(config_path))
    st.session_state.clear()

    initialize_security_context()
    assert st.session_state["multi_user"] is True
    assert is_path_allowed(allowed) is False  # no user before login

    st.session_state["nano_user"] = "alice"
    initialize_security_context()
    assert is_path_allowed(allowed) is True
    assert is_path_allowed(allowed / "nested", allow_nonexistent=True) is True
    assert is_path_allowed(outside) is False


def test_admin_user_gets_full_filesystem_scope(tmp_path, monkeypatch):
    config_path = tmp_path / "pyViz.conf"
    config_path.write_text(
        """[application]
access_mode = admin

[admin]
username = yuzhang
password_hash = {password}
all_paths = true
""".format(password=_sha256("admin-pass")),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOORGANIZER_CONFIG", str(config_path))
    st.session_state.clear()
    st.session_state["nano_user"] = "yuzhang"

    initialize_security_context()

    assert st.session_state["access_mode"] == "admin"
    assert Path("/") in [Path(root) for root in st.session_state["allowed_roots"]]
    assert is_path_allowed(tmp_path) is True
