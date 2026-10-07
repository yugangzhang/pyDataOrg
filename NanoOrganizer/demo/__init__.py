#!/usr/bin/env python3
"""
Generated example projects, so the package has something to run on anywhere.

Three of them, for three different questions:

:func:`~NanoOrganizer.demo.lab.simulate_lab`
    **Raw data, not a project** — three instruments writing into three folder
    trees that do not agree, plus a metadata dict naming only some of it. The
    data behind notebooks 10–12 and the web app's Demo page: building the
    organizer from it is the lesson.

:func:`build_demo_project`
    Small and quick — one technique on the curve side, one on the image side,
    six samples, a few seconds to build.  Use it for a first look, for tests,
    and whenever you want the pipeline without the scenery.

:func:`build_showcase_project`
    A full campaign: a Cu–Au alloy nanocatalyst library for CO₂ reduction seen
    by fifteen techniques across four stages, with a sparse measurement matrix
    and one failed run.  Use it to see what the framework is actually for.

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

#: Default parent for generated data.  One directory, not one per project.
DEFAULT_DEMO_ROOT = Path.home() / "Repos" / "OrgDemo"


def demo_root(*parts: Union[str, Path]) -> Path:
    """Return the demo data directory, optionally joined with *parts*.

    >>> demo_root()                      # doctest: +SKIP
    PosixPath('/home/you/Repos/OrgDemo')
    >>> demo_root("Lab", "lab.json")     # doctest: +SKIP
    PosixPath('/home/you/Repos/OrgDemo/Lab/lab.json')

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
from NanoOrganizer.demo.lab import lab_paths, lab_truth, simulate_lab
from NanoOrganizer.demo.showcase import build_showcase_project
from NanoOrganizer.demo.simple import (
    AXIS, DEFAULT_TEMPERATURES, band_centre_nm, build_demo_project, demo_truth,
    particle_diameter_nm,
)

__all__ = [
    # where generated data goes
    "demo_root", "DEMO_ROOT_ENV", "DEFAULT_DEMO_ROOT",
    # the lab: raw data for notebooks 10-12 and the Demo page
    "simulate_lab", "lab_paths", "lab_truth",
    # the quick demo
    "build_demo_project", "demo_truth", "AXIS", "DEFAULT_TEMPERATURES",
    "band_centre_nm", "particle_diameter_nm",
    # the multimodal showcase
    "build_showcase_project", "showcase_truth", "DEFAULT_FRACTIONS",
    "PRODUCTS", "lattice_parameter_A", "lspr_nm", "alloy_particle_diameter_nm",
    "surface_au_fraction", "d_band_centre_eV", "co_binding_eV",
    "faradaic_efficiency", "co_partial_current",
]
