#!/usr/bin/env python3
"""
Plugins — how a project package adds itself to pyDataOrg.

pyDataOrg knows how to organise, draw and analyse; it knows nothing about any
particular material, instrument or collaboration. A project package supplies
that, and everything it adds goes through a registry pyDataOrg already reads:

==================  ========================================================
techniques          :func:`pyDataOrg.core.modality.register_modality`
file names          :func:`pyDataOrg.analysis.frames.register_grammar`
record formats      :func:`pyDataOrg.ingest.register_adapter`
analyses            :func:`pyDataOrg.analysis.register_analysis`
campaigns           :func:`pyDataOrg.campaign.register_campaign`
machines            :func:`pyDataOrg.servers.register_server`
optimisers          :func:`pyDataOrg.optimize.register_engine`
GUI pages           a :class:`Plugin`'s :attr:`~Plugin.pages`
==================  ========================================================

Declare the plugin in the package's ``setup.py`` (or ``pyproject.toml``)::

    entry_points={"pyDataOrg.plugins": ["myproj = myproj.plugin:PLUGIN"]}

where ``PLUGIN`` is a :class:`Plugin` (or a function returning one)::

    PLUGIN = Plugin(
        name="myproj", title="My project",
        register=lambda: importlib.import_module("myproj.analyses"),
        pages=[Page("myproj/web/views/overview.py", "Overview", "⚗️",
                    default=True)],
    )

Installed, it is found by :func:`load_plugins` and its ``register`` runs
once. ``dataorg gui --app myproj`` runs it as the app: its title, its pages
first and its default page, then the general pages, all on the same open
organizer. The general ``dataorg gui`` loads no plugin — it is the public
tool, and shows pyDataOrg alone.

A plugin that fails to load is reported (:func:`plugin_errors`, ``dataorg
plugins``), never fatal: one broken package must not take the GUI down.
Set ``PYDATAORG_PLUGINS`` to a comma-separated list to load only those, or
to ``none`` to load none.
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Union

GROUP = "pyDataOrg.plugins"
ENV = "PYDATAORG_PLUGINS"


@dataclass(frozen=True)
class Page:
    """One GUI page a plugin contributes: a Streamlit script.

    *path* is a file, or ``"package.module:relative/file.py"`` to resolve it
    beside an installed module. *url_path* defaults to
    ``<plugin>_<file stem>`` so two plugins' ``overview.py`` cannot collide.
    """

    path: Union[str, Path]
    title: str
    icon: str = ""
    default: bool = False
    url_path: str = ""

    def file(self) -> Path:
        text = str(self.path)
        if ":" in text and not Path(text).exists() and not \
                (len(text) > 1 and text[1] == ":"):
            module, relative = text.split(":", 1)
            import importlib

            found = importlib.import_module(module)
            base = Path(found.__file__).parent if getattr(
                found, "__file__", None) else Path(list(found.__path__)[0])
            return (base / relative).resolve()
        return Path(text).expanduser().resolve()


@dataclass
class Plugin:
    """A project package, as pyDataOrg sees it.

    *register* runs once when the plugin is loaded — import the modules that
    register analyses, campaigns, servers. *on_page* runs on every GUI page
    render before the page itself, **when this plugin is the app**
    (``--app``): open its default organizer, draw its sidebar extras. Keep
    it fast and side-effect free beyond the session.
    """

    name: str
    title: str = ""
    description: str = ""
    version: str = ""
    icon: str = "🧩"
    pages: Sequence[Page] = ()
    register: Optional[Callable[[], object]] = None
    on_page: Optional[Callable[[], object]] = None
    # Defaults the project's own pages read (e.g. which campaign to open).
    defaults: Dict[str, object] = field(default_factory=dict)

    @property
    def heading(self) -> str:
        return self.title or self.name


PLUGINS: Dict[str, Plugin] = {}
ERRORS: Dict[str, str] = {}
_LOADED = False


def register_plugin(plugin: Plugin) -> Plugin:
    """Add a plugin by hand (tests, a notebook) and run its ``register``."""
    if plugin.register is not None:
        plugin.register()
    PLUGINS[plugin.name] = plugin
    ERRORS.pop(plugin.name, None)
    return plugin


def _entry_points():
    from importlib import metadata

    found = metadata.entry_points()
    if hasattr(found, "select"):                     # Python 3.10+
        return list(found.select(group=GROUP))
    return list(found.get(GROUP, []))                # Python 3.9


def _wanted() -> Optional[List[str]]:
    text = os.environ.get(ENV)
    if text is None:
        return None
    text = text.strip()
    if text.lower() in ("", "all"):
        return None
    if text.lower() == "none":
        return []
    return [name.strip() for name in text.split(",") if name.strip()]


def load_plugins(force: bool = False) -> Dict[str, Plugin]:
    """Find, load and register every installed plugin (once per process
    unless *force*). Returns ``{name: Plugin}``; failures go to
    :func:`plugin_errors`."""
    global _LOADED
    if _LOADED and not force:
        return PLUGINS
    wanted = _wanted()
    for entry in _entry_points():
        if wanted is not None and entry.name not in wanted:
            continue
        if entry.name in PLUGINS and not force:
            continue
        try:
            obj = entry.load()
            plugin = obj() if callable(obj) and not isinstance(obj, Plugin) \
                else obj
            if not isinstance(plugin, Plugin):
                raise TypeError(f"{entry.value} is a {type(plugin).__name__}, "
                                f"not a pyDataOrg.plugins.Plugin")
            register_plugin(plugin)
        except Exception as exc:
            ERRORS[entry.name] = (f"{type(exc).__name__}: {exc}\n"
                                  + traceback.format_exc(limit=3))
    _LOADED = True
    return PLUGINS


def plugins() -> List[Plugin]:
    """The loaded plugins (loading them first if need be)."""
    return list(load_plugins().values())


def get_plugin(name: str) -> Plugin:
    load_plugins()
    try:
        return PLUGINS[name]
    except KeyError:
        known = ", ".join(PLUGINS) or "none installed"
        hint = f" (it failed to load: {ERRORS[name].splitlines()[0]})" \
            if name in ERRORS else ""
        raise KeyError(f"no plugin {name!r}{hint}; loaded: {known}") from None


def plugin_errors() -> Dict[str, str]:
    """``{entry point name: what went wrong}`` for plugins that did not load."""
    load_plugins()
    return dict(ERRORS)


def describe() -> str:
    """A plain-text listing — what ``dataorg plugins`` prints."""
    load_plugins()
    lines = []
    for plugin in PLUGINS.values():
        head = f"{plugin.icon} {plugin.name}"
        if plugin.version:
            head += f" {plugin.version}"
        if plugin.title and plugin.title != plugin.name:
            head += f" — {plugin.title}"
        lines.append(head)
        if plugin.description:
            lines.append(f"    {plugin.description}")
        for page in plugin.pages:
            lines.append(f"    page: {page.icon} {page.title}")
    for name, error in ERRORS.items():
        lines.append(f"✗ {name}: {error.splitlines()[0]}")
    return "\n".join(lines) or "no plugins installed"


__all__ = ["GROUP", "Page", "Plugin", "PLUGINS", "register_plugin",
           "load_plugins", "plugins", "get_plugin", "plugin_errors",
           "describe"]
