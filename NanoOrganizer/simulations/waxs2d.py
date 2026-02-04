#!/usr/bin/env python3
"""
Synthetic 2-D WAXS detector images.

Physics model: amorphous background + Bragg rings at specified q
positions.  Rings sharpen and grow as crystallinity increases (same
kinetic model as the 1-D WAXS simulation).

Default peak q-values correspond to Cu₂O (111), (200), (220).

Files are saved as ``.npy`` (float64).
"""

import numpy as np
from pathlib import Path
from typing import List, Tuple, Dict


# Cu₂O reference q-positions (Å⁻¹) and relative max intensities
_CU2O_PEAKS_Q = [(2.09, 100), (2.95, 80), (4.16, 60)]


def simulate_waxs2d_time_series_data(
    output_dir: Path,
    n_pixels: int = 256,
    time_points: List[float] = None,
    peaks: List[Tuple[float, float]] = None,
    crystallization_rate: float = 1.0,
    pixel_size_mm: float = 0.172,
    sdd_mm: float = 200.0,          # shorter distance for WAXS (20 cm)
    wavelength_A: float = 1.0,
) -> Tuple[List[Path], Dict]:
    """
    Generate 2-D WAXS detector images and save as ``.npy`` files.

    Parameters
    ----------
    output_dir : Path
        Directory for output files.
    n_pixels : int
        Detector size (square).
    time_points : list
        Time stamps in seconds.
    peaks : list of (q, max_intensity)
        Bragg peak positions in Å⁻¹ and their maximum intensities.
        Defaults to Cu₂O (111), (200), (220).
    crystallization_rate : float
        How fast crystallinity develops.
    pixel_size_mm, sdd_mm, wavelength_A : float
        Detector geometry / beam parameters.

    Returns
    -------
    npy_files : list of Path
    calibration : dict
        Pass as ``**calibration`` to ``link_data()``.
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]
    if peaks is None:
        peaks = _CU2O_PEAKS_Q

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2-D q map (exact, not small-angle – WAXS covers large angles)
    cx, cy  = n_pixels / 2.0, n_pixels / 2.0
    y, x    = np.mgrid[0:n_pixels, 0:n_pixels]
    r_mm    = np.sqrt((x - cx)**2 + (y - cy)**2) * pixel_size_mm
    two_theta_rad = np.arctan(r_mm / sdd_mm)
    theta_rad     = two_theta_rad / 2.0
    q_2d          = 4 * np.pi * np.sin(theta_rad) / wavelength_A   # Å⁻¹

    npy_files: List[Path] = []

    for idx, t in enumerate(time_points):
        cryst_fraction = 1 - np.exp(-crystallization_rate * t / 300)

        # Amorphous background (decreases with crystallinity)
        intensity = np.ones((n_pixels, n_pixels)) * 20 * (1 - 0.7 * cryst_fraction)

        # Bragg rings
        for q_peak, max_height in peaks:
            peak_height = max_height * cryst_fraction
            peak_width  = 0.08 - 0.04 * cryst_fraction   # Å⁻¹  (sharpens)
            intensity  += peak_height * np.exp(
                -((q_2d - q_peak)**2) / (2 * peak_width**2)
            )

        # Poisson noise
        intensity = np.random.poisson(np.maximum(intensity, 0)).astype(float)

        # Save
        npy_path = output_dir / f"waxs2d_{idx + 1:03d}.npy"
        np.save(npy_path, intensity)
        npy_files.append(npy_path)
        print(f"  ✓ Created 2D WAXS image at t={t}s: {npy_path.name}")

    calibration = {
        'pixel_size_mm': pixel_size_mm,
        'sdd_mm':        sdd_mm,
        'wavelength_A':  wavelength_A,
    }
    return npy_files, calibration
