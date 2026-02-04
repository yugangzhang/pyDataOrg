#!/usr/bin/env python3
"""
SAXS (small-angle X-ray scattering) 1-D loader.

CSV layout (one file per time point)::

    q,intensity
    0.01,1234.5
    0.02,987.6
    ...

Output dict from ``load()``
---------------------------
    times         – 1D  (n_times,)
    dtimes        – 1D  (n_times,)  or None
    temperatures  – 1D  (n_times,)  or None
    q             – 1D  (n_q,)      shared across all times
    intensity     – 2D  (n_times, n_q)
"""

import numpy as np
import warnings
from pathlib import Path
from typing import Dict, Any

from NanoOrganizer.loaders.base import BaseLoader


class SAXSLoader(BaseLoader):
    """Loader for SAXS 1-D profile time-series data."""

    data_type = "saxs"

    def load(self, force_reload: bool = False, verbose: bool = False) -> Dict[str, Any]:
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data

        if not self.link.file_paths:
            raise ValueError("No data files linked. Use link_data() first.")

        time_points        = self.link.metadata.get('time_points')
        dtime_points       = self.link.metadata.get('dtime_points')
        temperature_points = self.link.metadata.get('temperature_points')

        q_shared  = None
        profiles: list = []

        for i, fpath in enumerate(self.link.file_paths):
            fpath = Path(fpath)
            if not fpath.exists():
                warnings.warn(f"File not found: {fpath}")
                continue
            try:
                raw = np.loadtxt(fpath, delimiter=',', skiprows=1)
                q         = raw[:, 0]
                intensity = raw[:, 1]

                if q_shared is None:
                    q_shared = q
                profiles.append(intensity)
            except Exception as e:
                warnings.warn(f"Error reading {fpath}: {e}")
                continue

        n = len(profiles)
        self._loaded_data = {
            'times':        np.array(time_points)        if time_points        else np.arange(n, dtype=float),
            'dtimes':       np.array(dtime_points)       if dtime_points       else None,
            'temperatures': np.array(temperature_points) if temperature_points else None,
            'q':            q_shared if q_shared is not None else np.array([]),
            'intensity':    np.array(profiles),   # (n_times, n_q)
        }

        if verbose:
            print(f"  ✓ Loaded {n} SAXS profiles")
        return self._loaded_data
