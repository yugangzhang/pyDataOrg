#!/usr/bin/env python3
"""
WAXS 1-D plotter.

Expects the dict produced by ``WAXSLoader.load()``:

    times      – 1D  (n_times,)
    two_theta  – 1D  (n_2theta,)
    intensity  – 2D  (n_times, n_2theta)

Plot types
----------
pattern   – diffraction pattern at a selected time.
kinetics  – peak intensity vs time at a selected 2θ.
heatmap   – 2-D colour map (time × 2θ).
"""

import numpy as np
from typing import Any, Dict

from NanoOrganizer.viz.base import BasePlotter


class WAXSPlotter(BasePlotter):
    """Plotter for WAXS 1-D data."""

    data_type            = "waxs"
    default_plot_type    = "pattern"
    available_plot_types = ["pattern", "kinetics", "heatmap"]

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def plot(self, data: Dict[str, Any], plot_type: str = None,
             ax=None, **kwargs):
        if plot_type is None:
            plot_type = self.default_plot_type

        ax = self._get_axes(ax, **kwargs)

        dispatch = {
            'pattern':  self._pattern,
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

    def _pattern(self, data, ax, **kwargs):
        """Diffraction pattern at one time point."""
        times     = data['times']
        two_theta = data['two_theta']
        intensity = data['intensity']              # (n_times, n_2theta)

        time_point = kwargs.get('time_point')
        if time_point is None:
            time_point = times[len(times) // 2]
        idx          = int(np.argmin(np.abs(times - time_point)))
        closest_time = times[idx]

        ax.plot(two_theta, intensity[idx], linewidth=2)
        ax.set_xlabel('2θ (degrees)', fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'WAXS Pattern at t = {closest_time:.0f} s'),
                     fontsize=13)
        ax.grid(True, alpha=0.3)

    def _kinetics(self, data, ax, **kwargs):
        """Peak intensity vs time at one 2θ value."""
        times     = data['times']
        two_theta = data['two_theta']
        intensity = data['intensity']              # (n_times, n_2theta)

        tt_value  = kwargs.get('two_theta_value', 30.0)
        tt_idx    = int(np.argmin(np.abs(two_theta - tt_value)))
        closest_tt = two_theta[tt_idx]

        ax.plot(times, intensity[:, tt_idx], 'o-', linewidth=2, markersize=6)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'Peak Growth at 2θ = {closest_tt:.1f}°'),
                     fontsize=13)
        ax.grid(True, alpha=0.3)

    def _heatmap(self, data, ax, **kwargs):
        """2-D colour map of intensity over time and 2θ."""
        import matplotlib.pyplot as plt

        times     = data['times']
        two_theta = data['two_theta']
        intensity = data['intensity']              # (n_times, n_2theta)

        im = ax.pcolormesh(two_theta, times, intensity,
                           shading='auto', cmap='viridis')
        ax.set_xlabel('2θ (degrees)', fontsize=12)
        ax.set_ylabel('Time (s)', fontsize=12)
        ax.set_title(kwargs.get('title', 'WAXS Crystallization'), fontsize=13)
        plt.colorbar(im, ax=ax, label='Intensity (a.u.)')
