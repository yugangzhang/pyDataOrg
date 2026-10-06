# The sample-centric model

NanoOrganizer started out organised around *runs* (`project/experiment/run_id`)
with a fixed set of nine loader attributes bolted onto every `Run`. That shape
does not survive contact with a real campaign: one sample is synthesised once,
used in several reactions, and characterised repeatedly over weeks by different
instruments. Keying on a run scatters that history; keying on the sample keeps
it together.

This document describes the model that replaces it. The old `DataOrganizer` /
`Run` API still works and is untouched — existing projects keep loading.

## Four objects

```
Project                      a directory of samples + path aliases + sources
 └── Sample(sample_id)       the thing that persists
      ├── stages    {id: Stage}         one execution each
      ├── measurements [Measurement]    one body of data each
      └── derived   {name: DerivedValue} computed, filterable
```

**`Stage`** is one execution: a synthesis, a catalytic assay, a microscopy
session. It keeps its own `run_id`, `batch_tag`, `campaign`, `status`, timings
and error — promoted so they sort and filter — plus the entire authored
parameter dictionary in `params`, verbatim. Nothing is dropped in translation,
so an unrecognised field is still queryable.

**`Measurement`** references files without reading them: explicit `paths`, a
`pattern` glob, or both, plus `aux` companion files (a wavelength axis, a mask,
a calibration). It is tagged with a `modality` and the `stage` that produced it.

**`DerivedValue`** is a number computed from data, stored with the analysis that
produced it and the measurement it came from. This is what closes the loop:
derived values become columns in the same table as the authored parameters, so
you can filter on a fitted peak position exactly as you filter on a
synthesis temperature.

## Modality: technique is metadata, not a code path

The visualisation layer must not grow a branch per technique. It dispatches on
two technique-independent axes:

| axis | values |
|---|---|
| `domain` | wavelength, wavenumber, q, energy, two_theta, size, time, lag_time, space |
| `shape` | curve, series, image, map, volume, stack, corr, twotime |

`shape` maps to one of four **groups** — `curve`, `image`, `volume`,
`correlation` — and those are the GUI's top-level tabs. A *modality* (uvvis,
raman, tem, xpcs_g2, …) is then only a label plus defaults: axis captions, log
scaling, file extensions, which analyses apply.

Adding a technique is one `register()` call in
`NanoOrganizer/core/modality.py`. It needs no new page, no new loader branch,
and no change anywhere else:

```python
from NanoOrganizer.core.modality import Modality, register

register(Modality(
    key="pl", label="Photoluminescence", domain="wavelength", shape="series",
    x_label="Wavelength (nm)", y_label="Intensity (a.u.)",
    extensions=(".txt", ".csv"), analyses=("peak_fit",),
    category="spectroscopy",
))
```

## Path aliases: metadata outlives its mount point

Metadata written at the instrument records absolute paths such as
`/instrument/share/spectra/...`. On an analysis workstation that
prefix may be mounted elsewhere, or not at all. Rewriting the records at ingest
would make the store machine-specific and break the moment it is shared, so the
paths are kept exactly as authored and resolved per machine:

```python
project.add_alias("/instrument/share", ["/mnt/instrument"])
```

Resolution tries the recorded path first, then each alias candidate in order.
**A path that does not resolve is not an error.** Browsing metadata for data
that is not currently mounted is a normal, supported state —
`project.availability()` reports how much is readable here, and the interface
shows the rest as "not mounted" rather than failing.

A glob expands against the first candidate prefix that yields any match, so a
partially mounted tree cannot silently mix files from two different roots.

`suggest_aliases()` proposes aliases by matching recorded path components
against local trees. It is a setup convenience — review what it returns,
because directory names repeat.

## Ingest: the authored file stays the source of truth

Instrument-side metadata is a plain Python module of sample-keyed dicts, often
built by a helper function so ten samples sharing a protocol are not ten
hand-copied blocks. That convenience is why the file must be *executed* to be
read — see the warning in `NanoOrganizer/ingest/pydict.py`; only ingest modules
you or your collaborators wrote.

`project.ingest(path)` reads it into the canonical store at
`.nanoorganizer/samples.json`. The authored file is never edited. Re-ingesting
merges onto the same sample ids rather than duplicating them, so the file at the
instrument can keep growing and the project simply re-reads it
(`project.reingest()`).

The `sampledict` adapter is generic — it knows nothing about any particular chemistry. From each record it recovers:

- **the stage**, from the dict variable name (`Synthesis_dict` → `synthesis`);
- **run provenance**, promoted from a `*_batch` sub-dict, falling back to a
  nested `run_id` for schemas that keep it with the data block;
- **measurements**, from any sub-dict holding a glob, a path list, or
  path-valued `*_file` entries — modality read from the sub-dict's own name
  (a block named `raman_data` → `raman`);
- **everything else**, verbatim, as stage parameters.

A `*_file` entry only counts as a path when its value *looks* like one. A record
storing `"first_frame": "scan_000.npy"` is naming a file
inside a directory, not locating it.

To support another authoring format, register an adapter in
`NanoOrganizer/ingest/__init__.py`. Adapters never write to disk.

## Folder convention: data nobody wrote down

`<Modality>Data/<SampleID>/` attaches automatically:

```
MyProject/
├── MetaData/      Synthesis_dict.py, Reaction_dict.py
├── TEMData/
│   └── Sample000001/   1.tif … 5.tif, note.txt
└── SEMData/, DLSData/, ECData/, RamanData/
```

`project.attach_folders()` walks those directories, matches each against the
modality registry, keeps only files with an extension that modality claims, and
picks up a side-car `note.txt` into the measurement's metadata. This is how a
folder of micrographs dropped in by whoever ran the microscope joins the project
without anyone hand-editing a record. Folder names are configurable through
`ProjectConfig.modality_dirs`.

## Linking: data that is somewhere else and is staying there

The folder convention covers data laid out under the project root. The common
case is the other one: the micrographs are on the microscope's share, the
scattering on a beamline mount, the spectra in whatever folder somebody made
that afternoon, and none of it is going to move.

`link()` records where data is instead of collecting it:

```python
from NanoOrganizer import new_organizer

wb = new_organizer("~/CuAuStudy")          # root holds the store, not the data

wb.link("CuAu05", "uvvis", "/mnt/specs/CuAu05/*.csv", stage="synthesis")
wb.link("CuAu05", "tem",   "/mnt/scope/session17/")
wb.link("CuAu05", "waxs1d", ["/beamline/2024_3/w1.dat"])
```

`new_organizer(root)` is the empty-project entry point, as `open_project(root)`
is the existing-project one. Both return a `Workbench`.

**Three forms of source, and the difference matters:**

| | |
|---|---|
| a glob — `".../uvvis_b05_*.npy"` | stored as `Measurement.pattern`, a **live** query re-expanded at read time, so frames written later appear |
| a directory — `".../TEMData/CuAu05"` | listed **now** and filtered by the modality's extensions — a snapshot you can audit |
| a path or a list | stored verbatim |

`link_folder(sample, modality, folder, pattern="*.tif")` records the glob
rather than the listing, which is the one to use while a run is still going.

Linking the same sample, modality, stage and role twice **replaces** rather
than duplicating, so re-running a setup script is safe. `unlink()` removes.

### Bulk forms

```python
wb.link_many({                          # {sample: {modality: source}}
    "CuAu01": {"waxs1d": "/beamline/CuAu01/w.dat",
               "tem": {"source": "/mnt/scope/CuAu01/", "kV": 200}},
    "CuAu02": {"waxs1d": "/beamline/CuAu02/w.dat"},
}, stage="characterization")

wb.link_table("session_log.csv")        # sample_id, modality, source, …
```

`link_table` takes a DataFrame, a CSV path or a list of dicts. Columns beyond
the recognised ones become measurement metadata, so the spreadsheet whoever ran
the instrument was keeping anyway is an ingest format with no adapter to write.

`wb.links_table()` is the other half, and the pair is a genuine round trip —
export, fix forty rows in a spreadsheet, re-import:

```python
wb.links_table().to_csv("links.csv", index=False)
wb.link_table("links.csv")          # identical measurements
```

What a row records is the shortest form that re-imports to the same files: a
pattern as that pattern, a folder as its folder, and explicit paths as a
`;`-joined list **whenever listing the folder would not reproduce them
exactly**. A re-import can therefore never quietly link a different set of
files. `aux` travels as JSON.

### Paths are not rewritten, and the store still moves

A link records the path **exactly as given**. Nothing is made relative to the
project, because a rewritten store only works on the machine that wrote it —
the same reason ingest keeps instrument paths verbatim.

