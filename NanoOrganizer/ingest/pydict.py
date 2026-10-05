#!/usr/bin/env python3
"""
Read sample-keyed dictionaries out of an authored ``*.py`` metadata file.

The instrument-side convention in these projects is a plain Python module
holding one or more dictionaries keyed by sample id::

    Synthesis_dict = {
        "Sample000001": { ... },
        "Sample000002": { ... },
    }

Python rather than JSON is deliberate on the authoring side: records are often
built by a helper function so that ten samples sharing a protocol do not become
ten hand-copied blocks.  That convenience is exactly why the file has to be
*executed* to be read.

.. warning::
   Importing such a file runs the code in it.  Only ingest metadata modules you
   or your collaborators wrote.  Nothing here sandboxes the import.

The module is loaded under a private name so it cannot collide with, or be
cached as, a real package, and the project directory is *not* put on
``sys.path``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# A sample key looks like "Sample000001", "S001", "AuNP_01" – a short token,
# not a sentence.  Used to decide whether a dict is sample-keyed.
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-.]{0,63}$")

# Dict variable names that carry a stage meaning, longest match first.
STAGE_HINTS = (
    ("synthesis", "synthesis"),
    ("catalysis", "catalysis"),
    ("reaction", "reaction"),
    ("characterization", "characterization"),
    ("measurement", "measurement"),
    ("assay", "assay"),
    ("sample", ""),
)


def load_module(path: Path):
    """Import *path* as an anonymous module and return it."""
    path = Path(path)
    name = f"_nanoorganizer_meta_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import metadata module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        # Do not leave a throwaway module behind in the import cache.
        sys.modules.pop(name, None)
    return module


def is_sample_keyed(value: Any, min_samples: int = 1) -> bool:
    """True if *value* looks like ``{sample_id: {...}, ...}``."""
    if not isinstance(value, dict) or len(value) < min_samples:
        return False
    for key, record in value.items():
        if not isinstance(key, str) or not _KEY_RE.match(key):
            return False
        if not isinstance(record, dict):
            return False
    return True


def find_sample_dicts(path: Path, min_samples: int = 1) -> Dict[str, Dict[str, dict]]:
    """Return every module-level sample-keyed dict in *path*.

    Returns
    -------
    dict
        ``{variable_name: {sample_id: record}}``, private names skipped.
    """
    module = load_module(path)
    found: Dict[str, Dict[str, dict]] = {}
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if is_sample_keyed(value, min_samples=min_samples):
            found[name] = value
    return found


def stage_from_name(name: str, default: str = "") -> str:
    """Infer a stage label from a dict variable name.

    ``"Synthesis_dict"`` → ``"synthesis"``; ``"Catalysis_dict_2026"`` →
    ``"catalysis"``.  Falls back to the name with ``_dict`` stripped.
    """
    lowered = name.lower()
    for hint, stage in STAGE_HINTS:
        if hint in lowered:
            return stage or default
    cleaned = re.sub(r"_?dicts?$", "", lowered).strip("_")
    return cleaned or default


def stage_from_filename(path: Path, default: str = "") -> str:
    """Infer a stage label from a metadata filename."""
    return stage_from_name(Path(path).stem, default=default)


def looks_like_metadata_module(path: Path) -> bool:
    """Cheap textual check used by adapter auto-detection.

    Reads the file rather than importing it, so a file that merely *looks*
    wrong is rejected without executing anything.
    """
    path = Path(path)
    if path.suffix != ".py":
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not re.search(r"^\s*\w*[Dd]ict\w*\s*=\s*\{", text, re.MULTILINE):
        return False
    return bool(re.search(r"[\"'][A-Za-z][A-Za-z0-9_\-.]{0,63}[\"']\s*:\s*\{", text))


__all__ = [
    "load_module", "find_sample_dicts", "is_sample_keyed",
    "stage_from_name", "stage_from_filename", "looks_like_metadata_module",
]
