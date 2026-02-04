#!/usr/bin/env python3
"""
Synthetic DLS size-distribution time-series.

Model: volume-weighted log-normal distribution.  Mean diameter grows
with exponential saturation; the distribution narrows over time
(decreasing polydispersity).
"""

import numpy as np
from typing import Tuple, List


def simulate_dls_time_series_data(
    diameter_range: Tuple[float, float] = (0.5, 200.0),
    n_points: int = 200,
    time_points: List[float] = None,
    initial_mean_nm: float = 5.0,
    final_mean_nm: float = 50.0,
    initial_sigma: float = 0.8,   # log-space std  (broad)
    final_sigma: float = 0.4,     # log-space std  (narrow)
    growth_rate: float = 1.0,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Simulate DLS size distributions for a growing nanoparticle synthesis.

    Returns long-format lists (times, diameters, intensity) suitable
    for ``save_time_series_to_csv``.

    Parameters
    ----------
    diameter_range : tuple
        (min, max) diameter in nm.
    n_points : int
        Number of diameter bins.
    time_points : list
        Time stamps in seconds.
    initial_mean_nm, final_mean_nm : float
        Mean diameter at t = 0 and t → ∞.
    initial_sigma, final_sigma : float
        Log-space standard deviation (controls width / PDI).
    growth_rate : float
        Saturation rate constant (higher → faster).
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]

    diameters = np.linspace(diameter_range[0], diameter_range[1], n_points)

    times_out     = []
    diameters_out = []
    intensity_out = []

    for t in time_points:
        growth_fraction = 1 - np.exp(-growth_rate * t / 300)

        mean_d = initial_mean_nm + (final_mean_nm - initial_mean_nm) * growth_fraction
        sigma  = initial_sigma  + (final_sigma  - initial_sigma)  * growth_fraction
        mu     = np.log(mean_d)

        # Volume-weighted log-normal  I(d) ∝ d² · exp(-(ln d − μ)² / 2σ²)
        log_d     = np.log(diameters)
        intensity = diameters**2 * np.exp(-((log_d - mu)**2) / (2 * sigma**2))

        # Normalise
        norm = np.trapz(intensity, diameters)
        if norm > 0:
            intensity /= norm

        # Noise
        intensity += np.random.normal(0, 0.001, n_points)
        intensity  = np.maximum(intensity, 0)

        for d, I in zip(diameters, intensity):
            times_out.append(t)
            diameters_out.append(d)
            intensity_out.append(I)

    return times_out, diameters_out, intensity_out
