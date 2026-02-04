#!/usr/bin/env python3
"""
2-D WAXS plotter.

Same detector-image display as SAXS2D; the azimuthal average is plotted
vs 2θ (degrees) when detector calibration is available, vs pixel radius
otherwise.

Expects the same dict layout as ``SAXS2DLoader`` / ``WAXS2DLoader``.

Plot types
----------
detector   – log-scaled 2-D detector image at a selected time.
azimuthal  – azimuthally averaged I(2θ).
"""

import numpy as np
from typing import Any, Dict

from NanoOrganizer.viz.base import BasePlotter
from NanoOrganizer.viz.saxs2d import _azimuthal_average   # shared helper


class WAXS2DPlotter(BasePlotter):
    """Plotter for 2-D WAXS detector data."""

    data_type            = "waxs2d"
    default_plot_type    = "detector"
    available_plot_types = ["detector", "azimuthal"]

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def plot(self, data: Dict[str, Any], plot_type: str = None,
             ax=None, **kwargs):
        if plot_type is None:
            plot_type = self.default_plot_type

        ax = self._get_axes(ax, **kwargs)

        dispatch = {
            'detector':  self._detector,
            'azimuthal': self._azimuthal,
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

    def _detector(self, data, ax, **kwargs):
        """Display a single 2-D detector image (log scale by default)."""
        import matplotlib.pyplot as plt

        times  = data['times']
        images = data['images']

        time_point = kwargs.get('time_point')
        if time_point is None:
            time_point = times[len(times) // 2]
        idx          = int(np.argmin(np.abs(times - time_point)))
        closest_time = times[idx]

        img       = images[idx]
        log_scale = kwargs.get('log_scale', True)
        if log_scale:
            img = np.log10(np.maximum(img, 1e-10))

        im = ax.imshow(img, origin='lower', cmap='viridis')
        ax.set_xlabel('Pixel x', fontsize=12)
        ax.set_ylabel('Pixel y', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'2D WAXS at t = {closest_time:.0f} s'),
                     fontsize=13)
        plt.colorbar(im, ax=ax,
                     label='log₁₀(Intensity)' if log_scale else 'Intensity')

    def _azimuthal(self, data, ax, **kwargs):
        """Radially averaged I(2θ) from one 2-D image."""
        times  = data['times']
        images = data['images']

        time_point = kwargs.get('time_point')
        if time_point is None:
            time_point = times[len(times) // 2]
        idx          = int(np.argmin(np.abs(times - time_point)))
        closest_time = times[idx]

        r_pix, profile = _azimuthal_average(images[idx])

        # Convert pixel radius → 2θ if calibration is available
        pixel_size = data.get('pixel_size_mm')
        sdd        = data.get('sdd_mm')

        if None not in (pixel_size, sdd):
            r_mm   = r_pix * pixel_size
            x_axis = np.degrees(np.arctan(r_mm / sdd))   # 2θ in degrees
            xlabel = '2θ (degrees)'
        else:
            x_axis = r_pix
            xlabel = 'Pixel radius'

        mask = x_axis > 0
        ax.plot(x_axis[mask], profile[mask], 'o-', linewidth=2, markersize=3,
                label=f't = {closest_time:.0f} s')
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'Azimuthal Average at t = {closest_time:.0f} s'),
                     fontsize=13)
        ax.legend()
        ax.grid(True, alpha=0.3)
