#!/usr/bin/env python3
"""
Microscopy image loader (SEM / TEM / generic).

Unlike the spectroscopy loaders, ``load()`` can return a single image
(by index) to avoid reading an entire series into memory at once.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from NanoOrganizer.loaders.base import BaseLoader


class ImageLoader(BaseLoader):
    """
    Loader for microscopy image series.

    Parameters
    ----------
    run_id : str
        Identifier of the parent run.
    image_type : str
        Label used in links and plotter lookup (``"sem"`` or ``"tem"``).
    """

    data_type = "image"   # class-level default; overridden per instance

    def __init__(self, run_id: str, image_type: str = "sem"):
        self.image_type = image_type
        # Instance-level override so the DataLink and plotter lookup
        # use "sem" / "tem" rather than the generic "image".
        self.data_type = image_type
        super().__init__(run_id)

    # ------------------------------------------------------------------
    # loading
    # ------------------------------------------------------------------

    def load(self, index: Optional[int] = None, force_reload: bool = False) -> Any:
        """
        Load one or all images as PIL Image objects.

        Parameters
        ----------
        index : int, optional
            If given, load only this image.  Otherwise load the full series.
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImportError(
                "Pillow is required for image loading.  "
                "Install: pip install Pillow"
            )

        if not self.link.file_paths:
            raise ValueError("No image files linked. Use link_data() first.")

        if index is not None:
            return Image.open(self.link.file_paths[index])
        return [Image.open(f) for f in self.link.file_paths]

    # ------------------------------------------------------------------
    # plotting convenience (override because the data dict is different)
    # ------------------------------------------------------------------

    def plot(self, index: int = 0, ax=None, **kwargs):
        """Display a single image via the ImagePlotter."""
        from NanoOrganizer.viz import PLOTTER_REGISTRY

        img = self.load(index)
        plotter = PLOTTER_REGISTRY[self.data_type]()
        return plotter.plot(
            {'image': img, 'filename': Path(self.link.file_paths[index]).name},
            plot_type="image",
            ax=ax,
            **kwargs,
        )
