#!/usr/bin/env python3
"""
DataLink: lightweight file-reference container.

Stores paths + metadata without touching the actual files.
This is the serialization unit written to JSON for every data accessor.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from pathlib import Path


@dataclass
class DataLink:
    """
    Reference to one or more data files.

    Attributes
    ----------
    file_paths : list of str
        Absolute paths to the data files.
    metadata : dict
        Instrument / collection metadata (time_points, etc.).
    data_type : str
        Identifier for the data type (e.g. "uvvis", "saxs", "sem").
    """
    file_paths: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    data_type: str = ""

    def to_dict(self) -> dict:
        return {
            'file_paths': self.file_paths,
            'metadata': self.metadata,
            'data_type': self.data_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DataLink':
        return cls(**data)

    def validate(self) -> List[str]:
        """Return list of file paths that do not exist on disk."""
        return [fp for fp in self.file_paths if not Path(fp).exists()]
