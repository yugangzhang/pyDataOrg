#!/usr/bin/env python3
"""
BaseLoader – abstract base class for every data-type loader.

Contract
--------
* ``link_data(file_paths, ...)``  – store references, no I/O.
* ``validate()``                  – check files exist.
* ``load()``                      – read files, return a standardised dict.
* ``plot(...)``                   – convenience shim that delegates to the
                                    matching plotter in ``nanoorganizer.viz``.
* ``to_dict()``                   – JSON-safe serialisation of the link.

Subclasses must
---------------
* Set the class attribute ``data_type`` (str).
* Implement ``load()``.

Data-dict convention (time-series)
----------------------------------
    times      – 1D  (n_times,)       unique time stamps
    <x_axis>   – 1D  (n_x,)          shared x-axis (wavelength, q, …)
    <y_axis>   – 2D  (n_times, n_x)  measured values
"""

from abc import ABC, abstractmethod
import warnings
from pathlib import Path
from typing import List, Dict, Optional, Union, Any

from NanoOrganizer.core.data_links import DataLink


class BaseLoader(ABC):
    """Abstract base for all data loaders."""

    data_type: str  # e.g. "uvvis" – must be set by each subclass

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.link = DataLink(data_type=self.data_type)
        self._loaded_data = None

    # ------------------------------------------------------------------
    # linking
    # ------------------------------------------------------------------

    def link_data(self, file_paths: List[Union[str, Path]],
                  metadata: Optional[Dict] = None, **kwargs):
        """
        Register data files without reading them.

        Extra keyword arguments (``time_points``, ``dtime_points``, …) are
        stored transparently in ``link.metadata``.
        """
        self.link.file_paths = [str(Path(f).absolute()) for f in file_paths]
        if metadata:
            self.link.metadata.update(metadata)
        for key, value in kwargs.items():
            if value is not None:
                self.link.metadata[key] = value
        print(f"  ✓ Linked {len(file_paths)} {self.data_type.upper()} files")

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------

    def validate(self) -> bool:
        """Return False (and warn) if any linked file is missing."""
        missing = self.link.validate()
        if missing:
            warnings.warn(
                f"Missing {self.data_type.upper()} files:\n"
                + "\n".join(f"  - {f}" for f in missing)
            )
            return False
        return True

    # ------------------------------------------------------------------
    # loading  (subclasses implement this)
    # ------------------------------------------------------------------

    @abstractmethod
    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        """Read files into memory and return the standardised data dict."""
        ...

    # ------------------------------------------------------------------
    # plotting convenience
    # ------------------------------------------------------------------

    def plot(self, plot_type: str = None, ax=None, **kwargs):
        """
        Load data, then delegate to the matching plotter.

        This keeps the familiar ``run.uvvis.plot(plot_type="heatmap")`` API
        while the plotting logic lives in ``NanoOrganizer.viz``.
        """
        from NanoOrganizer.viz import PLOTTER_REGISTRY
        data = self.load()
        plotter = PLOTTER_REGISTRY[self.data_type]()
        if plot_type is None:
            plot_type = plotter.default_plot_type
        return plotter.plot(data, plot_type=plot_type, ax=ax, **kwargs)

    # ------------------------------------------------------------------
    # serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """JSON-safe dict of the file link (written into run JSON)."""
        return self.link.to_dict()
