#!/usr/bin/env python3
"""
XAS plotter – XANES and EXAFS spectra.

Expects the dict produced by ``XASLoader.load()``:

    times      – 1D  (n_times,)
    energy     – 1D  (n_energy,)   in eV
    absorption – 2D  (n_times, n_energy)

Plot types
----------
xanes     – absorption spectrum at a selected time.
kinetics  – absorption at a selected energy vs time.
heatmap   – 2-D colour map (time × energy).
"""

import numpy as np
from typing import Any, Dict

from NanoOrganizer.viz.base import BasePlotter


class XASPlotter(BasePlotter):
    """Plotter for XAS (XANES / EXAFS) data."""

    data_type            = "xas"
    default_plot_type    = "xanes"
    available_plot_types = ["xanes", "kinetics", "heatmap"]

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def plot(self, data: Dict[str, Any], plot_type: str = None,
             ax=None, **kwargs):
        if plot_type is None:
            plot_type = self.default_plot_type

        ax = self._get_axes(ax, **kwargs)

        dispatch = {
            'xanes':    self._xanes,
            'kinetics': self._kinetics,
            'heatmap':  self._heatmap,
        }
        if plot_type not in dispatch:
            raise ValueError(
                f"Unknown plot_type '{plot_type}'. "
                f"Available: {self.available_plot_types}"
            )
        dispatch[plot_type](data, ax, **kwargs)
        return ax

    # ------------------------------------------------------------------
    # individual plot types
    # ------------------------------------------------------------------

    def _xanes(self, data, ax, **kwargs):
        """XANES spectrum at one time point."""
        times      = data['times']
        energy     = data['energy']
        absorption = data['absorption']

        time_point = kwargs.get('time_point')
        if time_point is None:
            time_point = times[len(times) // 2]
        idx          = int(np.argmin(np.abs(times - time_point)))
        closest_time = times[idx]

        ax.plot(energy, absorption[idx], linewidth=2,
                label=f't = {closest_time:.0f} s')
        ax.set_xlabel('Energy (eV)', fontsize=12)
        ax.set_ylabel('Absorption (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'XAS Spectrum at t = {closest_time:.0f} s'),
                     fontsize=13)
        ax.legend()
        ax.grid(True, alpha=0.3)

    def _kinetics(self, data, ax, **kwargs):
        """Absorption at one energy vs time."""
        times      = data['times']
        energy     = data['energy']
        absorption = data['absorption']

        energy_value = kwargs.get('energy')
        if energy_value is None:
            energy_value = energy[len(energy) // 2]
        e_idx     = int(np.argmin(np.abs(energy - energy_value)))
        closest_e = energy[e_idx]

        ax.plot(times, absorption[:, e_idx], 'o-', linewidth=2, markersize=6)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Absorption (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'Absorption Kinetics at E = {closest_e:.1f} eV'),
                     fontsize=13)
        ax.grid(True, alpha=0.3)

    def _heatmap(self, data, ax, **kwargs):
        """2-D colour map (time × energy)."""
        import matplotlib.pyplot as plt

        times      = data['times']
        energy     = data['energy']
        absorption = data['absorption']

        im = ax.pcolormesh(energy, times, absorption,
                           shading='auto', cmap='viridis')
        ax.set_xlabel('Energy (eV)', fontsize=12)
        ax.set_ylabel('Time (s)', fontsize=12)
        ax.set_title(kwargs.get('title', 'XAS Evolution'), fontsize=13)
        plt.colorbar(im, ax=ax, label='Absorption (a.u.)')
