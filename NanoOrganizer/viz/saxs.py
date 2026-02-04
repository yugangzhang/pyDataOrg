#!/usr/bin/env python3
"""
SAXS 1-D plotter.

Expects the dict produced by ``SAXSLoader.load()``:

    times      – 1D  (n_times,)
    q          – 1D  (n_q,)
    intensity  – 2D  (n_times, n_q)

Plot types
----------
profile   – I(q) at a selected time (log-log by default).
kinetics  – I(t) at a selected q value.
heatmap   – 2-D colour map (time × q).
"""

import numpy as np
from typing import Any, Dict

from NanoOrganizer.viz.base import BasePlotter


class SAXSPlotter(BasePlotter):
    """Plotter for SAXS 1-D data."""

    data_type            = "saxs"
    default_plot_type    = "profile"
    available_plot_types = ["profile", "kinetics", "heatmap"]

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def plot(self, data: Dict[str, Any], plot_type: str = None,
             ax=None, **kwargs):
        if plot_type is None:
            plot_type = self.default_plot_type

        ax = self._get_axes(ax, **kwargs)

        dispatch = {
            'profile':  self._profile,
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

    def _profile(self, data, ax, **kwargs):
        """I(q) at one time point."""
        times     = data['times']
        q         = data['q']
        intensity = data['intensity']              # (n_times, n_q)

        time_point = kwargs.get('time_point')
        if time_point is None:
            time_point = times[len(times) // 2]
        idx          = int(np.argmin(np.abs(times - time_point)))
        closest_time = times[idx]

        loglog = kwargs.get('loglog', True)
        legend = kwargs.get('legend', '')
        plot_fn = ax.loglog if loglog else ax.plot
        plot_fn(q, intensity[idx], 'o-', linewidth=2, markersize=4, label=legend)

        ax.set_xlabel('q (1/Å)', fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'SAXS Profile at t = {closest_time:.0f} s'),
                     fontsize=13)
        ax.grid(True, alpha=0.3)
        if legend:
            ax.legend(loc='best', fontsize=kwargs.get('legend_fontsize', 8))

    def _kinetics(self, data, ax, **kwargs):
        """Intensity vs time at a single q."""
        times     = data['times']
        q         = data['q']
        intensity = data['intensity']              # (n_times, n_q)

        q_value  = kwargs.get('q_value', 0.02)
        q_idx    = int(np.argmin(np.abs(q - q_value)))
        closest_q = q[q_idx]

        ax.plot(times, intensity[:, q_idx], 'o-', linewidth=2, markersize=6)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'Growth at q = {closest_q:.3f} 1/Å'),
                     fontsize=13)
        ax.grid(True, alpha=0.3)

    def _heatmap(self, data, ax, **kwargs):
        """2-D colour map of intensity over time and q."""
        import matplotlib.pyplot as plt

        times     = data['times']
        q         = data['q']
        intensity = data['intensity']              # (n_times, n_q)

        im = ax.pcolormesh(q, times, intensity,
                           shading='auto', cmap='viridis')
        ax.set_xlabel('q (1/Å)', fontsize=12)
        ax.set_ylabel('Time (s)', fontsize=12)
        ax.set_title(kwargs.get('title', 'SAXS Evolution'), fontsize=13)
        plt.colorbar(im, ax=ax, label='Intensity (a.u.)')
