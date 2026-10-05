#!/usr/bin/env python3
"""
Machine-local access configuration for the web app.

NanoOrganizer runs in two rather different settings:

* a single-user workstation, where the owner browses their own disks; and
* a shared server, where each account should see only the folders listed for
  it.

This module is the common configuration layer for both: an optional INI file
describing who may log in and which directories each of them may browse. It has
no Streamlit dependency, so the same rules apply to the CLI and the GUI.

The default file is ``~/.config/pyViz.conf``. Set ``NANOORGANIZER_CONFIG`` to
choose another, or keep a project-local ``.config/pyViz.conf``. **Real
configuration files should never be committed** — they contain local paths and
password hashes.

.. note::
   Mapping one dataset onto different mount points on different machines is
   *not* done here. That is what a project's path aliases are for
   (:class:`~NanoOrganizer.core.pathmap.PathResolver`), and they travel with
   the project instead of with the machine.

Example
-------

.. code-block:: ini

    [application]
    access_mode = user
    start_dir = /data/projects

    [users]
    alice = admin
    bob = user

    [user:bob]
    password_hash = 9f86d0818882...
    roots =
        /data/projects/bob
        /scratch/bob
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ENV_CONFIG = "NANOORGANIZER_CONFIG"
ENV_MODE = "NANOORGANIZER_MODE"
ENV_START_DIR = "NANOORGANIZER_START_DIR"

DEFAULT_CONFIG_NAME = "pyViz.conf"

#: ``local`` trusts whoever is at the keyboard; ``user`` and ``admin`` require
#: a login, and ``admin`` grants the whole filesystem the process can read.
ACCESS_MODES = {"admin", "user", "local"}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _split_paths(value: object) -> Tuple[str, ...]:
    """Split a path list on the platform separator, newlines, or ``;``.

    ``;`` is accepted everywhere as a convenience for configuration files
    shared between Windows and Unix. Commas are intentionally *not* separators,
    because a comma is a valid filename character.
    """
    text = _clean(value)
    if not text:
        return ()
    values = [text]
    for separator in (os.pathsep, "\n", ";"):
        next_values: List[str] = []
        for item in values:
            next_values.extend(item.split(separator))
        values = next_values
    return tuple(item.strip() for item in values if item.strip())


def _bool(value: object, default: bool = False) -> bool:
    text = _clean(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on", "y"}


def _hash_like(value: object) -> str:
    """Return a stored password hash, accepting the legacy ``password`` key."""
    return _clean(value).lower()


def normalize_access_mode(value: object, default: str = "local") -> str:
    text = _clean(value).lower()
    return text if text in ACCESS_MODES else default


def _expand(value: str, *, username: str = "") -> str:
    """Expand ``{username}`` and ``~`` in a configured path."""
    text = _clean(value)
    if not text:
        return ""
    if "{username}" in text:
        text = text.replace("{username}", username)
    return os.path.expanduser(text)


@dataclass
class UserAccess:
    """One account: how it authenticates and what it may browse."""

    username: str
    password_hash: str = ""
    is_admin: bool = False
    all_paths: bool = False
    roots: Tuple[str, ...] = ()

    def allowed_roots(self) -> Tuple[str, ...]:
        """Directories this account may browse.

        An admin with ``all_paths`` gets ``/`` deliberately: the point of an
        admin account is to reach data mounts outside ``$HOME``. The operating
        system remains the real boundary.
        """
        if self.is_admin and self.all_paths:
            return ("/",)
        return self.roots


@dataclass
class AccessConfig:
    """Parsed configuration with normalized, application-facing values."""

    path: Optional[Path] = None
    access_mode: str = "local"
    start_dir: str = ""
    default_path: str = ""
    extra_roots: Tuple[str, ...] = ()
    users: Mapping[str, UserAccess] = field(default_factory=dict)

    @property
    def requires_authentication(self) -> bool:
        return self.access_mode in {"admin", "user"} or bool(self.users)

    def user(self, username: str) -> Optional[UserAccess]:
        return self.users.get(_clean(username).lower())

    def roots_for(self, username: str) -> Tuple[str, ...]:
        """Allowed roots for *username*, or an empty tuple if unknown."""
        account = self.user(username)
        return account.allowed_roots() if account else ()


def discover_config_path() -> Optional[Path]:
    """Find the configuration file without creating one."""
    candidates: List[Path] = []
    explicit = _clean(os.environ.get(ENV_CONFIG))
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(Path.cwd() / ".config" / DEFAULT_CONFIG_NAME)
    candidates.append(Path.home() / ".config" / DEFAULT_CONFIG_NAME)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _section(parser: configparser.ConfigParser, *names: str):
    for name in names:
        if parser.has_section(name):
            return parser[name]
    return None


def _path_values(section, *keys: str) -> Tuple[str, ...]:
    if section is None:
        return ()
    for key in keys:
        if key in section:
            return _split_paths(section[key])
    return ()


def _user_from_section(username: str, section, *, admin: bool = False,
                       ) -> UserAccess:
    if section is None:
        return UserAccess(username=username, is_admin=admin, all_paths=admin)

    is_admin = _bool(section.get("admin"), admin)
    roots = tuple(
        _expand(value, username=username)
        for value in _path_values(section, "roots", "paths", "allowed_roots")
    )
    return UserAccess(
        username=username,
        password_hash=_hash_like(section.get("password_hash")
                                 or section.get("password")),
        is_admin=is_admin,
        all_paths=_bool(section.get("all_paths"), is_admin and not roots),
        roots=roots,
    )


def _parse_users(parser: configparser.ConfigParser) -> Dict[str, UserAccess]:
    """Read the account sections.

    Three forms are accepted, because configuration files outlive the code
    that reads them:

    * ``[admin]`` with a ``username`` key — a single privileged account;
    * ``[users]`` mapping name to role;
    * ``[user:<name>]`` for that account's password and roots.
    """
    users: Dict[str, UserAccess] = {}

    admin_section = _section(parser, "admin", "owner")
    if admin_section is not None:
        name = _clean(admin_section.get("username")).lower()
        if name:
            users[name] = _user_from_section(name, admin_section, admin=True)

    listing = _section(parser, "users", "accounts")
    if listing is not None:
        for name, role in listing.items():
            key = _clean(name).lower()
            if not key:
                continue
            users[key] = UserAccess(
                username=key,
                is_admin=_clean(role).lower() in {"admin", "administrator"},
                all_paths=_clean(role).lower() in {"admin", "administrator"},
            )

    for section_name in parser.sections():
        if not section_name.lower().startswith("user:"):
            continue
        key = section_name.split(":", 1)[1].strip().lower()
        if not key:
            continue
        previous = users.get(key)
        account = _user_from_section(
            key, parser[section_name],
            admin=previous.is_admin if previous else False)
        if previous is not None and not account.roots:
            account.roots = previous.roots
        users[key] = account

    return users


def load_access_config(path: Optional[os.PathLike] = None) -> AccessConfig:
    """Read the configuration file, or return defaults when there is none."""
    config_path = Path(path).expanduser() if path else discover_config_path()
    if config_path is None or not Path(config_path).is_file():
        return AccessConfig(
            access_mode=normalize_access_mode(os.environ.get(ENV_MODE)),
            start_dir=_clean(os.environ.get(ENV_START_DIR)),
        )

    parser = configparser.ConfigParser()
    # Keys are paths and usernames; lower-casing them would be wrong.
    parser.optionxform = str
    parser.read(config_path, encoding="utf-8")

    application = _section(parser, "application", "app", "general")
    access_mode = normalize_access_mode(
        os.environ.get(ENV_MODE)
        or (application.get("access_mode") if application else ""),
    )
    start_dir = _expand(
        _clean(os.environ.get(ENV_START_DIR))
        or (application.get("start_dir") if application else "")
    )
    default_path = _expand(application.get("default_path", "")
                           if application else "")
    extra_roots = tuple(
        _expand(value)
        for value in _path_values(_section(parser, "paths", "roots"),
                                  "extra_roots", "roots", "data_roots")
    )

    return AccessConfig(
        path=Path(config_path),
        access_mode=access_mode,
        start_dir=start_dir,
        default_path=default_path,
        extra_roots=extra_roots,
        users=_parse_users(parser),
    )


def config_users(path: Optional[os.PathLike] = None) -> Dict[str, dict]:
    """Accounts as plain dicts, in the shape the web app's user store uses."""
    config = load_access_config(path)
    return {
        name: {
            "password_hash": account.password_hash,
            "admin": account.is_admin,
            "all_paths": account.all_paths,
            "roots": list(account.roots),
        }
        for name, account in config.users.items()
    }


def configured_start_dir(path: Optional[os.PathLike] = None,
                         default: str = "") -> str:
    return load_access_config(path).start_dir or default


def configured_extra_roots(path: Optional[os.PathLike] = None) -> Tuple[str, ...]:
    """Additional data roots named in the configuration file.

    A private configuration may point at a mount the public package cannot
    know about; this is how it reaches the allow-list.
    """
    return load_access_config(path).extra_roots


__all__ = [
    "AccessConfig", "UserAccess", "ACCESS_MODES",
    "ENV_CONFIG", "ENV_MODE", "ENV_START_DIR", "DEFAULT_CONFIG_NAME",
    "load_access_config", "discover_config_path", "config_users",
    "configured_start_dir", "configured_extra_roots", "normalize_access_mode",
]
