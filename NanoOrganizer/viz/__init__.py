"""
Visualization module – plotters for each data type.

PLOTTER_REGISTRY maps a data-type key to its plotter class.
``"sem"`` and ``"tem"`` both resolve to ImagePlotter.
"""

from NanoOrganizer.viz.base    import BasePlotter
from NanoOrganizer.viz.uvvis   import UVVisPlotter
from NanoOrganizer.viz.saxs    import SAXSPlotter
from NanoOrganizer.viz.waxs    import WAXSPlotter
from NanoOrganizer.viz.dls     import DLSPlotter
from NanoOrganizer.viz.xas     import XASPlotter
from NanoOrganizer.viz.saxs2d  import SAXS2DPlotter
from NanoOrganizer.viz.waxs2d  import WAXS2DPlotter
from NanoOrganizer.viz.image   import ImagePlotter

PLOTTER_REGISTRY = {
    'uvvis':  UVVisPlotter,
    'saxs':   SAXSPlotter,
    'waxs':   WAXSPlotter,
    'dls':    DLSPlotter,
    'xas':    XASPlotter,
    'saxs2d': SAXS2DPlotter,
    'waxs2d': WAXS2DPlotter,
    'sem':    ImagePlotter,
    'tem':    ImagePlotter,
    'image':  ImagePlotter,
}

__all__ = [
    'BasePlotter',
    'UVVisPlotter', 'SAXSPlotter', 'WAXSPlotter',
    'DLSPlotter', 'XASPlotter', 'SAXS2DPlotter', 'WAXS2DPlotter',
    'ImagePlotter',
    'PLOTTER_REGISTRY',
]
