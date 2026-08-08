"""Machine-local access and data-location configuration.

NanoOrganizer is used in two rather different settings:

* a trusted beamline workstation, where the owner may need to browse several
  data trees; and
* a public/local install, where each person should see only the folders listed
  for their account.

The web application historically configured these details through a mixture
of environment variables and a JSON user file.  This module adds one small,
optional INI file as the common configuration layer.  It deliberately has no
Streamlit dependency, so the same path rules can be used by the CLI, the
beamline-path helpers, and the GUI.

The default file is ``~/.config/pyViz.conf``.  Set
``NANOORGANIZER_CONFIG=/path/to/pyViz.conf`` to choose another file.  A project
local ``.config/pyViz.conf`` is also accepted, which is useful for a private
beamline checkout.  Real configuration files should never be committed: they
contain local paths and password hashes.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


ENV_CONFIG = "NANOORGANIZER_CONFIG"
ENV_MODE = "NANOORGANIZER_MODE"
ENV_SITE = "NANOORGANIZER_SITE"
ENV_BEAMLINE = "NANOORGANIZER_BEAMLINE"
ENV_START_DIR = "NANOORGANIZER_START_DIR"

DEFAULT_CONFIG_NAME = "pyViz.conf"
DEFAULT_BEAMLINE = "smi"

SITE_ALIASES = {
    "onsite": "onsite",
    "on_beamline": "onsite",
    "on-beamline": "onsite",
    "beamline": "onsite",
    "offsite": "offsite",
    "off_beamline": "offsite",
    "off-beamline": "offsite",
    "offbeamline": "offsite",
}

ACCESS_MODES = {"admin", "user", "local"}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _split_paths(value: object) -> Tuple[str, ...]:
    """Split a path list using the platform separator and newlines.

    ``;`` is accepted on every platform as a convenience for config files
    shared between Windows and Unix.  Commas are intentionally not treated as
    separators because a comma is a valid filename character.
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


def normalize_site(value: object, default: str = "auto") -> str:
    text = _clean(value).lower().replace(" ", "_")
    if not text or text == "auto":
        return default
    return SITE_ALIASES.get(text, default)


def normalize_access_mode(value: object, default: str = "local") -> str:
    text = _clean(value).lower().replace(" ", "_")
    return text if text in ACCESS_MODES else default


def _format_path(value: str, *, beamline: str, site: str,
                 username: str = "") -> str:
    """Expand a config path without requiring that it exists yet."""
    text = value.strip()
    try:
        text = text.format(beamline=beamline, site=site, username=username)
    except (KeyError, ValueError):
        # A typo in a template should not make the whole app fail to start;
        # it remains visible in the UI and will simply fail the path check.
        pass
    return str(Path(text).expanduser())


@dataclass(frozen=True)
class UserAccess:
    """One login and its filesystem scope."""

    username: str
    password_hash: str = ""
    roots: Tuple[str, ...] = ()
    site_roots: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    admin: bool = False
    all_paths: bool = False

    def roots_for(self, site: str = "auto") -> Tuple[str, ...]:
        if self.admin and self.all_paths:
            # ``/`` is converted to a resolved root by the security layer and
            # gives the admin the same access as the old admin JSON entry.
            return ("/",)
        selected = list(self.roots)
        selected.extend(self.site_roots.get(normalize_site(site), ()))
        return tuple(selected)


@dataclass(frozen=True)
class AccessConfig:
    """Parsed configuration with normalized, application-facing values."""

    path: Optional[Path] = None
    access_mode: str = "local"
    site: str = "auto"
    beamline: str = DEFAULT_BEAMLINE
    start_dir: str = ""
    default_path: str = ""
    path_templates: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    users: Mapping[str, UserAccess] = field(default_factory=dict)

    @property
    def requires_authentication(self) -> bool:
        return self.access_mode in {"admin", "user"} or bool(self.users)

    def roots_for(self, username: str, site: Optional[str] = None) -> Tuple[str, ...]:
        key = _clean(username).lower()
        user = self.users.get(key)
        return user.roots_for(site or self.site) if user else ()

    def roots_for_site(self, site: str, beamline: Optional[str] = None) -> Tuple[str, ...]:
        """Return configured data roots for a site/beamline pair."""
        bl = _clean(beamline).lower() or self.beamline
        key = normalize_site(site)
        return tuple(_format_path(p, beamline=bl, site=key) for p in
                     self.path_templates.get(key, ()))


