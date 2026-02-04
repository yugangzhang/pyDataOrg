#!/usr/bin/env python3
"""
UV-Vis spectroscopy plotter.

Expects the dict produced by ``UVVisLoader.load()``:

    times        – 1D  (n_times,)
    wavelengths  – 1D  (n_wavelengths,)
    absorbance   – 2D  (n_times, n_wavelengths)

Plot types
----------
spectrum  – single spectrum at a selected time point.
kinetics  – absorbance vs time at a selected wavelength.
heatmap   – 2-D colour map (time × wavelength).
"""

import numpy as np
from typing import Any, Dict

from NanoOrganizer.viz.base import BasePlotter


class UVVisPlotter(BasePlotter):
    """Plotter for UV-Vis spectroscopy data."""

    data_type            = "uvvis"
    default_plot_type    = "spectrum"
    available_plot_types = ["spectrum", "kinetics", "heatmap"]

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def plot(self, data: Dict[str, Any], plot_type: str = None,
             ax=None, **kwargs):
        if plot_type is None:
            plot_type = self.default_plot_type

        ax = self._get_axes(ax, **kwargs)

        dispatch = {
            'spectrum': self._spectrum,
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

    def _spectrum(self, data, ax, **kwargs):
        """Single spectrum at one time point."""
        times       = data['times']
        wavelengths = data['wavelengths']
        absorbance  = data['absorbance']          # (n_times, n_wl)

        time_point = kwargs.get('time_point')
        if time_point is None:
            time_point = times[len(times) // 2]
        idx          = int(np.argmin(np.abs(times - time_point)))
        closest_time = times[idx]

        ax.plot(wavelengths, absorbance[idx], linewidth=2,
                label=f't = {closest_time:.0f} s')
        ax.set_xlabel('Wavelength (nm)', fontsize=12)
        ax.set_ylabel('Absorbance (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'UV-Vis Spectrum at t = {closest_time:.0f} s'),
                     fontsize=13)
        ax.legend()
        ax.grid(True, alpha=0.3)

    def _kinetics(self, data, ax, **kwargs):
        """Absorbance vs time at a single wavelength."""
        times       = data['times']
        wavelengths = data['wavelengths']
        absorbance  = data['absorbance']          # (n_times, n_wl)

        wavelength = kwargs.get('wavelength', 520)
        wl_idx     = int(np.argmin(np.abs(wavelengths - wavelength)))
        closest_wl = wavelengths[wl_idx]

        ax.plot(times, absorbance[:, wl_idx], 'o-', linewidth=2, markersize=6)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Absorbance (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'Growth Kinetics at λ = {closest_wl:.0f} nm'),
                     fontsize=13)
        ax.grid(True, alpha=0.3)

    def _heatmap(self, data, ax, **kwargs):
        """2-D colour map of absorbance over time and wavelength."""
        import matplotlib.pyplot as plt

        times       = data['times']
        wavelengths = data['wavelengths']
        absorbance  = data['absorbance']          # (n_times, n_wl)

        im = ax.pcolormesh(wavelengths, times, absorbance,
                           shading='auto', cmap='viridis')
        ax.set_xlabel('Wavelength (nm)', fontsize=12)
        ax.set_ylabel('Time (s)', fontsize=12)
        ax.set_title(kwargs.get('title', 'UV-Vis Evolution'), fontsize=13)
        plt.colorbar(im, ax=ax, label='Absorbance (a.u.)')
