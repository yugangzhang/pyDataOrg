#!/usr/bin/env python3
"""
NanoOrganizer: Metadata and data management for nanoparticle synthesis.

A modular, reusable system for organizing experimental data from 
high-throughput reactor synthesis.

Main Components
---------------
DataOrganizer : Main organizer class
    Manages all runs, saves/loads metadata
Run : Single experimental run
    Contains metadata and data accessors
RunMetadata : Experiment metadata
    Reaction conditions, chemicals, etc.
ReactionParams : Reaction parameters
    Temperature, time, chemicals, etc.
ChemicalSpec : Chemical specification
    Name, concentration, volume

Data Accessors
--------------
UVVisData : UV-Vis spectroscopy
SAXSData : Small-angle X-ray scattering
WAXSData : Wide-angle X-ray diffraction
ImageData : Microscopy images (SEM/TEM)

Utilities
---------
save_time_series_to_csv : Save time-series data to CSV files

Basic Usage
-----------
>>> from NanoOrganizer import DataOrganizer, RunMetadata, ReactionParams, ChemicalSpec
>>> 
>>> # Create organizer
>>> org = DataOrganizer("./MyProject")
>>> 
>>> # Create run
>>> metadata = RunMetadata(
...     project="Project_Au",
...     experiment="2024-10-25",
...     run_id="Au_Test_001",
...     sample_id="Sample_001",
...     reaction=ReactionParams(
...         chemicals=[ChemicalSpec(name="HAuCl4", concentration=0.5)],
...         temperature_C=80.0
...     )
... )
>>> run = org.create_run(metadata)
>>> 
>>> # Link data
>>> run.uvvis.link_data(csv_files, time_points=[0, 30, 60])
>>> 
>>> # Save
>>> org.save()
>>> 
>>> # Later: load and analyze
>>> org = DataOrganizer.load("./MyProject")
>>> run = org.get_run("Project_Au", "2024-10-25", "Au_Test_001")
>>> data = run.uvvis.load()
>>> run.uvvis.plot(plot_type="heatmap")
"""

__version__ = "1.0.0"
__author__ = "NanoOrganizer Team"

# Import main classes for public API
from NanoOrganizer.metadata import ChemicalSpec, ReactionParams, RunMetadata
from NanoOrganizer.organizer import DataOrganizer
from NanoOrganizer.run import Run
from NanoOrganizer.utils import save_time_series_to_csv

# Import data accessors (optional, but convenient)
from NanoOrganizer.data_accessors import UVVisData, SAXSData, WAXSData, ImageData
from NanoOrganizer.data_links import DataLink


from NanoOrganizer.time_series_simulations import (
    simulate_uvvis_time_series_data,
    simulate_saxs_time_series_data,
    simulate_waxs_time_series_data,
    create_fake_image_series
)


# Define public API
__all__ = [
    # Main classes
    'DataOrganizer',
    'Run',
    
    # Metadata classes
    'RunMetadata',
    'ReactionParams',
    'ChemicalSpec',
    
    # Data accessors
    'UVVisData',
    'SAXSData',
    'WAXSData',
    'ImageData',
    
    # Data links
    'DataLink',
    
    # Utilities
    'save_time_series_to_csv',
]


# Package information
def get_version():
    """Get package version."""
    return __version__


def get_info():
    """Get package information."""
    return {
        'name': 'NanoOrganizer',
        'version': __version__,
        'description': 'Metadata and data management for nanoparticle synthesis',
        'author': __author__,
    }


if __name__ == "__main__":
    print("NanoOrganizer Package")
    print("=" * 50)
    print(f"Version: {__version__}")
    print("\nImport this module to use:")
    print("  from NanoOrganizer import DataOrganizer, RunMetadata, ReactionParams, ChemicalSpec")
    print("\nAvailable classes:")
    for item in __all__:
        print(f"  - {item}")
        
        
# from NanoOrganizer.nanoorganizer import ( DataOrganizer, RunMetadata, ReactionParams, ChemicalSpec, DataOrganizer, save_time_series_to_csv ) # DirectoryMap, ImportSchema,  VisualizationHelper, save_time_series_to_csv )


# from NanoOrganizer.demo_toy_sim import (simulate_uvvis_data, simulate_saxs_data  , simulate_waxs_data,  create_fake_image ) 


 