#!/usr/bin/env python3
"""
Microscopy image plotter (SEM / TEM).

Expects a dict with::

    image    – a PIL Image object
    filename – original filename (used as default title)
"""

from typing import Any, Dict

from NanoOrganizer.viz.base import BasePlotter


class ImagePlotter(BasePlotter):
    """Plotter for microscopy images."""

    data_type            = "image"
    default_plot_type    = "image"
    available_plot_types = ["image"]

    def plot(self, data: Dict[str, Any], plot_type: str = None,
             ax=None, **kwargs):
        ax = self._get_axes(ax, **kwargs)

        img      = data['image']
        filename = data.get('filename', '')

        ax.imshow(img, cmap='gray')
        ax.axis('off')
        ax.set_title(kwargs.get('title', filename), fontsize=13)
        return ax
