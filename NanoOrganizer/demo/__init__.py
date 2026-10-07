#!/usr/bin/env python3
"""
Generated example projects, so the package has something to run on anywhere.

Two of them, for two different questions:

:func:`build_demo_project`
    Small and quick — one technique on the curve side, one on the image side,
    six samples, a few seconds to build.  Use it for a first look, for tests,
    and whenever you want the pipeline without the scenery.

:func:`build_showcase_project`
    A full campaign: a Cu–Au alloy nanocatalyst library for CO₂ reduction seen
    by fifteen techniques across four stages, with a sparse measurement matrix
    and one failed run.  Use it to see what the framework is actually for.
    It is the data behind the workflow notebooks (``10`` → ``12``), the web
    app's **Demo** page and the README: four metadata dicts declare most of
    it, and four techniques arrive as bare folders that are linked by hand.
    Every path it records is relative to its own folder, so the organizer
    built from it sits beside it and the whole folder moves as one piece.

Both are built from a hidden control variable the pipeline is meant to
recover, and both refuse to overwrite a directory they did not create.

>>> from NanoOrganizer.demo import build_showcase_project
>>> from NanoOrganizer import open_project
>>> root = build_showcase_project("/tmp/CuAuDemo")       # doctest: +SKIP
>>> workbench = open_project(root)                       # doctest: +SKIP

Where generated data goes
-------------------------
:func:`demo_root` gives one parent for everything these generators write, so a
few runs of the notebooks cannot leave a scatter of directories across a home
folder.  Override it with ``$NANOORGANIZER_DEMO_ROOT``; nothing in the package
writes anywhere else unless you pass an explicit path, which every builder
still accepts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

#: Environment variable that overrides where generated demo data is written.
DEMO_ROOT_ENV = "NANOORGANIZER_DEMO_ROOT"

def _default_demo_root() -> Path:
    """``../OrgDemo`` beside the source checkout, else ``~/Repos/OrgDemo``.

    Beside the checkout — a sibling of the repository folder — is where a
    clone's demo data belongs: next to the code, outside it, and never loose
    in a home directory. An installed (non-editable) package has no checkout
    to sit beside, and falls back to ``~/Repos/OrgDemo``.
    """
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "setup.py").exists() and (checkout / "NanoOrganizer").is_dir():
        return checkout.parent / "OrgDemo"
    return Path.home() / "Repos" / "OrgDemo"


#: Default parent for generated data.  One directory, not one per project.
DEFAULT_DEMO_ROOT = _default_demo_root()


def demo_root(*parts: Union[str, Path]) -> Path:
    """Return the demo data directory, optionally joined with *parts*.

    >>> demo_root()                      # doctest: +SKIP
    PosixPath('/home/you/Repos/OrgDemo')       # ../OrgDemo beside the checkout
    >>> demo_root("CuAu", "cuau.json")   # doctest: +SKIP
    PosixPath('/home/you/Repos/OrgDemo/CuAu/cuau.json')

    The directory is **not** created here — the builder that writes into it
    does that, so merely asking where data would go leaves nothing behind.
    """
    base = os.environ.get(DEMO_ROOT_ENV, "").strip()
    root = Path(base).expanduser() if base else DEFAULT_DEMO_ROOT
    return root.joinpath(*(str(p) for p in parts)) if parts else root


from NanoOrganizer.demo.materials import (
    DEFAULT_FRACTIONS, PRODUCTS, co_binding_eV, co_partial_current,
    d_band_centre_eV, faradaic_efficiency, lattice_parameter_A, lspr_nm,
    showcase_truth, surface_au_fraction,
)
from NanoOrganizer.demo.materials import (
    particle_diameter_nm as alloy_particle_diameter_nm,
)
from NanoOrganizer.demo.showcase import build_showcase_project
from NanoOrganizer.demo.simple import (
    AXIS, DEFAULT_TEMPERATURES, band_centre_nm, build_demo_project, demo_truth,
    particle_diameter_nm,
)

__all__ = [
    # where generated data goes
    "demo_root", "DEMO_ROOT_ENV", "DEFAULT_DEMO_ROOT",
    # the quick demo
    "build_demo_project", "demo_truth", "AXIS", "DEFAULT_TEMPERATURES",
    "band_centre_nm", "particle_diameter_nm",
    # the multimodal showcase
    "build_showcase_project", "showcase_truth", "DEFAULT_FRACTIONS",
    "PRODUCTS", "lattice_parameter_A", "lspr_nm", "alloy_particle_diameter_nm",
    "surface_au_fraction", "d_band_centre_eV", "co_binding_eV",
    "faradaic_efficiency", "co_partial_current",
]
