#!/usr/bin/env python3
"""Synthetic SAXS 1-D time-series: spherical form factor with growing radius."""

import numpy as np
from typing import Tuple, List


def simulate_saxs_time_series_data(
    q_range: Tuple[float, float] = (0.01, 0.5),
    n_points: int = 200,
    time_points: List[float] = None,
    initial_size_nm: float = 2.0,
    final_size_nm: float = 10.0,
    growth_rate: float = 1.0,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Simulate SAXS profiles using a spherical form factor.

    Returns long-format lists (times, q, intensity).
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]

    q = np.linspace(q_range[0], q_range[1], n_points)

    times_out     = []
    q_out         = []
    intensity_out = []

    for t in time_points:
        growth_fraction = 1 - np.exp(-growth_rate * t / 300)
        radius_nm = initial_size_nm + (final_size_nm - initial_size_nm) * growth_fraction
        radius_A  = radius_nm * 10 / 2   # nm → Å, diameter → radius

        qr = q * radius_A
        form_factor = np.where(
            qr > 0.01,
            (3 * (np.sin(qr) - qr * np.cos(qr)) / qr**3) ** 2,
            1.0,
        )

        particle_volume      = (4 / 3) * np.pi * radius_A**3
        concentration_factor = 1 + 2 * growth_fraction
        intensity = 1000 * particle_volume * concentration_factor * form_factor

        noise     = np.random.normal(0, 0.05 * np.sqrt(intensity + 1), n_points)
        intensity = np.maximum(intensity + noise, 0.1)

        for q_val, I_val in zip(q, intensity):
            times_out.append(t)
            q_out.append(q_val)
            intensity_out.append(I_val)

    return times_out, q_out, intensity_out
