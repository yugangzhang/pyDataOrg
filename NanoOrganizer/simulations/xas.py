#!/usr/bin/env python3
"""
Synthetic XAS (Cu K-edge XANES + EXAFS) time-series.

Physics model
-------------
* Pre-edge   – small Gaussian feature (d → s transition); grows during
               reduction.
* Edge jump  – error-function step at E₀.
* White line – Gaussian peak just above E₀; strong for Cu²⁺, disappears
               for Cu⁰.
* EXAFS      – damped sinusoidal oscillation that appears as metallic
               Cu clusters form.

During the synthesis Cu²⁺ is reduced to Cu⁰:
    edge position shifts ~3 eV to lower energy,
    white-line intensity drops,
    EXAFS amplitude grows.
"""

import numpy as np
from typing import Tuple, List


def simulate_xas_time_series_data(
    energy_range: Tuple[float, float] = (8850, 9100),
    n_points: int = 300,
    time_points: List[float] = None,
    edge_energy_initial: float = 8982.0,   # Cu²⁺
    edge_energy_final: float = 8979.0,     # Cu⁰
    growth_rate: float = 1.0,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Simulate Cu K-edge XAS spectra during Cu²⁺ → Cu⁰ reduction.

    Returns long-format lists (times, energy, absorption) suitable
    for ``save_time_series_to_csv``.

    Parameters
    ----------
    energy_range : tuple
        (min, max) photon energy in eV.
    n_points : int
        Number of energy points per spectrum.
    time_points : list
        Time stamps in seconds.
    edge_energy_initial, edge_energy_final : float
        Cu²⁺ and Cu⁰ K-edge positions (eV).
    growth_rate : float
        Reduction rate constant.
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]

    from scipy.special import erf

    energies = np.linspace(energy_range[0], energy_range[1], n_points)

    times_out     = []
    energy_out    = []
    absorption_out = []

    for t in time_points:
        reduction_frac = 1 - np.exp(-growth_rate * t / 300)

        E0 = edge_energy_initial + (edge_energy_final - edge_energy_initial) * reduction_frac

        # --- pre-edge (small feature ~7 eV below edge) ---
        pre_edge_height = 0.03 + 0.05 * reduction_frac
        pre_edge = pre_edge_height * np.exp(
            -((energies - (E0 - 7))**2) / (2 * 1.5**2)
        )

        # --- edge jump (error function 0 → 1) ---
        edge_jump = 0.5 * (1 + erf((energies - E0) / 1.5))

        # --- white line (Gaussian, strong for Cu²⁺) ---
        wl_height = 0.6 * (1 - 0.85 * reduction_frac)
        white_line = wl_height * np.exp(
            -((energies - (E0 + 3))**2) / (2 * 1.0**2)
        )

        # --- EXAFS oscillations (only well above edge) ---
        k = np.sqrt(np.maximum(energies - E0, 0) / 3.81)   # Å⁻¹
        R = 3.6                                              # Cu–Cu  Å
        exafs_amp = 0.15 * reduction_frac
        damping   = np.exp(-2 * k**2 * 0.005)
        exafs     = exafs_amp * np.sin(2 * k * R + 0.5) * damping / (k + 0.01)
        exafs    *= (energies > E0 + 10)   # switch on 10 eV above edge

        absorption = pre_edge + edge_jump + white_line + exafs

        # noise
        absorption += np.random.normal(0, 0.008, n_points)

        for e, ab in zip(energies, absorption):
            times_out.append(t)
            energy_out.append(e)
            absorption_out.append(ab)

    return times_out, energy_out, absorption_out
