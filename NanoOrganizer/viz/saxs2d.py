#!/usr/bin/env python3
"""
2-D SAXS plotter.

Expects the dict produced by ``SAXS2DLoader.load()``:

    times         – 1D  (n_times,)
    images        – 3D  (n_times, ny, nx)
    qx            – 1D  (nx,)  or None
    pixel_size_mm – float or None
    sdd_mm        – float or None
    wavelength_A  – float or None

Plot types
----------
detector   – log-scaled 2-D detector image at a selected time.
azimuthal  – azimuthally averaged I(q) from the 2-D image.
"""

import numpy as np
from typing import Any, Dict

from NanoOrganizer.viz.base import BasePlotter


class SAXS2DPlotter(BasePlotter):
    """Plotter for 2-D SAXS detector data."""

    data_type            = "saxs2d"
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
                                f'2D SAXS at t = {closest_time:.0f} s'),
                     fontsize=13)
        plt.colorbar(im, ax=ax,
                     label='log₁₀(Intensity)' if log_scale else 'Intensity')

    def _azimuthal(self, data, ax, **kwargs):
        """Radially averaged I(q) from one 2-D image."""
        times  = data['times']
        images = data['images']

        time_point = kwargs.get('time_point')
        if time_point is None:
            time_point = times[len(times) // 2]
        idx          = int(np.argmin(np.abs(times - time_point)))
        closest_time = times[idx]

        r_pix, profile = _azimuthal_average(images[idx])

        # Convert pixel radius → q if calibration is available
        pixel_size = data.get('pixel_size_mm')
        sdd        = data.get('sdd_mm')
        wavelength = data.get('wavelength_A')

        if None not in (pixel_size, sdd, wavelength):
            x_axis = 2 * np.pi * r_pix * pixel_size / (sdd * wavelength)
            xlabel = 'q (1/Å)'
        else:
            x_axis = r_pix
            xlabel = 'Pixel radius'

        # Skip bin-0 (centre pixel, often a beamstop)
        mask = (x_axis > 0) & (profile > 0)
        ax.loglog(x_axis[mask], profile[mask], 'o-', linewidth=2, markersize=3,
                  label=f't = {closest_time:.0f} s')
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title',
                                f'Azimuthal Average at t = {closest_time:.0f} s'),
                     fontsize=13)
        ax.legend()
        ax.grid(True, alpha=0.3)


# ---------------------------------------------------------------------------
# shared helper (also used by WAXS2DPlotter)
# ---------------------------------------------------------------------------

def _azimuthal_average(image, center=None, n_bins=None):
    """
    Radial (azimuthal) average of a 2-D array.

    Returns
    -------
    r_centres : 1-D array   bin-centre radii in pixel units
    profile   : 1-D array   mean intensity per bin
    """
    ny, nx = image.shape
    if center is None:
        center = (nx / 2.0, ny / 2.0)

    y, x = np.indices(image.shape)
    r    = np.sqrt((x - center[0])**2 + (y - center[1])**2)

    if n_bins is None:
        n_bins = min(nx, ny) // 2

    edges   = np.linspace(0, r.max(), n_bins + 1)
    indices = np.digitize(r.ravel(), edges) - 1

    profile = np.zeros(n_bins)
    for i in range(n_bins):
        mask = indices == i
        if mask.any():
            profile[i] = image.ravel()[mask].mean()

    return (edges[:-1] + edges[1:]) / 2.0, profile
