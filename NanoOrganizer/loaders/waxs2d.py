#!/usr/bin/env python3
"""
2-D WAXS detector-image loader.

Identical loading logic to SAXS2DLoader; the physics difference lives in
the simulation and the plotter (2θ vs q axis labelling).

Supported formats, output dict, and calibration keywords are the same as
``saxs2d`` – see that module for details.
"""

import numpy as np
import warnings
from pathlib import Path
from typing import Dict, Any

from NanoOrganizer.loaders.base import BaseLoader
from NanoOrganizer.loaders.saxs2d import _load_2d_file


class WAXS2DLoader(BaseLoader):
    """Loader for 2-D WAXS detector images."""

    data_type = "waxs2d"

    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data

        if not self.link.file_paths:
            raise ValueError("No data files linked. Use link_data() first.")

        time_points = self.link.metadata.get('time_points')
        times:  list = []
        images: list = []

        for i, fpath in enumerate(self.link.file_paths):
            fpath = Path(fpath)
            if not fpath.exists():
                warnings.warn(f"File not found: {fpath}")
                continue
            try:
                img = _load_2d_file(fpath)
                t   = time_points[i] if time_points else float(i)
                times.append(t)
                images.append(img)
            except Exception as e:
                warnings.warn(f"Error reading {fpath}: {e}")
                continue

        images_arr = np.array(images) if images else np.zeros((0, 0, 0))

        self._loaded_data = {
            'times':        np.array(times),
            'images':       images_arr,
            'qx':           None,                                    # 2D WAXS uses 2θ, not q
            'qy':           None,
            'pixel_size_mm': self.link.metadata.get('pixel_size_mm'),
            'sdd_mm':       self.link.metadata.get('sdd_mm'),
            'wavelength_A': self.link.metadata.get('wavelength_A'),
        }

        shape_str = str(images_arr.shape[1:]) if images_arr.ndim == 3 else 'N/A'
        print(f"  ✓ Loaded {len(times)} 2D WAXS detector images (shape {shape_str})")
        return self._loaded_data