def discover_config_path() -> Optional[Path]:
    """Find the configured pyViz file without creating one."""
    candidates: List[Path] = []
    explicit = _clean(os.environ.get(ENV_CONFIG))
    if explicit:
        candidates.append(Path(explicit).expanduser())
    # Project-local config wins over the user's default when launching from a
    # private checkout.  This is also convenient for beamline-specific setups.
    candidates.append(Path.cwd() / ".config" / DEFAULT_CONFIG_NAME)
    candidates.append(Path.home() / ".config" / DEFAULT_CONFIG_NAME)
    candidates.append(Path.home() / ".config" / "pyviz.conf")

    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve(strict=False)
        if str(candidate) in seen:
            continue
        seen.add(str(candidate))
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
    values: List[str] = []
    for key in keys:
        if key in section:
            values.extend(_split_paths(section.get(key, "")))
    return tuple(values)


def _user_from_section(username: str, section, *, admin: bool = False,
                       all_paths: bool = False) -> UserAccess:
    generic = _path_values(section, "paths", "roots", "folders")
    site_roots: Dict[str, Tuple[str, ...]] = {}
    for site, keys in {
        "onsite": ("beamline_paths", "on_beamline_paths", "onsite_paths"),
        "offsite": ("off_beamline_paths", "offsite_paths", "offbeamline_paths"),
    }.items():
        values = _path_values(section, *keys)
        if values:
            site_roots[site] = values
    password_hash = ""
    if section is not None:
        password_hash = _hash_like(section.get("password_hash", ""))
        if not password_hash:
            password_hash = _hash_like(section.get("password", ""))
    return UserAccess(
        username=_clean(username).lower(),
        password_hash=password_hash,
        roots=generic,
        site_roots=site_roots,
        admin=admin,
        all_paths=all_paths,
    )


def _parse_users(parser: configparser.ConfigParser) -> Dict[str, UserAccess]:
    users: Dict[str, UserAccess] = {}

    admin_section = _section(parser, "admin", "administrator")
    if admin_section is not None:
        username = _clean(admin_section.get("username", "yuzhang")).lower()
        users[username] = _user_from_section(
            username,
            admin_section,
            admin=True,
            all_paths=_bool(admin_section.get("all_paths", "true"), True),
        )

    # Compact form for the requested ``{user1: [path1, path2]}`` model:
    # [users]
    # alice = /data/alice:/data/shared
    simple = _section(parser, "users")
    if simple is not None:
        for username, value in simple.items():
            key = username.strip().lower()
            if key in {"admin", "administrator"}:
                continue
            # The compact mapping is intentionally friendly to the notation
            # people tend to write first: ``alice = /one, /two``.
            users[key] = UserAccess(
                username=key,
                roots=_split_paths(str(value).replace(",", os.pathsep)),
            )

    # Extended form adds a password and/or separate roots for each site:
    # [user.alice] or [users.alice]
    for name in parser.sections():
        lower = name.lower()
        prefix = ""
        if lower.startswith("user."):
            prefix = "user."
        elif lower.startswith("users."):
            prefix = "users."
        elif lower.startswith("user:"):
            prefix = "user:"
        if not prefix:
            continue
        username = name[len(prefix):].strip().lower()
        if not username:
            continue
        parsed = _user_from_section(username, parser[name])
        previous = users.get(username)
        if previous is not None:
            # Permit the compact path mapping and the extended credential
            # section to be used together:
            # [users] alice = /data/alice
            # [user.alice] password_hash = ...
            merged_sites = dict(previous.site_roots)
            merged_sites.update(parsed.site_roots)
            parsed = UserAccess(
                username=username,
                password_hash=parsed.password_hash or previous.password_hash,
                roots=parsed.roots or previous.roots,
                site_roots=merged_sites,
                admin=parsed.admin or previous.admin,
                all_paths=parsed.all_paths or previous.all_paths,
            )
        users[username] = parsed

    return users


