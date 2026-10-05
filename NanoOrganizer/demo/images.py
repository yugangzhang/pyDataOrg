#!/usr/bin/env python3
"""
Synthetic 2D and 3D data for the multimodal demo.

Three kinds of object live here, and they deliberately show different things:

* **TEM** resolves the primary particles, so it measures
  :func:`materials.particle_diameter_nm`;
* **SEM** and **tomography** see the agglomerates the particles form on the
  support, so they measure :func:`materials.aggregate_nm` — the same object
  DLS and XPCS follow in suspension;
* **2D SAXS** is not a picture of anything; it is the detector image whose
  azimuthal average is the 1D curve.

A framework that labels all of these "image" and leaves it there would be
useless.  Telling them apart is what ``domain`` and ``shape`` in the modality
registry are for.

The micrographs carry their pixel calibration the way a real instrument does —
in the TIFF description tag — and the TEM frames carry an instrument banner
below the image, so the reader's banner-cropping path is exercised rather than
assumed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from NanoOrganizer.demo import materials as mat
from NanoOrganizer.demo import signals as sig

#: Pixel calibrations, in pixels per micrometre, as the TIFF tag records them.
TEM_PIXELS_PER_MICRON = 2000.0      # 0.5 nm/px — a field with ~50 particles in it
SEM_PIXELS_PER_MICRON = 500.0       # 2 nm/px — resolves agglomerates

#: Voxel size of the reconstructed tomogram, nm.
TOMO_NM_PER_VOXEL = 2.0

#: Rows of instrument banner written below a TEM frame.
TEM_BANNER_ROWS = 48


def _place_discs(size: int, radius_px: float, coverage: float, rng,
                 dispersity: float = 0.14) -> np.ndarray:
    """Return a float mask of non-overlapping discs filling *coverage* of the frame.

    Rejection sampling with a minimum centre separation, so particles touch
    but do not overlap — which is the case watershed splitting is for, and the
    case a demo therefore has to contain.
    """
    mask = np.zeros((size, size), dtype=float)
    target = coverage * size * size
    area = 0.0
    centres: list = []
    attempts = 0
    max_attempts = 20000

    yy, xx = np.ogrid[:size, :size]
    while area < target and attempts < max_attempts:
        attempts += 1
        this_radius = max(radius_px * rng.lognormal(0.0, dispersity), 1.5)
        row = rng.uniform(this_radius, size - this_radius)
        column = rng.uniform(this_radius, size - this_radius)
        clash = any(
            (row - r) ** 2 + (column - c) ** 2 < (0.96 * (this_radius + rad)) ** 2
            for r, c, rad in centres
        )
        if clash:
            continue
        centres.append((row, column, this_radius))
        mask[(yy - row) ** 2 + (xx - column) ** 2 <= this_radius ** 2] = 1.0
        area += np.pi * this_radius ** 2

    return mask


def tem_image(x: float, size: int, rng) -> np.ndarray:
    """Bright-field TEM: metal absorbs, so particles are dark on a light film.

    A banner is appended below the image, as the microscope writes it.  The
    reader crops it; nothing downstream should ever see those rows.
    """
    nm_per_px = 1000.0 / TEM_PIXELS_PER_MICRON
    radius_px = 0.5 * mat.particle_diameter_nm(x) / nm_per_px

    mask = _place_discs(size, radius_px, 0.16, rng, mat.size_dispersity(x))
    support = 198.0 + 6.0 * np.sin(np.linspace(0.0, 2.6, size))[None, :]
    frame = support - 140.0 * mask
    frame += rng.normal(0.0, 3.2, frame.shape)

    banner = np.full((TEM_BANNER_ROWS, size), 18.0)
    banner[8:16, 10:10 + size // 3] = 230.0        # a scale bar
    banner[26:34, 10:10 + size // 2] = 120.0       # a line of status text
    return np.clip(np.vstack([frame, banner]), 0.0, 255.0)


def sem_image(x: float, size: int, rng) -> np.ndarray:
    """Secondary-electron SEM: particles are *brighter* than the support.

    The contrast is inverted relative to TEM, which is exactly why
    :func:`NanoOrganizer.analysis.imaging.particle_sizing` has to decide the
    polarity rather than assume it.  At this magnification what you resolve is
    the agglomerate, not the primary particle.
    """
    nm_per_px = 1000.0 / SEM_PIXELS_PER_MICRON
    radius_px = 0.5 * mat.aggregate_nm(x) / nm_per_px

    mask = _place_discs(size, radius_px, 0.22, rng, 0.22)
    frame = 55.0 + 150.0 * mask
    # Edge brightening: the real reason SEM particles look like they glow.
    shifted = np.zeros_like(mask)
    shifted[1:-1, 1:-1] = mask[1:-1, 1:-1] - mask[:-2, 1:-1]
    frame += 45.0 * np.clip(shifted, 0.0, None)
    frame += rng.normal(0.0, 6.0, frame.shape)
    return np.clip(frame, 0.0, 255.0)


def tomo_volume(x: float, size: int, rng) -> np.ndarray:
    """A reconstructed tomogram of one agglomerate, as 8-bit voxels.

    Primary particles packed into a porous cluster: the thing tomography is
    actually for is the pore structure, which no projection image can show.
    """
    volume = np.zeros((size, size, size), dtype=bool)
    primary_px = max(0.5 * mat.particle_diameter_nm(x) / TOMO_NM_PER_VOXEL, 1.2)
    cluster_px = min(0.5 * mat.aggregate_nm(x) / TOMO_NM_PER_VOXEL, 0.46 * size)
    centre = size / 2.0

    # Enough primaries to fill about a fifth of the cluster's volume: packed
    # loosely enough that the pore network is the visible feature, which is
    # the only reason to have done a tomogram rather than a projection.
    n_particles = int(np.clip(0.20 * (cluster_px / primary_px) ** 3, 12, 4000))

    reach = int(np.ceil(primary_px * 1.6)) + 1
    offsets = np.arange(-reach, reach + 1)
    dz, dy, dx = np.meshgrid(offsets, offsets, offsets, indexing="ij")

    for _ in range(n_particles):
        direction = rng.normal(size=3)
        direction /= np.linalg.norm(direction) or 1.0
        distance = cluster_px * rng.uniform(0.0, 1.0) ** (1.0 / 3.0)
        cz, cy, cx = np.round(centre + direction * distance).astype(int)
        radius = max(primary_px * rng.lognormal(0.0, 0.15), 1.2)

        # Only touch the sphere's own bounding box: filling the whole array
        # once per particle is what makes a naive generator unusably slow.
        blob = (dz ** 2 + dy ** 2 + dx ** 2) <= radius ** 2
        z0, y0, x0 = cz - reach, cy - reach, cx - reach
        zs = slice(max(z0, 0), min(z0 + blob.shape[0], size))
        ys = slice(max(y0, 0), min(y0 + blob.shape[1], size))
        xs = slice(max(x0, 0), min(x0 + blob.shape[2], size))
        if zs.start >= zs.stop or ys.start >= ys.stop or xs.start >= xs.stop:
            continue
        volume[zs, ys, xs] |= blob[zs.start - z0: zs.stop - z0,
                                   ys.start - y0: ys.stop - y0,
                                   xs.start - x0: xs.stop - x0]

    out = 40.0 + 170.0 * volume
    out += rng.normal(0.0, 9.0, out.shape)
    return np.clip(out, 0.0, 255.0).astype(np.uint8)


def saxs2d_pattern(x: float, size: int, rng) -> np.ndarray:
    """The detector image whose azimuthal average is :func:`signals.saxs_curve`.

    Isotropic, because the particles are in suspension and have no preferred
    orientation, with a beamstop shadow at the centre — so a viewer that
    assumes the brightest pixel is the beam gets it wrong, as it should.
    """
    q_curve, i_curve = sig.saxs_curve(x, rng)
    centre = size / 2.0
    q_max_edge = 0.45

    yy, xx = np.mgrid[:size, :size]
    radius = np.hypot(yy - centre, xx - centre)
    q_map = radius / centre * q_max_edge

    intensity = np.interp(q_map, q_curve, i_curve,
                          left=i_curve[0], right=i_curve[-1])
    counts = rng.poisson(np.clip(intensity * 30.0, 0.0, None)).astype(float)

    counts[radius < 0.045 * size] = 0.0                      # beamstop
    counts[(np.abs(xx - centre) < 3) & (yy > centre)] = 0.0  # its support arm
    return counts


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _tiff_description(pixels_per_micron: float, instrument: str) -> str:
    """The calibration string, in the layout the microscope vendors use."""
    return (f"{instrument} XpixCal={pixels_per_micron:.6f}"
            f"YpixCal={pixels_per_micron:.6f}Unit=um")


def write_tiff(path: Path, array: np.ndarray, pixels_per_micron: float,
               instrument: str) -> bool:
    """Write *array* as an 8-bit TIFF carrying its pixel calibration.

    Returns False when Pillow is absent, so a minimal install still builds a
    project — without micrographs, rather than not at all.
    """
    try:
        from PIL import Image
    except ImportError:                      # pragma: no cover - Pillow is an extra
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array.astype(np.uint8)).save(
        path, description=_tiff_description(pixels_per_micron, instrument))
    return True


__all__ = [
    "TEM_PIXELS_PER_MICRON", "SEM_PIXELS_PER_MICRON", "TOMO_NM_PER_VOXEL",
    "TEM_BANNER_ROWS", "tem_image", "sem_image", "tomo_volume",
    "saxs2d_pattern", "write_tiff",
]
