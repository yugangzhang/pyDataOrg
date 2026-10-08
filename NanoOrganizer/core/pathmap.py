#!/usr/bin/env python3
"""
PathResolver – make paths written on one machine resolvable on another.

Metadata produced at the instrument records absolute paths such as
``/instrument/share/spectra/DEV001/2026-09-21/<run>/``.
On an analysis workstation that prefix may be mounted somewhere else, or not
mounted at all.  Rewriting the metadata would make it machine-specific, so the
records are kept verbatim and resolution happens here, per machine.

An *alias* maps one recorded prefix to an ordered list of local candidates::

    PathResolver([("/instrument/share", ["/mnt/instrument"])])

Resolution order for a recorded path:

1. the path itself, if it exists;
2. each alias whose prefix matches, in order, first existing candidate wins;
3. give up – and say so, rather than raising.

A **relative** recorded path is relative to the resolver's *base* — the
project root, which for an :class:`~NanoOrganizer.Organizer` is the folder its
JSON file sits in — never to wherever the process happens to be running.
Recording paths that way is what makes an organizer and its data portable as
one folder: move it, zip it, open it on another machine, and nothing needs an
alias. :func:`display_path` is the matching half for showing a location to a
person: relative to where they are, not as an absolute path that names
somebody's home directory.

A path that cannot be resolved is not an error.  Browsing metadata for data
that is not currently mounted is a normal, supported state; callers use
:meth:`PathResolver.status` to show that in the interface.
"""

from __future__ import annotations

import glob as _glob
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Status values returned by :meth:`PathResolver.status`
LOCAL = "local"        # the recorded path exists as written
ALIASED = "aliased"    # found through an alias
MISSING = "missing"    # not found anywhere


def is_relative(path: object) -> bool:
    """True for a recorded path that is relative: not ``/…``, ``~…`` or ``C:…``."""
    text = _normalise(path)
    if not text:
        return False
    return not (text.startswith("/") or text.startswith("~")
                or (len(text) > 1 and text[1] == ":"))


def display_path(path: object, start: object = None, max_up: int = 3) -> str:
    """A location as a person should see it: relative to where they are.

    ``/home/you/Repos/OrgDemo/CuAu`` seen from ``/home/you/Repos/NanoOrganizer``
    is ``../OrgDemo/CuAu``. Relative to *start* (the working directory by
    default) when that takes at most *max_up* ``..`` steps; otherwise under
    ``~`` when inside the home directory; otherwise as given. A relative path
    is returned unchanged — it already says where it is relative to.
    """
    text = _normalise(path)
    if not text or is_relative(text):
        return text
    absolute = os.path.abspath(os.path.expanduser(text))
    origin = os.path.abspath(os.path.expanduser(str(start))) if start else os.getcwd()
    try:
        relative = os.path.relpath(absolute, origin)
    except ValueError:                     # another drive on Windows
        relative = ""
    # Climbing all the way to the filesystem root is no shorter and says less:
    # from /tmp, ``../home/you/Data`` is better written ``~/Data``.
    try:
        shared = os.path.commonpath([absolute, origin])
    except ValueError:
        shared = ""
    if (relative and shared and shared != os.path.dirname(shared)
            and relative.replace("\\", "/").split("/").count("..") <= max_up):
        return relative.replace("\\", "/")
    home = os.path.expanduser("~")
    if absolute == home or absolute.startswith(home + os.sep):
        return "~" + absolute[len(home):].replace("\\", "/")
    return absolute.replace("\\", "/")


def _normalise(path: object) -> str:
    """Return *path* as a forward-slash string with no trailing separator.

    Windows-style recorded paths are accepted so that metadata written on a
    Windows acquisition machine resolves on Linux.
    """
    text = str(path or "").strip()
    if not text:
        return ""
    text = text.replace("\\", "/")
    while len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text


def _is_prefix(prefix: str, path: str) -> bool:
    """True if *prefix* is a whole-component prefix of *path*."""
    if not prefix:
        return False
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