def load_access_config(path: Optional[os.PathLike] = None) -> AccessConfig:
    """Load a pyViz config, returning safe defaults when it is absent.

    This function intentionally treats malformed files as an empty config.
    Authentication must not become an accidental denial-of-service merely
    because an optional local configuration was edited incorrectly; the GUI
    still reports the selected config path so the problem is discoverable.
    """
    config_path = Path(path).expanduser() if path is not None else discover_config_path()
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str.lower
    if config_path is not None:
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                parser.read_file(handle)
        except (OSError, configparser.Error):
            return AccessConfig(path=config_path.resolve(strict=False))

    application = _section(parser, "application", "app")
    paths = _section(parser, "paths", "data")

    configured_mode = ""
    configured_site = ""
    configured_beamline = ""
    configured_start = ""
    configured_default = ""
    if application is not None:
        configured_mode = _clean(application.get("access_mode", ""))
        if not configured_mode:
            # ``mode = admin`` is a convenient shorthand.  Site names in this
            # field remain location settings, not access settings.
            candidate = _clean(application.get("mode", ""))
            if candidate.lower() in ACCESS_MODES:
                configured_mode = candidate
        configured_site = _clean(application.get("site", ""))
        configured_beamline = _clean(application.get("beamline", ""))
        configured_start = _clean(application.get("start_dir", ""))
        configured_default = _clean(application.get("default_path", ""))

    env_mode = _clean(os.environ.get(ENV_MODE))
    access_mode = normalize_access_mode(env_mode or configured_mode, "local")
    env_site = _clean(os.environ.get(ENV_SITE))
    site_candidate = env_site or configured_site
    if not site_candidate and env_mode.lower() in SITE_ALIASES:
        site_candidate = env_mode
    if not site_candidate and application is not None:
        shorthand = _clean(application.get("mode", ""))
        site_candidate = shorthand if shorthand.lower() in SITE_ALIASES else ""
    site = normalize_site(site_candidate, "auto")
    beamline = (_clean(os.environ.get(ENV_BEAMLINE)) or
                configured_beamline or DEFAULT_BEAMLINE).lower()

    path_templates: Dict[str, Tuple[str, ...]] = {}
    if paths is not None:
        path_templates["onsite"] = _path_values(
            paths, "on_beamline", "onsite", "beamline", "beamline_root",
        )
        path_templates["offsite"] = _path_values(
            paths, "off_beamline", "offsite", "offbeamline", "offsite_root",
        )
    path_templates = {k: v for k, v in path_templates.items() if v}

    users = _parse_users(parser)

    env_start = _clean(os.environ.get(ENV_START_DIR))
    start_dir = env_start or configured_start or configured_default
    if start_dir:
        start_dir = _format_path(start_dir, beamline=beamline, site=site)
    if configured_default:
        configured_default = _format_path(
            configured_default, beamline=beamline, site=site)

    return AccessConfig(
        path=config_path.resolve(strict=False) if config_path is not None else None,
        access_mode=access_mode,
        site=site,
        beamline=beamline,
        start_dir=start_dir,
        default_path=configured_default,
        path_templates=path_templates,
        users=users,
    )


def config_users(path: Optional[os.PathLike] = None) -> Dict[str, dict]:
    """Return config users in the legacy JSON-like shape used by the GUI."""
    config = load_access_config(path)
    return {
        name: {
            "password": user.password_hash,
            "roots": list(user.roots),
            "site_roots": {key: list(value)
                           for key, value in user.site_roots.items()},
            "admin": user.admin,
            "all_paths": user.all_paths,
        }
        for name, user in config.users.items()
    }


def configured_site(path: Optional[os.PathLike] = None) -> str:
    return load_access_config(path).site


def configured_beamline(path: Optional[os.PathLike] = None) -> str:
    return load_access_config(path).beamline


def configured_start_dir(path: Optional[os.PathLike] = None,
                         default: str = "") -> str:
    value = load_access_config(path).start_dir
    return value or default


def configured_path_templates(site: str, beamline: str = DEFAULT_BEAMLINE,
                              path: Optional[os.PathLike] = None) -> Tuple[str, ...]:
    config = load_access_config(path)
    return config.roots_for_site(site, beamline)
