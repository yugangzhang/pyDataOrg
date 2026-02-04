#!/usr/bin/env python3
"""
2-D SAXS detector-image loader.

Supported file formats (auto-detected by extension)::

    .npy            – numpy array  (preferred; preserves float precision)
    .png .tif .tiff – image files  (loaded via Pillow, converted to float)

Output dict from ``load()``
---------------------------
    times         – 1D  (n_times,)
    images        – 3D  (n_times, ny, nx)   detector images
    qx            – 1D  (nx,)  or None
    qy            – 1D  (ny,)  or None
    pixel_size_mm – float or None   (passed through for plotter)
    sdd_mm        – float or None
    wavelength_A  – float or None

Calibration
-----------
Pass ``pixel_size_mm``, ``sdd_mm``, and ``wavelength_A`` as keyword
arguments to ``link_data()`` to enable automatic q-axis computation and
calibrated azimuthal averaging in the plotter.
"""

import numpy as np
import warnings
from pathlib import Path
from typing import Dict, Any

from NanoOrganizer.loaders.base import BaseLoader


class SAXS2DLoader(BaseLoader):
    """Loader for 2-D SAXS detector images."""

    data_type = "saxs2d"

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
        qx, qy     = _compute_q_axes(images_arr, self.link.metadata)

        self._loaded_data = {
            'times':        np.array(times),
            'images':       images_arr,
            'qx':           qx,
            'qy':           qy,
            'pixel_size_mm': self.link.metadata.get('pixel_size_mm'),
            'sdd_mm':       self.link.metadata.get('sdd_mm'),
            'wavelength_A': self.link.metadata.get('wavelength_A'),
        }

        shape_str = str(images_arr.shape[1:]) if images_arr.ndim == 3 else 'N/A'
        print(f"  ✓ Loaded {len(times)} 2D SAXS detector images (shape {shape_str})")
        return self._loaded_data


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_2d_file(fpath: Path) -> np.ndarray:
    """Read one 2-D array from a .npy or image file."""
    ext = fpath.suffix.lower()
    if ext == '.npy':
        return np.load(fpath).astype(float)
    if ext in ('.png', '.tif', '.tiff', '.jpg', '.jpeg'):
        try:
            from PIL import Image
        except ImportError:
            raise ImportError("Pillow required for image files – pip install Pillow")
        return np.array(Image.open(fpath).convert('L'), dtype=float)
    raise ValueError(f"Unsupported 2-D file format: {ext}")


def _compute_q_axes(images, metadata):
    """Return (qx, qy) arrays when full calibration is available."""
    pixel_size = metadata.get('pixel_size_mm')
    sdd        = metadata.get('sdd_mm')
    wavelength = metadata.get('wavelength_A')

    if images.size == 0 or None in (pixel_size, sdd, wavelength):
        return None, None

    ny, nx     = images.shape[1], images.shape[2]
    cx, cy     = nx / 2.0, ny / 2.0

    # Small-angle approximation: q ≈ 2π r / (SDD · λ)
    # r in mm, SDD in mm, λ in Å  →  q in Å⁻¹
    qx = 2 * np.pi * (np.arange(nx) - cx) * pixel_size / (sdd * wavelength)
    qy = 2 * np.pi * (np.arange(ny) - cy) * pixel_size / (sdd * wavelength)
    return qx, qy
