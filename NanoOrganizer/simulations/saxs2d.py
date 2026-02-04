#!/usr/bin/env python3
"""
Synthetic 2-D SAXS detector images.

Physics model: isotropic scattering from monodisperse spheres mapped onto
a flat detector.  A circular beamstop masks the central pixels.

Files are saved as ``.npy`` (float64) to preserve precision.
"""

import numpy as np
from pathlib import Path
from typing import List, Tuple, Dict


def simulate_saxs2d_time_series_data(
    output_dir: Path,
    n_pixels: int = 256,
    time_points: List[float] = None,
    initial_size_nm: float = 2.0,
    final_size_nm: float = 10.0,
    growth_rate: float = 1.0,
    pixel_size_mm: float = 0.172,   # typical Eiger pixel
    sdd_mm: float = 3000.0,         # 3 m sample–detector distance
    wavelength_A: float = 1.0,      # X-ray wavelength in Å
    beamstop_radius: int = 8,       # pixels masked at centre
) -> Tuple[List[Path], Dict]:
    """
    Generate 2-D SAXS detector images and save as ``.npy`` files.

    Parameters
    ----------
    output_dir : Path
        Directory for the output ``.npy`` files.
    n_pixels : int
        Detector size (n_pixels × n_pixels square).
    time_points : list
        Time stamps in seconds.
    initial_size_nm, final_size_nm : float
        Particle diameter at t = 0 and t → ∞.
    growth_rate : float
        Saturation rate constant.
    pixel_size_mm : float
        Physical pixel pitch (mm).
    sdd_mm : float
        Sample-to-detector distance (mm).
    wavelength_A : float
        X-ray wavelength (Å).
    beamstop_radius : int
        Central pixels to set to zero (beamstop).

    Returns
    -------
    npy_files : list of Path
        Paths to the saved ``.npy`` files.
    calibration : dict
        ``{'pixel_size_mm': …, 'sdd_mm': …, 'wavelength_A': …}``
        – pass directly as ``**calibration`` to ``link_data()``.
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pre-compute 2-D q map
    cx, cy = n_pixels / 2.0, n_pixels / 2.0
    y, x   = np.mgrid[0:n_pixels, 0:n_pixels]
    r_mm   = np.sqrt((x - cx)**2 + (y - cy)**2) * pixel_size_mm
    q_2d   = 2 * np.pi * r_mm / (sdd_mm * wavelength_A)   # Å⁻¹  (small-angle)

    # Beamstop mask
    r_pix  = np.sqrt((x - cx)**2 + (y - cy)**2)
    beamstop = r_pix < beamstop_radius

    npy_files: List[Path] = []

    for idx, t in enumerate(time_points):
        growth_fraction = 1 - np.exp(-growth_rate * t / 300)
        radius_nm = initial_size_nm + (final_size_nm - initial_size_nm) * growth_fraction
        radius_A  = radius_nm * 10 / 2   # nm diameter → Å radius

        # Spherical form factor on 2-D detector
        qr     = q_2d * radius_A
        safe_qr = np.where(qr > 0.01, qr, 1.0)   # avoid 0/0 in both branches
        form_factor = np.where(
            qr > 0.01,
            (3 * (np.sin(safe_qr) - safe_qr * np.cos(safe_qr)) / safe_qr**3) ** 2,
            1.0,
        )

        particle_volume      = (4 / 3) * np.pi * radius_A**3
        concentration_factor = 1 + 2 * growth_fraction
        intensity = 1000 * particle_volume * concentration_factor * form_factor

        # Poisson noise
        intensity = np.random.poisson(np.maximum(intensity, 0)).astype(float)

        # Apply beamstop
        intensity[beamstop] = 0.0

        # Save
        npy_path = output_dir / f"saxs2d_{idx + 1:03d}.npy"
        np.save(npy_path, intensity)
        npy_files.append(npy_path)
        print(f"  ✓ Created 2D SAXS image at t={t}s: {npy_path.name}")

    calibration = {
        'pixel_size_mm': pixel_size_mm,
        'sdd_mm':        sdd_mm,
        'wavelength_A':  wavelength_A,
    }
    return npy_files, calibration
