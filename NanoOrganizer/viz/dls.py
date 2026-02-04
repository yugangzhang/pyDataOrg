#!/usr/bin/env python3
"""
DLS size-distribution plotter.

Expects the dict produced by ``DLSLoader.load()``:

    times      – 1D  (n_times,)
    diameters  – 1D  (n_diameters,)
    intensity  – 2D  (n_times, n_diameters)

Plot types
----------
size_dist  – distribution at a selected time (log x-axis).
kinetics   – intensity-weighted mean diameter vs time.
heatmap    – 2-D colour map (time × diameter).
"""

import numpy as np
from typing import Any, Dict

from NanoOrganizer.viz.base import BasePlotter


class DLSPlotter(BasePlotter):
    """Plotter for DLS size-distribution data."""

    data_type            = "dls"
    default_plot_type    = "size_dist"
    available_plot_types = ["size_dist", "kinetics", "heatmap"]

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def plot(self, data: Dict[str, Any], plot_type: str = None,
             ax=None, **kwargs):
        if plot_type is None:
            plot_type = self.default_plot_type

        ax = self._get_axes(ax, **kwargs)

        dispatch = {
            'size_dist': self._size_dist,
            'kinetics':  self._kinetics,
            'heatmap':   self._heatmap,
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

    def _size_dist(self, data, ax, **kwargs):
        """Size distribution at one time point (log x-axis)."""
        times     = data['times']
        diameters = data['diameters']
        intensity = data['intensity']

        time_point = kwargs.get('time_point')
        if time_point is None:
            time_point = times[len(times) // 2]
        idx          = int(np.argmin(np.abs(times - time_point)))
        closest_time = times[idx]

        ax.semilogx(diameters, intensity[idx], linewidth=2,
                    label=f't = {closest_time:.0f} s')
        ax.set_xlabel('Diameter (nm)', fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'DLS Size Distribution at t = {closest_time:.0f} s'),
                     fontsize=13)
        ax.legend()
        ax.grid(True, alpha=0.3)

    def _kinetics(self, data, ax, **kwargs):
        """Intensity-weighted mean diameter vs time."""
        times     = data['times']
        diameters = data['diameters']
        intensity = data['intensity']

        mean_d = []
        for i in range(len(times)):
            total = intensity[i].sum()
            mean_d.append(
                float(np.sum(diameters * intensity[i]) / total) if total > 0 else np.nan
            )

        ax.plot(times, mean_d, 'o-', linewidth=2, markersize=6)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Mean Diameter (nm)', fontsize=12)
        ax.set_title(kwargs.get('title', 'Particle Growth Kinetics'), fontsize=13)
        ax.grid(True, alpha=0.3)

    def _heatmap(self, data, ax, **kwargs):
        """2-D colour map (time × diameter)."""
        import matplotlib.pyplot as plt

        times     = data['times']
        diameters = data['diameters']
        intensity = data['intensity']

        im = ax.pcolormesh(diameters, times, intensity,
                           shading='auto', cmap='viridis')
        ax.set_xlabel('Diameter (nm)', fontsize=12)
        ax.set_ylabel('Time (s)', fontsize=12)
        ax.set_title(kwargs.get('title', 'DLS Size Evolution'), fontsize=13)
        plt.colorbar(im, ax=ax, label='Intensity (a.u.)')
