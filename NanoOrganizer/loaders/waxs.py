#!/usr/bin/env python3
"""
WAXS (wide-angle X-ray scattering) 1-D loader.

CSV layout (one file per time point)::

    two_theta,intensity
    10.0,45.2
    10.1,44.8
    ...

Output dict from ``load()``
---------------------------
    times      – 1D  (n_times,)
    two_theta  – 1D  (n_2theta,)   shared across all times
    intensity  – 2D  (n_times, n_2theta)
"""

import numpy as np
import warnings
from pathlib import Path
from typing import Dict, Any

from NanoOrganizer.loaders.base import BaseLoader


class WAXSLoader(BaseLoader):
    """Loader for WAXS 1-D pattern time-series data."""

    data_type = "waxs"

    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data

        if not self.link.file_paths:
            raise ValueError("No data files linked. Use link_data() first.")

        time_points = self.link.metadata.get('time_points')

        tt_shared  = None
        times:    list = []
        patterns: list = []

        for i, fpath in enumerate(self.link.file_paths):
            fpath = Path(fpath)
            if not fpath.exists():
                warnings.warn(f"File not found: {fpath}")
                continue
            try:
                raw = np.loadtxt(fpath, delimiter=',', skiprows=1)
                tt        = raw[:, 0]
                intensity = raw[:, 1]

                if tt_shared is None:
                    tt_shared = tt

                t = time_points[i] if time_points else float(i)
                times.append(t)
                patterns.append(intensity)
            except Exception as e:
                warnings.warn(f"Error reading {fpath}: {e}")
                continue

        self._loaded_data = {
            'times':     np.array(times),
            'two_theta': tt_shared if tt_shared is not None else np.array([]),
            'intensity': np.array(patterns),   # (n_times, n_2theta)
        }

        print(f"  ✓ Loaded {len(patterns)} WAXS patterns")
        return self._loaded_data
