#!/usr/bin/env python3
"""Synthetic UV-Vis time-series: plasmon peak growth + red-shift."""

import numpy as np
from typing import Tuple, List


def simulate_uvvis_time_series_data(
    wavelength_range: Tuple[float, float] = (200, 800),
    n_wavelengths: int = 300,
    time_points: List[float] = None,
    initial_peak: float = 480,
    final_peak: float = 530,
    growth_rate: float = 1.0,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Simulate UV-Vis spectra showing nanoparticle growth.

    Returns long-format lists (times, wavelengths, absorbance) suitable
    for ``save_time_series_to_csv``.
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]

    wavelengths = np.linspace(wavelength_range[0], wavelength_range[1], n_wavelengths)

    times_out       = []
    wavelengths_out = []
    absorbance_out  = []

    for t in time_points:
        growth_fraction = 1 - np.exp(-growth_rate * t / 300)

        peak_center = initial_peak + (final_peak - initial_peak) * growth_fraction
        peak_height = 1.5 * growth_fraction
        peak_width  = 50 + 30 * (1 - growth_fraction)

        baseline   = 0.05 + 0.05 * growth_fraction
        absorbance = baseline + peak_height * np.exp(
            -((wavelengths - peak_center) ** 2) / (2 * peak_width ** 2)
        )

        noise_level = 0.02 * (1 + 0.5 / (growth_fraction + 0.1))
        absorbance += np.random.normal(0, noise_level, n_wavelengths)
        absorbance  = np.maximum(absorbance, 0)

        for wl, ab in zip(wavelengths, absorbance):
            times_out.append(t)
            wavelengths_out.append(wl)
            absorbance_out.append(ab)

    return times_out, wavelengths_out, absorbance_out
