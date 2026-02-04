#!/usr/bin/env python3
"""
NanoOrganizer – metadata and data management for nanoparticle synthesis.

Package layout
--------------
core/         Metadata dataclasses, DataOrganizer, Run, file-link logic.
loaders/      One loader class per data type.  Each reads files into a
              standardised dict.  New types: add a module here + one line
              in LOADER_REGISTRY.
viz/          One plotter class per data type.  Each takes a loader's
              output dict and produces matplotlib Axes.
simulations/  Synthetic data generators for demos and testing.

Supported data types
--------------------
UV-Vis, SAXS (1D), WAXS (1D), DLS, XAS, SAXS (2D), WAXS (2D),
SEM images, TEM images.

Quick start
-----------
>>> from NanoOrganizer import DataOrganizer, RunMetadata, ReactionParams, ChemicalSpec
>>>
>>> org = DataOrganizer("./MyProject")
>>> metadata = RunMetadata(
...     project="Project_Au",
...     experiment="2024-10-25",
...     run_id="Au_Test_001",
...     sample_id="Sample_001",
...     reaction=ReactionParams(
...         chemicals=[ChemicalSpec(name="HAuCl4", concentration=0.5)],
...         temperature_C=80.0,
...     ),
... )
>>> run = org.create_run(metadata)
>>> run.uvvis.link_data(csv_files, time_points=[0, 30, 60])
>>> org.save()
>>>
>>> # Later —
>>> org  = DataOrganizer.load("./MyProject")
>>> run  = org.get_run("Project_Au/2024-10-25/Au_Test_001")
>>> data = run.uvvis.load()          # dict with times / wavelengths / absorbance
>>> run.uvvis.plot(plot_type="heatmap")
"""

__version__ = "1.0.0"
__author__  = "NanoOrganizer Team"

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
from NanoOrganizer.core.metadata   import ChemicalSpec, ReactionParams, RunMetadata
from NanoOrganizer.core.data_links import DataLink
from NanoOrganizer.core.organizer  import DataOrganizer
from NanoOrganizer.core.run        import Run
from NanoOrganizer.core.utils      import save_time_series_to_csv

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
from NanoOrganizer.loaders import (
    UVVisLoader, SAXSLoader, WAXSLoader,
    DLSLoader, XASLoader, SAXS2DLoader, WAXS2DLoader,
    ImageLoader,
    LOADER_REGISTRY,
)

# ---------------------------------------------------------------------------
# Viz
# ---------------------------------------------------------------------------
from NanoOrganizer.viz import (
    UVVisPlotter, SAXSPlotter, WAXSPlotter,
    DLSPlotter, XASPlotter, SAXS2DPlotter, WAXS2DPlotter,
    ImagePlotter,
    PLOTTER_REGISTRY,
)

# ---------------------------------------------------------------------------
# Simulations
# ---------------------------------------------------------------------------
from NanoOrganizer.simulations import (
    simulate_uvvis_time_series_data,
    simulate_saxs_time_series_data,
    simulate_waxs_time_series_data,
    simulate_dls_time_series_data,
    simulate_xas_time_series_data,
    simulate_saxs2d_time_series_data,
    simulate_waxs2d_time_series_data,
    create_fake_image_series,
)

# ---------------------------------------------------------------------------
# Backward-compatibility aliases
# The old combined accessor classes are now split into loader + plotter.
# Existing code that does  ``from NanoOrganizer import UVVisData``  or
# ``run.uvvis = UVVisData(...)``  keeps working because the loaders expose
# the same  link_data / load / validate / plot  interface.
# ---------------------------------------------------------------------------
UVVisData = UVVisLoader
SAXSData  = SAXSLoader
WAXSData  = WAXSLoader
ImageData = ImageLoader

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
__all__ = [
    # Core
    'DataOrganizer', 'Run',
    'RunMetadata', 'ReactionParams', 'ChemicalSpec',
    'DataLink',
    'save_time_series_to_csv',

    # Loaders
    'UVVisLoader', 'SAXSLoader', 'WAXSLoader',
    'DLSLoader', 'XASLoader', 'SAXS2DLoader', 'WAXS2DLoader',
    'ImageLoader',
    'LOADER_REGISTRY',

    # Viz
    'UVVisPlotter', 'SAXSPlotter', 'WAXSPlotter',
    'DLSPlotter', 'XASPlotter', 'SAXS2DPlotter', 'WAXS2DPlotter',
    'ImagePlotter',
    'PLOTTER_REGISTRY',

    # Simulations
    'simulate_uvvis_time_series_data',
    'simulate_saxs_time_series_data',
    'simulate_waxs_time_series_data',
    'simulate_dls_time_series_data',
    'simulate_xas_time_series_data',
    'simulate_saxs2d_time_series_data',
    'simulate_waxs2d_time_series_data',
    'create_fake_image_series',

    # Backward-compat aliases
    'UVVisData', 'SAXSData', 'WAXSData', 'ImageData',
]


def get_version():
    """Return the package version string."""
    return __version__


def get_info():
    """Return a dict of basic package metadata."""
    return {
        'name':        'NanoOrganizer',
        'version':     __version__,
        'description': 'Metadata and data management for nanoparticle synthesis',
        'author':      __author__,
    }
