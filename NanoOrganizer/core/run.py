#!/usr/bin/env python3
"""
Run – a single experimental run with its metadata and data loaders.

The set of loaders attached to every Run is driven by DEFAULT_LOADERS.
Adding a new data type to future runs requires only adding an entry there
and registering the loader class in ``NanoOrganizer.loaders``.
"""

from pathlib import Path
from typing import Dict, Optional

from NanoOrganizer.core.metadata import RunMetadata
from NanoOrganizer.core.data_links import DataLink
from NanoOrganizer.loaders import LOADER_REGISTRY

# ---------------------------------------------------------------------------
# Registry of loaders that every Run gets by default.
# Format: (attribute_name, loader_registry_key, extra_kwargs_for_constructor)
# ---------------------------------------------------------------------------
DEFAULT_LOADERS = [
    ('uvvis',  'uvvis',  {}),
    ('saxs',   'saxs',   {}),
    ('waxs',   'waxs',   {}),
    ('dls',    'dls',    {}),
    ('xas',    'xas',    {}),
    ('saxs2d', 'saxs2d', {}),
    ('waxs2d', 'waxs2d', {}),
    ('sem',    'image',  {'image_type': 'sem'}),
    ('tem',    'image',  {'image_type': 'tem'}),
]


class Run:
    """
    A single experimental run: metadata + one loader per data type.

    Attributes
    ----------
    metadata : RunMetadata
    uvvis, saxs, waxs, dls, xas, saxs2d, waxs2d, sem, tem
        Data loaders (created automatically from DEFAULT_LOADERS).
    """

    def __init__(self, metadata: RunMetadata, base_dir: Optional[Path] = None,
                 create_folder: bool = False):
        self.metadata = metadata
        self.create_folder = create_folder

        if self.create_folder and base_dir is not None:
            self.base_dir = Path(base_dir)
            run_dir = (self.base_dir / metadata.project
                       / metadata.experiment / metadata.run_id)
            run_dir.mkdir(parents=True, exist_ok=True)

        # Instantiate every loader declared in DEFAULT_LOADERS
        for attr_name, loader_key, kwargs in DEFAULT_LOADERS:
            loader_cls = LOADER_REGISTRY[loader_key]
            setattr(self, attr_name, loader_cls(run_id=metadata.run_id, **kwargs))

    # ------------------------------------------------------------------
    # serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (metadata + all data links)."""
        return {
            'metadata': self.metadata.to_dict(),
            'data': {
                attr_name: getattr(self, attr_name).to_dict()
                for attr_name, _, _ in DEFAULT_LOADERS
            },
        }

    @classmethod
    def from_dict(cls, data: dict, base_dir: Optional[Path] = None) -> 'Run':
        """Reconstruct a Run from a JSON-loaded dict.

        Keys in ``data['data']`` that are not in DEFAULT_LOADERS are
        silently ignored, so old JSON files load fine after new types
        are added.
        """
        metadata = RunMetadata.from_dict(data['metadata'])
        run = cls(metadata, base_dir)

        for attr_name, _, _ in DEFAULT_LOADERS:
            if attr_name in data.get('data', {}):
                loader = getattr(run, attr_name)
                loader.link = DataLink.from_dict(data['data'][attr_name])

        return run

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------

    def validate(self) -> Dict[str, bool]:
        """Validate every loader's file links. Skip loaders with no files."""
        result = {}
        for attr_name, _, _ in DEFAULT_LOADERS:
            loader = getattr(self, attr_name)
            result[attr_name] = loader.validate() if loader.link.file_paths else True
        return result
