#!/usr/bin/env python3
"""
Profiles — reductions that turn a frame into a curve, as kernels.

These used to be computed *inside* plotting code: the 2D detector plotters
took an azimuthal average on the way to drawing it, and the DLS plotter took
an intensity-weighted mean diameter. A number computed inside a plot cannot be
checked, kept or reused, so they live here as plain functions of arrays and
the plots draw what these return (``docs/kernel_adapter_rule.md``).

``azimuthal_average(image)``   radial mean of a 2D array, in pixel radius
``radius_to_q(r, ...)``        pixel radius → scattering vector, in 1/Å
``radius_to_two_theta(r, ...)`` pixel radius → scattering angle, in degrees
``weighted_mean(x, weights)``  one weighted mean per row of *weights*
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def azimuthal_average(image, center: Optional[Tuple[float, float]] = None,
                      n_bins: Optional[int] = None
                      ) -> Tuple[np.ndarray, np.ndarray]:
    """Radial (azimuthal) average of a 2D array. **Kernel.**

    Returns ``(r, profile)``: bin-centre radii in pixels and the mean
    intensity in each bin. *center* is ``(x, y)`` in pixels and defaults to
    the middle of the array; *n_bins* defaults to half the shorter side. An
    empty bin reports 0, as it always has.
    """
    image = np.asarray(image, dtype=float)
    if image.ndim != 2:
        raise ValueError(f"expected a 2D image, got shape {image.shape}")

    ny, nx = image.shape
    if center is None:
        center = (nx / 2.0, ny / 2.0)

    y, x = np.indices(image.shape)
    r = np.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2)

    if n_bins is None:
        n_bins = min(nx, ny) // 2
    if n_bins < 1:
        raise ValueError(f"n_bins must be at least 1, got {n_bins}")

    edges = np.linspace(0, r.max(), n_bins + 1)
    index = np.clip(np.digitize(r.ravel(), edges) - 1, 0, n_bins - 1)
    # The outermost pixel sits exactly on the last edge; digitize puts it one
    # bin past the end, and it belongs in the last bin.
    total = np.bincount(index, weights=image.ravel(), minlength=n_bins)
    count = np.bincount(index, minlength=n_bins)
    profile = np.divide(total, count, out=np.zeros(n_bins), where=count > 0)
    return (edges[:-1] + edges[1:]) / 2.0, profile


def radius_to_q(r_pixels, pixel_size_mm: float, sdd_mm: float,
                wavelength_A: float) -> np.ndarray:
    """Pixel radius to scattering vector *q* in 1/Å. **Kernel.**

    The small-angle form, ``q = 2π r p / (L λ)`` — the one the 2D plotters
    have always used. Past a few degrees use the exact
    ``4π sin(θ) / λ`` instead.
    """
    if sdd_mm <= 0 or wavelength_A <= 0:
        raise ValueError("sdd_mm and wavelength_A must be positive")
    r = np.asarray(r_pixels, dtype=float)
    return 2 * np.pi * r * pixel_size_mm / (sdd_mm * wavelength_A)


def radius_to_two_theta(r_pixels, pixel_size_mm: float,
                        sdd_mm: float) -> np.ndarray:
    """Pixel radius to scattering angle 2θ in degrees. **Kernel.**"""
    if sdd_mm <= 0:
        raise ValueError("sdd_mm must be positive")
    r_mm = np.asarray(r_pixels, dtype=float) * pixel_size_mm
    return np.degrees(np.arctan(r_mm / sdd_mm))


def weighted_mean(x, weights) -> np.ndarray:
    """One weighted mean of *x* per row of *weights*. **Kernel.**

    ``weights`` is ``(n_rows, len(x))`` — a size distribution per time point,
    say — and the result has one value per row. A row whose weights sum to
    zero has no mean and reports NaN rather than 0.
    """
    x = np.asarray(x, dtype=float)
    weights = np.atleast_2d(np.asarray(weights, dtype=float))
    if weights.shape[1] != x.size:
        raise ValueError(
            f"each row of weights needs {x.size} values, got {weights.shape[1]}")
    total = weights.sum(axis=1)
    weighted = (weights * x).sum(axis=1)
    return np.divide(weighted, total, out=np.full(total.shape, np.nan),
                     where=total > 0)


__all__ = ["azimuthal_average", "radius_to_q", "radius_to_two_theta",
           "weighted_mean"]