@dataclass
class PathAlias:
    """One recorded prefix and the local prefixes that may stand in for it."""

    prefix: str
    candidates: Tuple[str, ...] = ()
    label: str = ""

    def __post_init__(self):
        self.prefix = _normalise(self.prefix)
        self.candidates = tuple(_normalise(c) for c in self.candidates if _normalise(c))

    def rewrite(self, path: str) -> List[str]:
        """Return *path* rewritten under each candidate prefix."""
        if not _is_prefix(self.prefix, path):
            return []
        tail = path[len(self.prefix):].lstrip("/")
        return [f"{c}/{tail}" if tail else c for c in self.candidates]

    def to_dict(self) -> dict:
        return {
            "prefix": self.prefix,
            "candidates": list(self.candidates),
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PathAlias":
        return cls(
            prefix=data.get("prefix", ""),
            candidates=tuple(data.get("candidates", ())),
            label=data.get("label", ""),
        )


class PathResolver:
    """Resolve recorded paths to local ones through an ordered alias table.

    Parameters
    ----------
    aliases : sequence
        Either :class:`PathAlias` objects, or ``(prefix, candidates)`` pairs,
        or mappings as produced by :meth:`PathAlias.to_dict`.
    extra_roots : sequence of str, optional
        Directories searched by basename as a last resort for a *file* whose
        recorded directory cannot be mapped.  Off by default because it can be
        slow and ambiguous; pass explicitly when it helps.
    base : path, optional
        What a relative recorded path is relative to — the project root. Left
        unset, a relative path is relative to the working directory, as a
        bare ``open()`` would have it.
    """

    def __init__(self, aliases: Sequence = (), extra_roots: Sequence[str] = (),
                 base: object = None):
        self.aliases: List[PathAlias] = [self._coerce(a) for a in aliases]
        self.extra_roots: Tuple[str, ...] = tuple(
            _normalise(r) for r in extra_roots if _normalise(r)
        )
        self.base: str = _normalise(base) if base else ""
        self._cache: Dict[str, Optional[str]] = {}

    def anchor(self, path: object) -> str:
        """*path* as an absolute string: a relative one joined onto :attr:`base`."""
        recorded = _normalise(path)
        if recorded and self.base and is_relative(recorded):
            return _normalise(os.path.normpath(f"{self.base}/{recorded}"))
        return recorded

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce(alias) -> PathAlias:
        if isinstance(alias, PathAlias):
            return alias
        if isinstance(alias, dict):
            return PathAlias.from_dict(alias)
        prefix, candidates = alias
        if isinstance(candidates, (str, Path)):
            candidates = [candidates]
        return PathAlias(prefix=prefix, candidates=tuple(candidates))

    def add_alias(self, prefix: str, candidates, label: str = "") -> PathAlias:
        """Append an alias and invalidate the resolution cache."""
        if isinstance(candidates, (str, Path)):
            candidates = [candidates]
        alias = PathAlias(prefix=prefix, candidates=tuple(candidates), label=label)
        self.aliases.append(alias)
        self._cache.clear()
        return alias

    # ------------------------------------------------------------------
    # resolution
    # ------------------------------------------------------------------

    def candidates_for(self, path: object) -> List[str]:
        """Return every local path that *path* might correspond to.

        The recorded path comes first, followed by alias rewrites in order.
        Existence is not checked; see :meth:`resolve`.
        """
        recorded = self.anchor(path)
        if not recorded:
            return []
        out = [recorded]
        for alias in self.aliases:
            for rewritten in alias.rewrite(recorded):
                if rewritten not in out:
                    out.append(rewritten)
        return out

    def resolve(self, path: object) -> Optional[Path]:
        """Return the first existing candidate for *path*, or None."""
        recorded = _normalise(path)
        if not recorded:
            return None
        if recorded in self._cache:
            hit = self._cache[recorded]
            return Path(hit) if hit else None

        found: Optional[str] = None
        for candidate in self.candidates_for(recorded):
            if os.path.exists(candidate):
                found = candidate
                break
        if found is None:
            found = self._search_extra_roots(recorded)

        self._cache[recorded] = found
        return Path(found) if found else None

    def _search_extra_roots(self, recorded: str) -> Optional[str]:
        """Last resort: look for the basename under each extra root."""
        if not self.extra_roots:
            return None
        name = PurePosixPath(recorded).name
        if not name:
            return None
        for root in self.extra_roots:
            for hit in _glob.iglob(f"{root}/**/{name}", recursive=True):
                return hit
        return None

    def status(self, path: object) -> str:
        """Return :data:`LOCAL`, :data:`ALIASED` or :data:`MISSING`."""
        recorded = _normalise(path)
        if not recorded:
            return MISSING
        resolved = self.resolve(recorded)
        if resolved is None:
            return MISSING
        return LOCAL if _normalise(resolved) == self.anchor(recorded) else ALIASED

    def exists(self, path: object) -> bool:
        """True if *path* resolves to something on this machine."""
        return self.resolve(path) is not None

    # ------------------------------------------------------------------
    # globs
    # ------------------------------------------------------------------

    def resolve_glob(self, pattern: object, sort: bool = True) -> List[Path]:
        """Expand a recorded glob *pattern* against the local filesystem.

        The first candidate prefix that yields any match wins, so a partially
        mounted tree cannot silently mix files from two different roots.
        """
        recorded = _normalise(pattern)
        if not recorded:
            return []
        for candidate in self.candidates_for(recorded):
            matches = _glob.glob(candidate, recursive=True)
            if matches:
                paths = [Path(m) for m in matches]
                return sorted(paths) if sort else paths
        return []

    def resolve_many(self, paths: Iterable[object]) -> Tuple[List[Path], List[str]]:
        """Resolve many paths at once.

        Returns
        -------
        (resolved, missing)
            ``resolved`` holds the paths that were found, ``missing`` holds the
            recorded strings that were not.
        """
        resolved: List[Path] = []
        missing: List[str] = []
        for path in paths:
            hit = self.resolve(path)
            if hit is None:
                missing.append(_normalise(path))
            else:
                resolved.append(hit)
        return resolved, missing

    # ------------------------------------------------------------------
    # serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "aliases": [a.to_dict() for a in self.aliases],
            "extra_roots": list(self.extra_roots),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PathResolver":
        return cls(
            aliases=[PathAlias.from_dict(a) for a in data.get("aliases", [])],
            extra_roots=tuple(data.get("extra_roots", ())),
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"PathResolver({len(self.aliases)} aliases, {len(self.extra_roots)} roots)"


def suggest_aliases(recorded_paths: Iterable[object],
                    search_roots: Iterable[object],
                    max_depth: int = 3) -> List[PathAlias]:
    """Propose aliases by matching recorded path components against local trees.

    For each recorded path, walk its components from the deepest end and look
    for a directory of the same name under one of *search_roots*.  The longest
    recorded prefix that can be replaced is reported.  This is a convenience
    for first-time project setup; the result should be reviewed, not trusted
    blindly, because directory names repeat.

    Parameters
    ----------
    recorded_paths : iterable
        Paths as written in the metadata.
    search_roots : iterable
        Local directories to search, e.g. ``["/mnt/instrument"]``.
    max_depth : int
        How many directory levels below each root to scan.
    """
    roots = [Path(_normalise(r)) for r in search_roots if _normalise(r)]
    roots = [r for r in roots if r.is_dir()]
    if not roots:
        return []

    # Index directory names found under each root, shallowest first.
    index: Dict[str, List[str]] = {}
    for root in roots:
        for depth in range(1, max_depth + 1):
            for entry in root.glob("/".join(["*"] * depth)):
                if entry.is_dir():
                    index.setdefault(entry.name, []).append(_normalise(entry))

    found: Dict[str, PathAlias] = {}
    for recorded in recorded_paths:
        text = _normalise(recorded)
        if not text:
            continue
        parts = PurePosixPath(text).parts
        # Deepest component first gives the longest replaceable prefix.
        for cut in range(len(parts) - 1, 0, -1):
            name = parts[cut]
            locals_ = index.get(name)
            if not locals_:
                continue
            prefix = _normalise("/".join(parts[: cut + 1]))
            if prefix in found:
                break
            found[prefix] = PathAlias(
                prefix=prefix, candidates=tuple(dict.fromkeys(locals_)),
                label=f"matched on {name!r}",
            )
            break
    return list(found.values())


__all__ = [
    "PathResolver", "PathAlias", "suggest_aliases", "display_path",
    "is_relative", "LOCAL", "ALIASED", "MISSING",
]
