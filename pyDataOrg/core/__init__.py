"""Core: the sample model, path resolution, ingest-facing schema, and config."""

from pyDataOrg.core.schema import (
    DerivedValue, Measurement, Sample, Stage, flatten_dict,
)
from pyDataOrg.core.pathmap import PathAlias, PathResolver, suggest_aliases
from pyDataOrg.core.project import Project, ProjectConfig
from pyDataOrg.core.linking import (
    link, link_folder, link_many, link_table, links_table, mount_prefix,
    unlink,
)
from pyDataOrg.core.access_config import (
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

    # Access configuration
    'AccessConfig', 'UserAccess', 'configured_extra_roots',
    'configured_start_dir', 'discover_config_path', 'load_access_config',
]
