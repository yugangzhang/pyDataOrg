#!/usr/bin/env python3
"""
Data link classes for storing references to data files.

DataLink stores file paths and metadata, but not the actual data.
This enables lazy loading and flexible file organization.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from pathlib import Path


@dataclass
class DataLink:
    """
    Base class for data file links.
    
    Stores references to data files without loading the actual data.
    This enables lazy loading and keeps memory usage low.
    """
    file_paths: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    data_type: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            'file_paths': self.file_paths,
            'metadata': self.metadata,
            'data_type': self.data_type
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DataLink':
        """Create from dictionary loaded from JSON."""
        return cls(**data)
    
    def validate(self) -> List[str]:
        """
        Check if all files exist.
        
        Returns
        -------
        missing : list
            List of missing file paths (empty if all exist)
        """
        missing = []
        for fpath in self.file_paths:
            if not Path(fpath).exists():
                missing.append(fpath)
        return missing