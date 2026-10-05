#!/usr/bin/env python3
"""
Structure inspection — what is in there, without opening all of it.

Before you can organise a dataset you have to understand its shape: which
folders hold what, how deep the nesting goes, what keys a metadata file uses,
what is actually inside an HDF5 or an ``.npz``. That question is usually
answered by a mix of ``ls``, ``h5ls``, ``python -c "import json…"`` and
guesswork.

This module answers it uniformly. Every container — a directory, a JSON file,
an HDF5 group, a saved ``.npz``, a Python metadata module — is presented as the
same thing: a :class:`Node` with children you can ask for one layer at a time.

**It reads structure, not data.** Array shapes and dtypes come from headers;
a 4 GB tomogram is described without being loaded. Long values are truncated
and only short scalars are previewed, because the point is to understand the
layout, not to view the contents.

Addresses
---------
A node is addressed by a string: a filesystem path, optionally followed by
``::`` and a slash-separated path *inside* that file.

    /data/Project                         a directory
    /data/Project/meta.json               a file
    /data/Project/meta.json::samples/0    inside it
    /data/run.h5::entry/instrument        inside an HDF5 file

That one convention is what lets the browser treat "descend into a folder" and
"descend into a file" as the same operation.

From a notebook
---------------

>>> from NanoOrganizer.structure import tree
>>> print(tree("~/NanoOrganizerDemo", depth=2))     # doctest: +SKIP
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: Separator between a filesystem path and a path inside the file.
INSIDE = "::"

#: Default cap on children returned for one node. A directory with 100 000
#: files should describe itself instantly, not enumerate itself.
DEFAULT_LIMIT = 300

#: Files larger than this are described but not parsed, so that clicking a
#: node can never hang the browser.
MAX_PARSE_BYTES = 200 * 1024 * 1024

_ICONS = {
    "folder": "📁", "file": "📄", "group": "🗂️", "array": "🔢",
    "mapping": "🔑", "sequence": "📋", "value": "·", "table": "📊",
    "more": "…", "error": "⚠️",
}


@dataclass(frozen=True)
class Node:
    """One item in a structure tree.

    Attributes
    ----------
    name : str
        What to show. A file name, a dict key, an array index.
    kind : str
        ``folder``, ``file``, ``group``, ``mapping``, ``sequence``, ``array``,
        ``table``, ``value``, ``more`` or ``error``.
    detail : str
        The useful one-line summary: a shape and dtype, a file size, a child
        count, a truncated scalar.
    address : str
        Where to go to expand this node. Empty when it cannot be expanded.
    expandable : bool
        Whether :func:`children` will return anything.
    n_children : int, optional
        How many children, when that is known cheaply.
    """

    name: str
    kind: str = "value"
    detail: str = ""
    address: str = ""
    expandable: bool = False
    n_children: Optional[int] = None

    @property
    def icon(self) -> str:
        return _ICONS.get(self.kind, "·")

    @property
    def label(self) -> str:
        return f"{self.icon} {self.name}"

    def __str__(self) -> str:         # pragma: no cover - cosmetic
        return f"{self.label}  {self.detail}".rstrip()


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------

def split_address(address: str) -> Tuple[Path, List[str]]:
    """``"/a/b.json::x/0"`` → ``(Path("/a/b.json"), ["x", "0"])``."""
    text = str(address)
    if INSIDE in text:
        outer, inner = text.split(INSIDE, 1)
        return Path(outer).expanduser(), [p for p in inner.split("/") if p]
    return Path(text).expanduser(), []


def join_address(path, inside: Sequence[str] = ()) -> str:
    """The inverse of :func:`split_address`."""
    inside = [str(p) for p in inside if str(p)]
    return f"{path}{INSIDE}{'/'.join(inside)}" if inside else str(path)


def breadcrumbs(address: str) -> List[Tuple[str, str]]:
    """``[(label, address), …]`` from the filesystem root down to *address*.

    This is what makes drill-down reversible: every ancestor stays one click
    away, so descending into the wrong branch costs nothing.
    """
    path, inside = split_address(address)
    trail: List[Tuple[str, str]] = []

    parts = list(path.parts)
    for index in range(1, len(parts) + 1):
        here = Path(*parts[:index])
        trail.append((parts[index - 1] or str(here), str(here)))

    for index in range(1, len(inside) + 1):
        trail.append((inside[index - 1], join_address(path, inside[:index])))
    return trail


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def human_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def _preview(value: Any, limit: int = 60) -> str:
    """A short, safe rendering of a scalar."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.6g}" if isinstance(value, float) else str(value)
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _type_name(value: Any) -> str:
    return type(value).__name__


# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

