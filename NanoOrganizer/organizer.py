#!/usr/bin/env python3
"""
Main DataOrganizer class for managing experimental runs.

The DataOrganizer:
- Creates and manages runs
- Saves/loads metadata to/from JSON
- Validates data integrity
"""

import json
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime

from NanoOrganizer.metadata import RunMetadata
from NanoOrganizer.run import Run


class DataOrganizer:
    """
    Main organizer for nanoparticle synthesis data.
    
    Features:
    - JSON-based metadata storage
    - Flexible directory structure
    - Lazy data loading
    - Data validation
    
    Attributes
    ----------
    base_dir : Path
        Base directory for storing metadata and organizing data
    runs : dict
        Dictionary of Run objects, keyed by "project/experiment/run_id"
    """
    
    def __init__(self, base_dir: Union[str, Path]):
        """
        Initialize DataOrganizer.
        
        Parameters
        ----------
        base_dir : str or Path
            Base directory for storing metadata and organizing data
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        self.metadata_dir = self.base_dir / ".metadata"
        self.metadata_dir.mkdir(exist_ok=True)
        
        self.runs: Dict[str, Run] = {}
        self._index_file = self.metadata_dir / "index.json"
        
        # Load existing runs if any
        self._load_index()
    
    def create_run(self, metadata: RunMetadata) -> Run:
        """
        Create a new run.
        
        Parameters
        ----------
        metadata : RunMetadata
            Metadata for the run
        
        Returns
        -------
        run : Run
            The created run object
        """
        run_key = f"{metadata.project}/{metadata.experiment}/{metadata.run_id}"
        
        if run_key in self.runs:
            warnings.warn(f"Run {run_key} already exists. Overwriting.")
        
        run = Run(metadata, self.base_dir)
        self.runs[run_key] = run
        
        print(f"✓ Created run: {run_key}")
        return run
    
    def get_run(self, run_key: str = '', project: str='', experiment: str='', run_id: str ='') -> Optional[Run]:
        """
        Get a run by its identifiers.
        
        Parameters
        ----------
        project : str
            Project name
        experiment : str
            Experiment name (usually a date)
        run_id : str
            Run identifier
        
        Returns
        -------
        Run or None
            The requested run, or None if not found
        """
        if run_key =='':
            run_key = f"{project}/{experiment}/{run_id}"            
        return self.runs.get(run_key)
    
    def list_runs(self) -> List[str]:
        """
        List all runs.
        
        Returns
        -------
        list
            List of run keys
        """
        return list(self.runs.keys())

    def list_run_ids(self) -> List[str]:
        """
        List all runs.
        
        Returns
        -------
        list
            List of run keys
        """
        ks = self.list_runs()
        lst = [ self.get_run(  k ).metadata.sample_id for k in ks ] 
        return lst 
        
    def get_run_dict(self) -> Dict:
        """
        List all runs.
        
        Returns
        -------
        list
            List of run keys
        """
        ks = self.list_runs()        
        lst =  self.list_run_ids()
        self.run_dict = {}
        for i, k in enumerate( ks ):
            self.run_dict[i] = [ k, lst[i] ]        
        return self.run_dict

        
    
    def save(self):
        """Save all metadata to JSON files."""
        print("\n--- Saving Metadata ---")
        
        # Save individual run files
        for run_key, run in self.runs.items():
            run_file = self.metadata_dir / f"{run_key.replace('/', '_')}.json"
            run_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(run_file, 'w') as f:
                json.dump(run.to_dict(), f, indent=2)
            
            print(f"  ✓ Saved: {run_key}")
        
        # Save index
        index = {
            'runs': list(self.runs.keys()),
            'last_updated': datetime.now().isoformat()
        }
        
        with open(self._index_file, 'w') as f:
            json.dump(index, f, indent=2)
        
        print(f"  ✓ Saved index: {len(self.runs)} runs")
        print(f"\n✓ Metadata saved to: {self.metadata_dir}")
    
    def _load_index(self):
        """Load index of runs."""
        if not self._index_file.exists():
            return
        
        with open(self._index_file, 'r') as f:
            index = json.load(f)
        
        # Load each run
        for run_key in index['runs']:
            run_file = self.metadata_dir / f"{run_key.replace('/', '_')}.json"
            if run_file.exists():
                with open(run_file, 'r') as f:
                    run_data = json.load(f)
                self.runs[run_key] = Run.from_dict(run_data, self.base_dir)
    
    @classmethod
    def load(cls, base_dir: Union[str, Path]) -> 'DataOrganizer':
        """
        Load existing DataOrganizer from directory.
        
        Parameters
        ----------
        base_dir : str or Path
            Base directory containing metadata
        
        Returns
        -------
        organizer : DataOrganizer
            Loaded organizer with all runs
        """
        org = cls(base_dir)
        print(f"✓ Loaded DataOrganizer: {len(org.runs)} runs")
        return org
    
    def validate_all(self) -> Dict[str, Dict[str, bool]]:
        """
        Validate all runs.
        
        Returns
        -------
        dict
            Dictionary mapping run keys to validation results
        """
        print("\n--- Validating Data Files ---")
        results = {}
        
        for run_key, run in self.runs.items():
            results[run_key] = run.validate()
            
            # Print summary
            all_valid = all(results[run_key].values())
            status = "✓" if all_valid else "⚠"
            print(f"  {status} {run_key}")
        
        return results