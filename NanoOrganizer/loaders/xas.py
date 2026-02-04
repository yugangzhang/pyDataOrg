#!/usr/bin/env python3
"""
XAS (X-ray Absorption Spectroscopy) loader – XANES and EXAFS.

CSV layout (one file per time point)::

    energy_eV,absorption
    8900.0,0.05
    8905.0,0.10
    ...

Output dict from ``load()``
---------------------------
    times      – 1D  (n_times,)
    energy     – 1D  (n_energy,)   in eV
    absorption – 2D  (n_times, n_energy)
"""

import numpy as np
import warnings
from pathlib import Path
from typing import Dict, Any

from NanoOrganizer.loaders.base import BaseLoader


class XASLoader(BaseLoader):
    """Loader for XAS (XANES / EXAFS) time-series data."""

    data_type = "xas"

    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data

        if not self.link.file_paths:
            raise ValueError("No data files linked. Use link_data() first.")

        time_points = self.link.metadata.get('time_points')
        times: list   = []
        spectra: list = []
        energy = None

        for i, fpath in enumerate(self.link.file_paths):
            fpath = Path(fpath)
            if not fpath.exists():
                warnings.warn(f"File not found: {fpath}")
                continue
            try:
                raw = np.loadtxt(fpath, delimiter=',', skiprows=1)
                e   = raw[:, 0]
                ab  = raw[:, 1]

                if energy is None:
                    energy = e

                t = time_points[i] if time_points else float(i)
                times.append(t)
                spectra.append(ab)
            except Exception as exc:
                warnings.warn(f"Error reading {fpath}: {exc}")
                continue

        self._loaded_data = {
            'times':      np.array(times),
            'energy':     energy if energy is not None else np.array([]),
            'absorption': np.array(spectra),   # (n_times, n_energy)
        }

        print(f"  ✓ Loaded {len(times)} XAS spectra")
        return self._loaded_data
