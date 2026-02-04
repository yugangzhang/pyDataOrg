"""
Data loaders – one per supported data type.

LOADER_REGISTRY maps a short string key to its loader class.
Adding a new data type: create a loader module here, import it,
and add one line to LOADER_REGISTRY.
"""

from NanoOrganizer.loaders.base    import BaseLoader
from NanoOrganizer.loaders.uvvis   import UVVisLoader
from NanoOrganizer.loaders.saxs    import SAXSLoader
from NanoOrganizer.loaders.waxs    import WAXSLoader
from NanoOrganizer.loaders.dls     import DLSLoader
from NanoOrganizer.loaders.xas     import XASLoader
from NanoOrganizer.loaders.saxs2d  import SAXS2DLoader
from NanoOrganizer.loaders.waxs2d  import WAXS2DLoader
from NanoOrganizer.loaders.image   import ImageLoader

LOADER_REGISTRY = {
    'uvvis':  UVVisLoader,
    'saxs':   SAXSLoader,
    'waxs':   WAXSLoader,
    'dls':    DLSLoader,
    'xas':    XASLoader,
    'saxs2d': SAXS2DLoader,
    'waxs2d': WAXS2DLoader,
    'image':  ImageLoader,
}

__all__ = [
    'BaseLoader',
    'UVVisLoader', 'SAXSLoader', 'WAXSLoader',
    'DLSLoader', 'XASLoader', 'SAXS2DLoader', 'WAXS2DLoader',
    'ImageLoader',
    'LOADER_REGISTRY',
]
