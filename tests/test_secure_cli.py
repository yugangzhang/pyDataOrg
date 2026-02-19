import hashlib
import os
import sys
from pathlib import Path

import pytest

from NanoOrganizer.web_app import app_cli


def test_main_secure_sets_port_and_security_env(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_launch(port, env=None):
        captured["port"] = port
        captured["env"] = env
        return 0

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_cli, "_launch_streamlit", fake_launch)
    monkeypatch.setattr(sys, "argv", ["viz", "6011", "top-secret"])

    with pytest.raises(SystemExit) as exc:
        app_cli.main_secure()

    assert exc.value.code == 0
    assert captured["port"] == 6011

    env = captured["env"]
    assert env["NANOORGANIZER_SECURE_MODE"] == "1"
    assert env["NANOORGANIZER_USER_MODE"] == "1"
    assert env["NANOORGANIZER_START_DIR"] == str(tmp_path.resolve())
    assert env["NANOORGANIZER_PASSWORD_HASH"] == hashlib.sha256(
        b"top-secret"
    ).hexdigest()

    allowed_roots = env["NANOORGANIZER_ALLOWED_ROOTS"].split(os.pathsep)
    assert str(tmp_path.resolve()) in allowed_roots
    assert str(Path.home().resolve()) in allowed_roots


def test_main_secure_rejects_invalid_port(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["viz", "70000", "pw"])
    with pytest.raises(SystemExit) as exc:
        app_cli.main_secure()
    assert exc.value.code == 2


def test_main_user_sets_restricted_env(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_launch(port, env=None):
        captured["port"] = port
        captured["env"] = env
        return 0

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_cli, "_launch_streamlit", fake_launch)

    with pytest.raises(SystemExit) as exc:
        app_cli.main_user()

    assert exc.value.code == 0
    assert captured["port"] == app_cli.DEFAULT_PORT
    assert captured["env"]["NANOORGANIZER_USER_MODE"] == "1"
    assert captured["env"]["NANOORGANIZER_START_DIR"] == str(tmp_path.resolve())
    assert captured["env"]["NANOORGANIZER_ALLOWED_ROOTS"] == str(tmp_path.resolve())