def is_noise(name: str) -> bool:
    """True for an entry that is housekeeping rather than data.

    Dot-files and ``__pycache__`` are not part of anyone's dataset, and
    ``__pycache__`` in particular is created by this package's own metadata
    ingest — showing it would be reporting our own footprint back as data.
    Hidden entries are counted in the folder's summary rather than dropped
    silently, and ``show_hidden=True`` brings them back.
    """
    return name.startswith(".") or name in {"__pycache__", "__MACOSX"}


def _folder_detail(path: Path, show_hidden: bool = False) -> str:
    """``"3 folders · 1322 files · .npy 1322, .txt 1"`` — read in one pass."""
    folders = hidden = 0
    extensions: Dict[str, int] = {}
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if not show_hidden and is_noise(entry.name):
                    hidden += 1
                    continue
                if entry.is_dir():
                    folders += 1
                else:
                    suffix = Path(entry.name).suffix.lower() or "(no suffix)"
                    extensions[suffix] = extensions.get(suffix, 0) + 1
    except OSError as exc:
        return f"unreadable: {exc.strerror}"

    files = sum(extensions.values())
    parts = []
    if folders:
        parts.append(f"{folders} folder{'s' if folders != 1 else ''}")
    if files:
        parts.append(f"{files} file{'s' if files != 1 else ''}")
    if extensions:
        common = sorted(extensions.items(), key=lambda kv: -kv[1])[:4]
        parts.append(", ".join(f"{suffix} {count}" for suffix, count in common))
    if hidden:
        parts.append(f"{hidden} hidden")
    return " · ".join(parts) or "empty"


def _folder_children(path: Path, limit: int,
                     show_hidden: bool = False) -> List[Node]:
    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(),
                                                          e.name.lower()))
    except OSError as exc:
        return [Node(name=str(exc.strerror or exc), kind="error")]

    if not show_hidden:
        entries = [e for e in entries if not is_noise(e.name)]

    nodes: List[Node] = []
    for entry in entries[:limit]:
        child = Path(entry.path)
        if entry.is_dir():
            nodes.append(Node(name=entry.name, kind="folder",
                              detail=_folder_detail(child, show_hidden),
                              address=str(child), expandable=True))
        else:
            nodes.append(describe_file(child))

    if len(entries) > limit:
        nodes.append(_more(len(entries) - limit))
    return nodes


def _more(remaining: int) -> Node:
    """The node that stands for what was not listed.

    It carries the true remainder, so a caller rendering a tree can report
    "+40 more" rather than counting its own truncated list and reporting the
    size of the truncation.
    """
    return Node(name=f"+{remaining} more", kind="more",
                detail="raise the per-layer limit to see them")


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

#: Suffixes this module can look inside, and the handler name for each.
OPENERS = {
    ".json": "json", ".npz": "npz", ".npy": "npy",
    ".h5": "hdf5", ".hdf5": "hdf5", ".nxs": "hdf5", ".nx5": "hdf5",
    ".py": "pydict",
    ".csv": "table", ".dat": "table", ".txt": "table", ".xy": "table",
    ".yaml": "yaml", ".yml": "yaml",
}


def describe_file(path: Path) -> Node:
    """One line about a file, and whether it can be opened."""
    try:
        size = path.stat().st_size
    except OSError:
        size = 0

    suffix = path.suffix.lower()
    handler = OPENERS.get(suffix)
    detail = human_bytes(size)

    if suffix == ".npy":
        shape = _npy_header(path)
        if shape:
            detail = f"{shape} · {detail}"
        return Node(name=path.name, kind="array", detail=detail,
                    address=str(path), expandable=False)

    expandable = bool(handler) and size <= MAX_PARSE_BYTES
    if handler and not expandable:
        detail += " · too large to parse"
    return Node(name=path.name, kind="file", detail=detail,
                address=str(path) if expandable else "", expandable=expandable)


def _npy_header(path: Path) -> str:
    """Shape and dtype of a ``.npy``, from its header alone."""
    try:
        import numpy as np

        with open(path, "rb") as handle:
            version = np.lib.format.read_magic(handle)
            if version[0] == 1:
                shape, _, dtype = np.lib.format.read_array_header_1_0(handle)
            else:
                shape, _, dtype = np.lib.format.read_array_header_2_0(handle)
        return f"{dtype} {tuple(shape)}"
    except Exception:
        return ""


def _array_node(name: str, array, address: str = "") -> Node:
    detail = f"{array.dtype} {tuple(array.shape)}"
    if array.size == 1:
        detail += f" = {_preview(array.reshape(-1)[0])}"
    return Node(name=name, kind="array", detail=detail, address=address)


# --- JSON ------------------------------------------------------------------

