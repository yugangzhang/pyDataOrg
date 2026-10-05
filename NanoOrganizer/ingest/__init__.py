#!/usr/bin/env python3
"""
Ingest adapters – authored metadata in, :class:`Sample` records out.

An adapter is a callable ``ingest(path, project=None, **kwargs) -> List[Sample]``
plus an optional ``detect(path) -> bool`` used for auto-selection.  Registering
a new authoring format is one :func:`register_adapter` call; nothing else in
the package needs to know about it.

Adapters never write to disk and never mutate the file they read.  The project
decides what to do with the samples they return, which keeps re-ingest
idempotent: reading the same file twice merges onto the same sample ids rather
than duplicating them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from NanoOrganizer.core.schema import Sample


@dataclass
class Adapter:
    """One registered metadata reader."""

    key: str
    ingest: Callable[..., List[Sample]]
    detect: Optional[Callable[[Path], bool]] = None
    label: str = ""
    extensions: Sequence[str] = ()
    priority: int = 50          # lower runs first during auto-detection

    def can_read(self, path: Path) -> bool:
        if self.extensions and path.suffix.lower() not in self.extensions:
            return False
        if self.detect is None:
            return bool(self.extensions)
        try:
            return bool(self.detect(path))
        except Exception:
            return False


ADAPTERS: Dict[str, Adapter] = {}


def register_adapter(adapter: Adapter, overwrite: bool = False) -> Adapter:
    """Add *adapter* to the registry."""
    if adapter.key in ADAPTERS and not overwrite:
        raise ValueError(f"Adapter {adapter.key!r} is already registered")
    ADAPTERS[adapter.key] = adapter
    return adapter


def choose_adapter(path: Path) -> str:
    """Return the key of the first adapter that claims *path*.

    Raises
    ------
    ValueError
        If no adapter recognises the file, with the registered keys listed so
        the caller can pass one explicitly.
    """
    path = Path(path)
    for adapter in sorted(ADAPTERS.values(), key=lambda a: (a.priority, a.key)):
        if adapter.can_read(path):
            return adapter.key
    raise ValueError(
        f"No ingest adapter recognises {path.name!r}. "
        f"Pass adapter= explicitly; available: {', '.join(sorted(ADAPTERS))}"
    )


def run_adapter(key: str, path: Path, project=None, **kwargs) -> List[Sample]:
    """Run the named adapter over *path*."""
    adapter = ADAPTERS.get(key)
    if adapter is None:
        raise KeyError(
            f"Unknown ingest adapter {key!r}; "
            f"available: {', '.join(sorted(ADAPTERS))}"
        )
    return adapter.ingest(Path(path), project=project, **kwargs)


def list_adapters() -> List[Adapter]:
    return sorted(ADAPTERS.values(), key=lambda a: (a.priority, a.key))


# ---------------------------------------------------------------------------
# Built-in adapters
# ---------------------------------------------------------------------------

from NanoOrganizer.ingest import sampledict as _sampledict  # noqa: E402

register_adapter(Adapter(
    key="sampledict",
    ingest=_sampledict.ingest,
    detect=_sampledict.detect,
    label="Sample-keyed Python dict (*.py)",
    extensions=(".py",),
    priority=10,
))

__all__ = [
    "Adapter", "ADAPTERS", "register_adapter", "choose_adapter",
    "run_adapter", "list_adapters",
]
