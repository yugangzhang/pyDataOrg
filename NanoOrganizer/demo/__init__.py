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

Both are built from a hidden control variable the pipeline is meant to
recover, and both refuse to overwrite a directory they did not create.

>>> from NanoOrganizer.demo import build_showcase_project
>>> from NanoOrganizer import open_project
>>> root = build_showcase_project("/tmp/CuAuDemo")       # doctest: +SKIP
>>> workbench = open_project(root)                       # doctest: +SKIP
"""

from __future__ import annotations

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
    # the quick demo
    "build_demo_project", "demo_truth", "AXIS", "DEFAULT_TEMPERATURES",
    "band_centre_nm", "particle_diameter_nm",
    # the multimodal showcase
    "build_showcase_project", "showcase_truth", "DEFAULT_FRACTIONS",
    "PRODUCTS", "lattice_parameter_A", "lspr_nm", "alloy_particle_diameter_nm",
    "surface_au_fraction", "d_band_centre_eV", "co_binding_eV",
    "faradaic_efficiency", "co_partial_current",
]
