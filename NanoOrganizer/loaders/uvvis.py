#!/usr/bin/env python3
"""
UV-Vis spectroscopy loader.

CSV layout (one file per time point)::

    wavelength,absorbance
    200.0,0.05
    201.0,0.06
    ...

Output dict from ``load()``
---------------------------
    times        – 1D  (n_times,)
    wavelengths  – 1D  (n_wavelengths,)   shared across all times
    absorbance   – 2D  (n_times, n_wavelengths)
"""

import re
import numpy as np
import warnings
from pathlib import Path
from typing import Dict, Any

from NanoOrganizer.loaders.base import BaseLoader


class UVVisLoader(BaseLoader):
    """Loader for UV-Vis spectroscopy time-series data."""

    data_type = "uvvis"

    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data

        if not self.link.file_paths:
            raise ValueError("No data files linked. Use link_data() first.")

        time_points = self.link.metadata.get('time_points')
        times: list = []
        spectra: list = []
        wavelengths = None

        for i, fpath in enumerate(self.link.file_paths):
            fpath = Path(fpath)
            if not fpath.exists():
                warnings.warn(f"File not found: {fpath}")
                continue
            try:
                raw = np.loadtxt(fpath, delimiter=',', skiprows=1)
                wl = raw[:, 0]
                ab = raw[:, 1]

                if wavelengths is None:
                    wavelengths = wl

                t = time_points[i] if time_points else _extract_time(fpath.name, i)
                times.append(t)
                spectra.append(ab)
            except Exception as e:
                warnings.warn(f"Error reading {fpath}: {e}")
                continue

        self._loaded_data = {
            'times':        np.array(times),
            'wavelengths':  wavelengths if wavelengths is not None else np.array([]),
            'absorbance':   np.array(spectra),   # (n_times, n_wavelengths)
        }

        print(f"  ✓ Loaded {len(times)} UV-Vis spectra "
              f"({len(times) * (len(wavelengths) if wavelengths is not None else 0)} total data points)")
        return self._loaded_data


def _extract_time(filename: str, index: int) -> float:
    """Best-effort time extraction from filename; falls back to file index."""
    for pattern in (r't(\d+)s', r't(\d+)', r'_(\d+)s', r'_(\d+)'):
        match = re.search(pattern, filename)
        if match:
            return float(match.group(1))
    return float(index)