def _json_root(path: Path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _walk_object(node: Any, inside: Sequence[str]) -> Any:
    """Follow *inside* through nested mappings and sequences."""
    for step in inside:
        if isinstance(node, dict):
            if step in node:
                node = node[step]
                continue
            matches = [k for k in node if str(k) == step]
            if not matches:
                raise KeyError(step)
            node = node[matches[0]]
        elif isinstance(node, (list, tuple)):
            node = node[int(step)]
        else:
            raise KeyError(step)
    return node


def _object_children(node: Any, path: Path, inside: Sequence[str],
                     limit: int) -> List[Node]:
    """Children of a plain Python mapping or sequence."""
    items: List[Tuple[str, Any]]
    if isinstance(node, dict):
        items = [(str(k), v) for k, v in node.items()]
    elif isinstance(node, (list, tuple)):
        items = [(str(i), v) for i, v in enumerate(node)]
    else:
        return []

    nodes: List[Node] = []
    for name, value in items[:limit]:
        address = join_address(path, list(inside) + [name])
        if isinstance(value, dict):
            nodes.append(Node(name=name, kind="mapping",
                              detail=f"{len(value)} keys",
                              address=address, expandable=True,
                              n_children=len(value)))
        elif isinstance(value, (list, tuple)):
            nodes.append(Node(name=name, kind="sequence",
                              detail=_sequence_detail(value),
                              address=address, expandable=bool(value),
                              n_children=len(value)))
        elif hasattr(value, "shape") and hasattr(value, "dtype"):
            nodes.append(_array_node(name, value))
        else:
            nodes.append(Node(name=name, kind="value",
                              detail=f"{_type_name(value)} = {_preview(value)}"))

    if len(items) > limit:
        nodes.append(_more(len(items) - limit))
    return nodes


def _sequence_detail(value: Sequence) -> str:
    """``"12 items of dict"`` — the element type matters more than the length."""
    if not value:
        return "empty"
    kinds = {_type_name(v) for v in value[:50]}
    kind = kinds.pop() if len(kinds) == 1 else f"{len(kinds)} types"
    return f"{len(value)} items of {kind}"


# --- npz -------------------------------------------------------------------

def _npz_children(path: Path, inside: Sequence[str], limit: int) -> List[Node]:
    import numpy as np

    with np.load(path, allow_pickle=False, mmap_mode=None) as bundle:
        if not inside:
            return [_array_node(name, bundle[name]) for name in list(bundle)[:limit]]
        return [_array_node(inside[-1], bundle[inside[-1]])]


# --- HDF5 ------------------------------------------------------------------

def _hdf5_children(path: Path, inside: Sequence[str], limit: int) -> List[Node]:
    try:
        import h5py
    except ImportError:
        return [Node(name="h5py is not installed", kind="error",
                     detail="pip install \"nanoorganizer[hdf5]\"")]

    nodes: List[Node] = []
    with h5py.File(path, "r") as handle:
        group = handle["/" + "/".join(inside)] if inside else handle

        for key, value in list(group.attrs.items())[:limit]:
            nodes.append(Node(name=f"@{key}", kind="value",
                              detail=f"attr = {_preview(value)}"))

        if not hasattr(group, "keys"):
            return nodes

        for name in list(group.keys())[:limit]:
            item = group[name]
            address = join_address(path, list(inside) + [name])
            if hasattr(item, "keys"):
                nodes.append(Node(name=name, kind="group",
                                  detail=f"{len(item)} items",
                                  address=address, expandable=True,
                                  n_children=len(item)))
            else:
                detail = f"{item.dtype} {tuple(item.shape)}"
                if item.chunks:
                    detail += f" · chunks {tuple(item.chunks)}"
                if item.compression:
                    detail += f" · {item.compression}"
                nodes.append(Node(name=name, kind="array", detail=detail,
                                  address=address,
                                  expandable=bool(item.attrs)))
    return nodes


# --- Python metadata modules ----------------------------------------------

def _pydict_children(path: Path, inside: Sequence[str], limit: int) -> List[Node]:
    """Sample-keyed dicts in a metadata module.

    Importing a module runs it, so this is the one opener that can execute
    code. It is only reached for a file the user chose by name, and the GUI
    says so before it happens.
    """
    from NanoOrganizer.ingest import pydict

    found = pydict.find_sample_dicts(path)
    if not found:
        return [Node(name="no sample-keyed dicts found", kind="error",
                     detail="expected a module-level dict keyed by sample id")]

    if not inside:
        return [
            Node(name=name, kind="mapping", detail=f"{len(records)} samples",
                 address=join_address(path, [name]), expandable=True,
                 n_children=len(records))
            for name, records in found.items()
        ]
    return _object_children(_walk_object(found, inside), path, inside, limit)


# --- Delimited text --------------------------------------------------------

def _table_children(path: Path, limit: int) -> List[Node]:
    """Header lines and inferred columns of a text table."""
    nodes: List[Node] = []
    header: List[str] = []
    first_data = ""
    rows = 0

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("#", "%", ";")):
                if len(header) < 8:
                    header.append(stripped.lstrip("#%; ").strip())
                continue
            if not first_data:
                first_data = stripped
            rows += 1

    for text in header:
        nodes.append(Node(name="header", kind="value", detail=text))

    if first_data:
        delimiter = "," if first_data.count(",") > first_data.count("\t") else None
        fields = (first_data.split(",") if delimiter
                  else first_data.split())
        names = header[-1].replace(",", " ").split() if header else []
        for index, value in enumerate(fields[:limit]):
            label = names[index] if index < len(names) else f"column {index}"
            nodes.append(Node(name=label, kind="value",
                              detail=f"first value {value.strip()}"))
        nodes.insert(0, Node(name="shape", kind="table",
                             detail=f"{rows} rows × {len(fields)} columns"))
    return nodes


