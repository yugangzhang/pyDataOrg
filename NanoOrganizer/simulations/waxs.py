#!/usr/bin/env python3
"""Synthetic WAXS 1-D time-series: amorphous → crystalline transition."""

import numpy as np
from typing import Tuple, List


def simulate_waxs_time_series_data(
    two_theta_range: Tuple[float, float] = (10, 80),
    n_points: int = 500,
    time_points: List[float] = None,
    peaks: List[Tuple[float, float]] = None,
    crystallization_rate: float = 1.0,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Simulate WAXS patterns showing amorphous → crystalline transition.

    Default peaks correspond to Cu₂O.  Returns long-format lists.
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]

    if peaks is None:
        peaks = [(30.0, 100), (35.0, 80), (62.0, 60)]   # Cu₂O

    two_theta = np.linspace(two_theta_range[0], two_theta_range[1], n_points)

    times_out     = []
    two_theta_out = []
    intensity_out = []

    for t in time_points:
        cryst_fraction = 1 - np.exp(-crystallization_rate * t / 300)

        intensity = np.ones(n_points) * 20 * (1 - 0.7 * cryst_fraction)

        for peak_pos, peak_max_height in peaks:
            peak_height = peak_max_height * cryst_fraction
            peak_width  = 3.0 - 1.5 * cryst_fraction
            intensity += peak_height * np.exp(
                -((two_theta - peak_pos) ** 2) / (2 * peak_width ** 2)
            )

        noise     = np.random.normal(0, 2 + 0.5 * np.sqrt(intensity), n_points)
        intensity = np.maximum(intensity + noise, 0)

        for tt, I_val in zip(two_theta, intensity):
            times_out.append(t)
            two_theta_out.append(tt)
            intensity_out.append(I_val)

    return times_out, two_theta_out, intensity_out
