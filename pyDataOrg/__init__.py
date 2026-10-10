#!/usr/bin/env python3
"""
pyDataOrg — organise, visualise and analyse experimental data, sample by sample.

The foundation that project packages build on: it knows how to keep track of
samples, the measurements made on them and the results derived from them, and
nothing about any particular material, instrument or facility. A project
package adds that — its file formats, its analyses, its pages — through the
registries and the plugin hook below.

Package layout
--------------
core/         the sample model (Project, Sample, Stage, Measurement), path
              resolution across machines, linking files to samples.
ingest/       reading authored metadata (Python dicts, JSON …) into the model.
analysis/     kernels on plain arrays + the analysis registry that runs them
              over samples and keeps the results.
viz/          drawing: ``plots`` (matplotlib), ``interactive`` (Plotly),
              ``show`` (any measurement, dispatched on its kind).
campaign      a table of inputs → results → objectives across samples.
snapshots     dated copies of authored records, and what changed between them.
servers       where recorded paths live on each machine.
agent         the operations, described for an AI agent or any other caller.
plugins       how project packages register themselves.
web_app/      the Streamlit GUI (``dataorg`` command).
demo/         generators for synthetic projects — no real data ships here.

Quick start
-----------
>>> from pyDataOrg import Organizer
>>> org = Organizer("my_project.json", name="My project")      # doctest: +SKIP
>>> org.ingest("MetaData/Synthesis_dict.py")                    # doctest: +SKIP
>>> org.link("S01", "uvvis", "spectra/S01/*.csv")               # doctest: +SKIP
>>> org.batch("peak_fit")                                       # doctest: +SKIP
>>> org.save()                                                  # doctest: +SKIP
"""

from pyDataOrg.version import __version__

__author__ = "Yugang Zhang, Center for Functional Nanomaterials, " \
             "Brookhaven National Laboratory"

from pyDataOrg.core.project  import Project, ProjectConfig
from pyDataOrg.core.schema   import (
    Sample, Stage, Measurement, DerivedValue, flatten_dict,
)
from pyDataOrg.core.pathmap  import (
    PathResolver, PathAlias, display_path, suggest_aliases,
)
from pyDataOrg.core          import modality

# Workbench binds a project, a selection and the analyses together — the entry
# point the notebooks and the GUI both use.  Imported last: it reaches back
# into this package, so everything it needs must already be defined.
from pyDataOrg.workbench     import (
    Organizer, Workbench, new_organizer, open_project,
)
from pyDataOrg.structure     import dict_tree, tree

__all__ = [
    'Organizer', 'Workbench', 'open_project', 'new_organizer',
    'dict_tree', 'tree',
    'Project', 'ProjectConfig',
    'Sample', 'Stage', 'Measurement', 'DerivedValue', 'flatten_dict',
    'PathResolver', 'PathAlias', 'display_path', 'suggest_aliases',
    'modality',
    '__version__',
]