def _yaml_children(path: Path, inside: Sequence[str], limit: int) -> List[Node]:
    try:
        import yaml
    except ImportError:
        return [Node(name="PyYAML is not installed", kind="error",
                     detail="pip install pyyaml")]
    with open(path, "r", encoding="utf-8") as handle:
        root = yaml.safe_load(handle)
    return _object_children(_walk_object(root, inside), path, inside, limit)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def describe(address: str, show_hidden: bool = False) -> Node:
    """One :class:`Node` describing whatever *address* points at."""
    path, inside = split_address(address)

    if not path.exists():
        return Node(name=path.name or str(path), kind="error",
                    detail="does not exist on this machine")
    if path.is_dir():
        return Node(name=path.name or str(path), kind="folder",
                    detail=_folder_detail(path, show_hidden),
                    address=str(path), expandable=True)
    if not inside:
        return describe_file(path)

    node = Node(name=inside[-1], kind="mapping", detail="",
                address=address, expandable=True)
    return node


def children(address: str, limit: int = DEFAULT_LIMIT,
             show_hidden: bool = False) -> List[Node]:
    """One layer of children below *address*.

    Never raises for a bad path or an unreadable file: the problem comes back
    as an ``error`` node, because a browser that throws on one unreadable file
    in a thousand is not a browser.
    """
    path, inside = split_address(address)

    try:
        if path.is_dir():
            return _folder_children(path, limit, show_hidden)
        if not path.exists():
            return [Node(name="not found", kind="error", detail=str(path))]

        handler = OPENERS.get(path.suffix.lower())
        if handler == "json":
            return _object_children(_walk_object(_json_root(path), inside),
                                    path, inside, limit)
        if handler == "yaml":
            return _yaml_children(path, inside, limit)
        if handler == "npz":
            return _npz_children(path, inside, limit)
        if handler == "hdf5":
            return _hdf5_children(path, inside, limit)
        if handler == "pydict":
            return _pydict_children(path, inside, limit)
        if handler == "table":
            return _table_children(path, limit)
        return []
    except Exception as exc:
        return [Node(name=f"{type(exc).__name__}", kind="error",
                     detail=str(exc)[:200])]


def tree(address: str, depth: int = 2, limit: int = 12,
         show_hidden: bool = False, _prefix: str = "",
         _root: bool = True) -> str:
    """An indented text tree below *address*, for printing in a notebook.

    *depth* is how many layers to descend and *limit* how many children to
    show per layer — both deliberately small, because the useful output is one
    that fits on a screen.
    """
    lines: List[str] = []
    if _root:
        node = describe(address, show_hidden)
        lines.append(f"{node.icon} {node.name}  {node.detail}".rstrip())

    if depth <= 0:
        return "\n".join(lines)

    # The openers add their own "+n more" node when they truncate, and it
    # carries the true remainder — counting the returned list instead would
    # report the size of the truncation rather than of what was left out.
    kids = children(address, limit=limit, show_hidden=show_hidden)

    for index, child in enumerate(kids):
        last = index == len(kids) - 1
        joint = "└── " if last else "├── "
        lines.append(f"{_prefix}{joint}{child.icon} {child.name}"
                     f"{('  ' + child.detail) if child.detail else ''}")
        if child.expandable and child.address and depth > 1:
            lines.append(tree(child.address, depth - 1, limit, show_hidden,
                              _prefix + ("    " if last else "│   "),
                              _root=False))
    return "\n".join(line for line in lines if line)


__all__ = [
    "Node", "INSIDE", "DEFAULT_LIMIT", "OPENERS", "describe", "describe_file",
    "children", "tree", "breadcrumbs", "split_address", "join_address",
    "human_bytes", "is_noise",
]
