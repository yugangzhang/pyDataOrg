#!/usr/bin/env python3
"""
Where recorded data lives on each machine — one :class:`Server` per machine.

An instrument records every path the way *it* sees it::

    /instrument/share/spectra/DEV001/2026-09-21/run_a/*.csv

On an analysis workstation the same tree is mounted somewhere else, say
``/mnt/lab/spectra``. A :class:`Server` is just that: for each prefix the
records carry, the folder it sits under on one machine. ::

    from pyDataOrg.servers import Server, register_server, server

    register_server(Server("workstation", {
        "/instrument/share": "/mnt/lab",
    }))
    here = server("workstation")
    here.local("/instrument/share/spectra/DEV001/run_a/*.csv")
    # '/mnt/lab/spectra/DEV001/run_a/*.csv'

    org = Organizer("project.json", server="workstation")   # aliases applied

``server()`` (no name) is the recording machine's own view: paths unchanged.
``server("auto")`` is the first registered server whose folders are mounted
here. Add a machine by registering a server — never rewrite the records.

A project package registers its machines on import, so its users only ever
type the machine's name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Union

#: ``server()`` with no name: recorded paths as they are.
RECORDED = "recorded"
#: The first registered server whose folders exist here.
AUTO = "auto"


@dataclass(frozen=True)
class Server:
    """One machine, and where each recorded tree is mounted on it.

    *prefixes* maps ``{prefix the records carry: the same folder here}``.
    """

    name: str
    prefixes: Mapping[str, str] = field(default_factory=dict)
    description: str = ""

    def aliases(self) -> Dict[str, str]:
        """Only the prefixes that differ here — what an Organizer needs."""
        return {recorded: local for recorded, local in self.prefixes.items()
                if recorded.rstrip("/") != local.rstrip("/")}

    def local(self, path) -> str:
        """*path* as it was recorded → the same path on this machine.

        A path under none of the prefixes comes back unchanged. Globs are
        fine: only the prefix is swapped. The longest matching prefix wins.
        """
        text = str(path)
        for recorded in sorted(self.prefixes, key=len, reverse=True):
            head = recorded.rstrip("/")
            if text == head or text.startswith(head + "/"):
                return self.prefixes[recorded].rstrip("/") + text[len(head):]
        return text

    def mounted(self) -> bool:
        """Whether every local folder of this server is reachable from here
        (a server with no prefixes is always 'mounted')."""
        return all(Path(local).expanduser().is_dir()
                   for local in self.prefixes.values())


SERVERS: Dict[str, Server] = {RECORDED: Server(RECORDED)}


def register_server(entry: Server, overwrite: bool = True) -> Server:
    """Add (or replace) a machine. Returns it."""
    if entry.name in (RECORDED, AUTO):
        raise ValueError(f"{entry.name!r} is reserved")
    if entry.name in SERVERS and not overwrite:
        raise KeyError(f"server {entry.name!r} is already registered")
    SERVERS[entry.name] = entry
    return entry


def list_servers() -> List[str]:
    """Registered machine names, the recorded view first."""
    return list(SERVERS)


def server(name: Union[str, Server, None] = None) -> Server:
    """The :class:`Server` called *name*.

    ``None``/``"recorded"`` is the recording machine's own view;
    ``"auto"`` is the first registered server (other than that view) whose
    folders are all mounted here, else the recorded view.
    """
    if isinstance(name, Server):
        return name
    if not name or name == RECORDED:
        return SERVERS[RECORDED]
    if name == AUTO:
        return next((s for key, s in SERVERS.items()
                     if key != RECORDED and s.prefixes and s.mounted()),
                    SERVERS[RECORDED])
    try:
        return SERVERS[name]
    except KeyError:
        raise KeyError(f"unknown server {name!r}; known: "
                       f"{', '.join(SERVERS)} (or 'auto'). Register one with "
                       f"pyDataOrg.servers.register_server().") from None


__all__ = ["Server", "SERVERS", "RECORDED", "AUTO", "register_server",
           "list_servers", "server"]