Portability is an alias instead. Each link registers the mount its data sits on
(found by walking up to the first real mount point), mapping the prefix onto
itself. That is a no-op where the data was linked, and the one line to edit
anywhere else:

```python
wb.project.add_alias("/mnt/data", ["/facility/data"])    # on the next machine
```

### Giving links something to filter on

Links give an organiser files. `set_params` gives it columns:

```python
wb.set_params("CuAu05", stage="synthesis", au_fraction=0.55, temperature_C=90)
#   -> synthesis.au_fraction, synthesis.temperature_C in to_dataframe()
```

Promoted stage fields (`run_id`, `batch_tag`, `campaign`, `status`, `error`,
timings) are set on the `Stage`; everything else lands in `params`. Calling it
again merges.

`wb.add_sample("CuAu09", status="error")` creates a sample with no data at all,
which is a state worth being able to record: a synthesis that failed is a
result, and leaving it out biases every comparison drawn afterwards.
`wb.remove_sample()` forgets one — the record only; no file is touched.

`wb.catalog()` is the sample × technique matrix — ticks, or file counts with
`counts=True`. The gaps are the point: a campaign's measurement matrix is
always sparse, and knowing which comparisons exist beats discovering halfway
through that four samples never got the technique the argument rests on.

## Reading and drawing by sample and technique

With the organiser built, technique is an argument rather than a code path:

```python
x, Y, info = wb.data("CuAu05", "uvvis")      # (n_frames, n_points)
array, meta = wb.data("CuAu05", "tem", frame=1)
volume, meta = wb.data("CuAu01", "tomo")

wb.plot("CuAu05", "uvvis")                    # lines, coloured by time
wb.plot("CuAu05", "tem", frame=2)             # heatmap on nm axes
wb.plot("CuAu01", "tomo", engine="interactive", mode="volume")
wb.overlay("waxs1d", reduce="last")           # one curve per selected sample
```

`wb.plot` returns a matplotlib `Axes`, or a Plotly `Figure` with
`engine="interactive"`. The dispatch lives in `NanoOrganizer/viz/show.py`, so
the notebooks and the Visualize page make the same decisions about the numbers
— which frame a time selects, how a long series is strided down, where an
image's display range comes from.

### The layer below a measurement: frames

A measurement is rarely one number; it is forty spectra taken while the
reaction ran. `wb.frames(sample, modality)` is that layer as a table — one row
per file, with whatever the filename admitted about when (`t_s`) and how hot
(`T_c`) it was taken, parsed by the grammars in `analysis/frames.py`. Files no
grammar parses are listed with NaN, never dropped.

That table is what makes these addressable:

```python
wb.plot("CuAu05", "uvvis", frame=0)    # by position — always available
wb.plot("CuAu05", "uvvis", t=600)      # nearest frame to 600 s
wb.plot("CuAu05", "uvvis", T=90)       # nearest frame at about 90 °C
```

`t` and `T` take the **nearest** recorded value, not an exact one, because an
acquisition clock never lands on a round number.

## The table is the engine

`project.to_dataframe()` returns one row per sample: authored parameters as
dotted columns, derived values, and per-modality presence flags.

```
sample_id      synthesis.conditions.temperature_C  catalysis.status  has.tem  derived.peak1_center
Sample000001                                                       6.0              done     True         0.0123
Sample000002                                                       2.0              done    False            NaN
```

Everything else is built on this: filter the table to a region of interest, plot
the selected samples, batch-analyse them, write results back as new columns,
filter again. `has.*` columns are real booleans and `n_files.*` real integers —
never NaN — so filter widgets have something to bind to.

`project.to_dataframe(level="measurement")` gives one row per measurement with
its modality, group, stage and file count, which is what the visualisation pages
select from.

## Worked example

```python
from NanoOrganizer import Project

project = Project("/data/MyProject")
project.add_alias("/instrument/share", ["/mnt/instrument"])

project.ingest("MetaData/Synthesis_dict.py")
project.ingest("MetaData/Reaction_dict.py")
project.attach_folders()
project.save()

print(project.summary())

# samples whose synthesis used a 6:1 synthesis temperature
ids = project.filter(**{
    "synthesis.conditions.temperature_C": 6.0})

# their catalysis UV-Vis series, ready to read
for m in project.measurements(modality="uvvis", stage="catalysis", sample_ids=ids):
    files = m.resolve(project.resolver)
    axis = m.resolve_aux(project.resolver).get("wavelength_file")
```
