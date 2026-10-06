"""Core: the sample model, path resolution, ingest-facing schema, and config."""

from NanoOrganizer.core.metadata import ChemicalSpec, ReactionParams, RunMetadata
from NanoOrganizer.core.data_links import DataLink
from NanoOrganizer.core.utils import save_time_series_to_csv
from NanoOrganizer.core.organizer import DataOrganizer
from NanoOrganizer.core.run import Run
from NanoOrganizer.core.schema import (
    DerivedValue, Measurement, Sample, Stage, flatten_dict,
)
from NanoOrganizer.core.pathmap import PathAlias, PathResolver, suggest_aliases
from NanoOrganizer.core.project import Project, ProjectConfig
from NanoOrganizer.core.linking import (
    link, link_folder, link_many, link_table, links_table, mount_prefix,
    unlink,
)
from NanoOrganizer.core.access_config import (
    AccessConfig, UserAccess, configured_extra_roots, configured_start_dir,
    discover_config_path, load_access_config,
)

__all__ = [
    # Sample-centric model
    'Project', 'ProjectConfig',
    'Sample', 'Stage', 'Measurement', 'DerivedValue', 'flatten_dict',
    'PathResolver', 'PathAlias', 'suggest_aliases',
    'link', 'link_folder', 'link_many', 'link_table', 'links_table',
    'unlink', 'mount_prefix',

    # Legacy run-centric model
    'ChemicalSpec', 'ReactionParams', 'RunMetadata',
    'DataLink', 'DataOrganizer', 'Run',
    'save_time_series_to_csv',

    # Access configuration
    'AccessConfig', 'UserAccess', 'configured_extra_roots',
    'configured_start_dir', 'discover_config_path', 'load_access_config',
]
