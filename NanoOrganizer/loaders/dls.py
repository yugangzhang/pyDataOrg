#!/usr/bin/env python3
"""
DLS (Dynamic Light Scattering) size-distribution loader.

CSV layout (one file per time point)::

    diameter_nm,intensity
    0.5,0.001
    1.0,0.012
    ...

Output dict from ``load()``
---------------------------
    times      – 1D  (n_times,)
    diameters  – 1D  (n_diameters,)  in nm
    intensity  – 2D  (n_times, n_diameters)
"""

import numpy as np
import warnings
from pathlib import Path
from typing import Dict, Any

from NanoOrganizer.loaders.base import BaseLoader


class DLSLoader(BaseLoader):
    """Loader for DLS size-distribution time-series data."""

    data_type = "dls"

    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data

        if not self.link.file_paths:
            raise ValueError("No data files linked. Use link_data() first.")

        time_points = self.link.metadata.get('time_points')
        times: list = []
        distributions: list = []
        diameters = None

        for i, fpath in enumerate(self.link.file_paths):
            fpath = Path(fpath)
            if not fpath.exists():
                warnings.warn(f"File not found: {fpath}")
                continue
            try:
                raw = np.loadtxt(fpath, delimiter=',', skiprows=1)
                d         = raw[:, 0]
                intensity = raw[:, 1]

                if diameters is None:
                    diameters = d

                t = time_points[i] if time_points else float(i)
                times.append(t)
                distributions.append(intensity)
            except Exception as e:
                warnings.warn(f"Error reading {fpath}: {e}")
                continue

        self._loaded_data = {
            'times':     np.array(times),
            'diameters': diameters if diameters is not None else np.array([]),
            'intensity': np.array(distributions),   # (n_times, n_diameters)
        }

        print(f"  ✓ Loaded {len(times)} DLS size distributions")
        return self._loaded_data
