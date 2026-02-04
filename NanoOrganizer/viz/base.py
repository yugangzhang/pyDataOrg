#!/usr/bin/env python3
"""
BasePlotter – abstract base class for every data-type plotter.

Plotters are *stateless*: they receive an already-loaded data dict
(the output of the matching loader's ``load()``) and produce a
matplotlib Axes.  They have no knowledge of files, DataLinks, or
the organizer.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BasePlotter(ABC):
    """Abstract base for data-type plotters."""

    data_type: str                # e.g. "uvvis"
    default_plot_type: str        # used when caller omits plot_type
    available_plot_types: list    # for documentation / validation

    @abstractmethod
    def plot(self, data: Dict[str, Any], plot_type: str = None,
             ax=None, **kwargs):
        """
        Render a plot.

        Parameters
        ----------
        data : dict
            Output of the matching loader's ``load()``.
        plot_type : str
            Which visualisation style to use.
        ax : matplotlib Axes, optional
            Pre-existing axes.  A new figure is created when None.
        **kwargs
            Extra styling: ``title``, ``figsize``, selector values, etc.

        Returns
        -------
        ax : matplotlib Axes
        """
        ...

    # ------------------------------------------------------------------
    # shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_axes(ax, **kwargs):
        """Create a (fig, ax) pair when *ax* is None."""
        if ax is None:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=kwargs.pop('figsize', (10, 6)))
        return ax
