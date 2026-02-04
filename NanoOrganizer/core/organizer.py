#!/usr/bin/env python3
"""
DataOrganizer – top-level manager for experimental runs.

Responsibilities
----------------
* Create / retrieve Run objects.
* Persist metadata as JSON (one file per run + an index).
* Validate that every linked data file still exists on disk.
"""

import json
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime

from NanoOrganizer.core.metadata import RunMetadata
from NanoOrganizer.core.run import Run


class DataOrganizer:
    """
    Manage a collection of experimental runs on disk.

    Attributes
    ----------
    base_dir : Path
        Root directory that contains the ``.metadata/`` folder.
    runs : dict
        ``{run_key: Run}`` where run_key = ``project/experiment/run_id``.
    """

    def __init__(self, base_dir: Union[str, Path]):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.metadata_dir = self.base_dir / ".metadata"
        self.metadata_dir.mkdir(exist_ok=True)

        self.runs: Dict[str, Run] = {}
        self._index_file = self.metadata_dir / "index.json"

        self._load_index()

    # ------------------------------------------------------------------
    # run management
    # ------------------------------------------------------------------

    def create_run(self, metadata: RunMetadata) -> Run:
        """Create a new Run (overwrites if the key already exists)."""
        run_key = f"{metadata.project}/{metadata.experiment}/{metadata.run_id}"

        if run_key in self.runs:
            warnings.warn(f"Run {run_key} already exists. Overwriting.")

        run = Run(metadata, self.base_dir)
        self.runs[run_key] = run
        print(f"✓ Created run: {run_key}")
        return run

    def get_run(self, run_key: str = '',
                project: str = '', experiment: str = '', run_id: str = '') -> Optional[Run]:
        """Retrieve a Run by its three-part key or a single slash-joined string."""
        if run_key == '':
            run_key = f"{project}/{experiment}/{run_id}"
        return self.runs.get(run_key)

    def list_runs(self) -> List[str]:
        """Return all run keys."""
        return list(self.runs.keys())

    def list_run_ids(self) -> List[str]:
        """Return the sample_id of every run."""
        return [self.get_run(k).metadata.sample_id for k in self.list_runs()]

    def get_run_dict(self) -> Dict[int, list]:
        """Return ``{index: [run_key, sample_id]}`` for every run."""
        keys = self.list_runs()
        ids = self.list_run_ids()
        self.run_dict = {i: [k, ids[i]] for i, k in enumerate(keys)}
        return self.run_dict

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def save(self):
        """Write all run metadata to ``.metadata/`` as JSON."""
        print("\n--- Saving Metadata ---")

        for run_key, run in self.runs.items():
            run_file = self.metadata_dir / f"{run_key.replace('/', '_')}.json"
            run_file.parent.mkdir(parents=True, exist_ok=True)
            with open(run_file, 'w') as f:
                json.dump(run.to_dict(), f, indent=2)
            print(f"  ✓ Saved: {run_key}")

        index = {
            'runs': list(self.runs.keys()),
            'last_updated': datetime.now().isoformat(),
        }
        with open(self._index_file, 'w') as f:
            json.dump(index, f, indent=2)

        print(f"  ✓ Saved index: {len(self.runs)} runs")
        print(f"\n✓ Metadata saved to: {self.metadata_dir}")

    def _load_index(self):
        """Read index.json and reconstruct all Run objects."""
        if not self._index_file.exists():
            return

        with open(self._index_file, 'r') as f:
            index = json.load(f)

        for run_key in index['runs']:
            run_file = self.metadata_dir / f"{run_key.replace('/', '_')}.json"
            if run_file.exists():
                with open(run_file, 'r') as f:
                    run_data = json.load(f)
                self.runs[run_key] = Run.from_dict(run_data, self.base_dir)

    @classmethod
    def load(cls, base_dir: Union[str, Path]) -> 'DataOrganizer':
        """Load an existing organizer from *base_dir*."""
        org = cls(base_dir)
        print(f"✓ Loaded DataOrganizer: {len(org.runs)} runs")
        return org

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------

    def validate_all(self) -> Dict[str, Dict[str, bool]]:
        """Validate every file link in every run."""
        print("\n--- Validating Data Files ---")
        results = {}
        for run_key, run in self.runs.items():
            results[run_key] = run.validate()
            status = "✓" if all(results[run_key].values()) else "⚠"
            print(f"  {status} {run_key}")
        return results
