#!/usr/bin/env python3
"""
Run class representing a single experimental run.

A Run contains:
- Metadata (experimental conditions)
- Data accessors (UV-Vis, SAXS, WAXS, images)
"""

from pathlib import Path
from typing import Dict

from NanoOrganizer.metadata import RunMetadata
from NanoOrganizer.data_accessors import UVVisData, SAXSData, WAXSData, ImageData
from NanoOrganizer.data_links import DataLink


class Run:
    """
    Represents a single experimental run with all associated data.
    
    Attributes
    ----------
    metadata : RunMetadata
        Experiment metadata and conditions
    uvvis : UVVisData
        UV-Vis spectroscopy data accessor
    saxs : SAXSData
        SAXS data accessor
    waxs : WAXSData
        WAXS data accessor
    sem : ImageData
        SEM image data accessor
    tem : ImageData
        TEM image data accessor
    """
    
    def __init__(self, metadata: RunMetadata, base_dir: Path = None, create_folder = False ):
        """
        Initialize a Run.
        
        Parameters
        ----------
        metadata : RunMetadata
            Experiment metadata
        base_dir : Path
            Base directory for the project
        """
        self.metadata = metadata
        self.create_folder = create_folder
        if self.create_folder:
            self.base_dir = Path(base_dir)
            self.run_dir = self.base_dir / metadata.project / metadata.experiment / metadata.run_id
            self.run_dir.mkdir(parents=True, exist_ok=True)
        
        # Create data accessors
        self.uvvis = UVVisData(metadata.run_id)
        self.saxs = SAXSData(metadata.run_id)
        self.waxs = WAXSData(metadata.run_id)
        self.sem = ImageData(metadata.run_id, "sem")
        self.tem = ImageData(metadata.run_id, "tem")
    
    def to_dict(self) -> dict:
        """
        Convert run to dictionary for JSON storage.
        
        Returns
        -------
        dict
            Dictionary containing metadata and data links
        """
        return {
            'metadata': self.metadata.to_dict(),
            'data': {
                'uvvis': self.uvvis.link.to_dict(),
                'saxs': self.saxs.link.to_dict(),
                'waxs': self.waxs.link.to_dict(),
                'sem': self.sem.link.to_dict(),
                'tem': self.tem.link.to_dict(),
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict, base_dir: Path) -> 'Run':
        """
        Load run from dictionary.
        
        Parameters
        ----------
        data : dict
            Dictionary loaded from JSON
        base_dir : Path
            Base directory for the project
        
        Returns
        -------
        Run
            Reconstructed run object
        """
        metadata = RunMetadata.from_dict(data['metadata'])
        run = cls(metadata, base_dir)
        
        # Restore data links
        run.uvvis.link = DataLink.from_dict(data['data']['uvvis'])
        run.saxs.link = DataLink.from_dict(data['data']['saxs'])
        run.waxs.link = DataLink.from_dict(data['data']['waxs'])
        run.sem.link = DataLink.from_dict(data['data']['sem'])
        run.tem.link = DataLink.from_dict(data['data']['tem'])
        
        return run
    
    def validate(self) -> Dict[str, bool]:
        """
        Validate all data links.
        
        Returns
        -------
        dict
            Dictionary mapping data type to validation result
        """
        return {
            'uvvis': self.uvvis.validate() if self.uvvis.link.file_paths else True,
            'saxs': self.saxs.validate() if self.saxs.link.file_paths else True,
            'waxs': self.waxs.validate() if self.waxs.link.file_paths else True,
            'sem': self.sem.validate() if self.sem.link.file_paths else True,
            'tem': self.tem.validate() if self.tem.link.file_paths else True,
        }