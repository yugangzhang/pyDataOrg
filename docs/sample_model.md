# The sample-centric model

pyDataOrg started out organised around *runs* (`project/experiment/run_id`)
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
`pyDataOrg/core/modality.py`. It needs no new page, no new loader branch,
and no change anywhere else:

```python
from pyDataOrg.core.modality import Modality, register

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

When the same prefixes recur on every machine a project is opened on, name
the machines once instead (`pyDataOrg.servers`):

```python
from pyDataOrg.servers import Server, register_server

register_server(Server("workstation", {"/instrument/share": "/mnt/instrument"}))
org = Organizer("project.json", server="workstation")   # or "auto": the one mounted here
org.local("/instrument/share/spectra/S01/*.csv")        # the recorded path, as seen here
```

## Ingest: the authored file stays the source of truth

Instrument-side metadata is a plain Python module of sample-keyed dicts, often
built by a helper function so ten samples sharing a protocol are not ten
hand-copied blocks. That convenience is why the file must be *executed* to be
read — see the warning in `pyDataOrg/ingest/pydict.py`; only ingest modules
you or your collaborators wrote.

`project.ingest(path)` reads it into the canonical store at
`.pydataorg/samples.json`. The authored file is never edited. Re-ingesting
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
`pyDataOrg/ingest/__init__.py`. Adapters never write to disk.

### Ingesting a dict rather than a file

A file is the right shape when metadata was *authored* at the instrument and
must not be edited in place. A notebook has the other case: the dict is being
written right now, and the loop is edit it, ingest, look, edit again. So
`ingest` takes the dict itself:

```python
org.ingest(synthesis=Synthesis_dict)          # the keyword names the stage
org.ingest(Synthesis_dict, stage="synthesis") # the same thing
```

The keyword form exists because a dict's variable name is invisible once it
has been passed in — `ingest(d)` cannot know it was called `Synthesis_dict`,
and guessing the stage from a file name is not available either.

Both forms end in the same `record_to_sample`, so a record behaves identically
whichever way it arrived.

**`replace=True` is what makes an editing loop honest.** Merging can only ever
add, so a key you popped from the dict would sit in the store forever looking
like data. With `replace`, the mapping is the whole truth for its stage:

| edit | effect |
|---|---|
| a new record | the sample is created |
| a changed value | the stage's parameters are replaced, not merged |
| a popped record | that sample loses this stage — and goes entirely if that was all it had |

A sample with links of its own survives losing its stage, because linked data
is not the dict's to delete.

## Folder convention: the tidy case

`<Modality>Data/<SampleID>/` attaches automatically. This is the **exception**,
not the normal route: almost no campaign is laid out this way, because the
microscope, the beamline and the spectrometer each write where they write.
Reach for it when a directory genuinely has this shape, and
[link](#linking-data-that-is-somewhere-else-and-is-staying-there) otherwise.

```
MyProject/
├── MetaData/      Synthesis_dict.py, Reaction_dict.py
├── TEMData/
│   └── Sample000001/   1.tif … 5.tif, note.txt
└── SEMData/, DLSData/, ECData/, RamanData/
```

`project.attach_folders()` walks those directories, matches each against the
modality registry, keeps only files with an extension that modality claims, and
picks up a side-car `note.txt` into the measurement's metadata. Folder names
are configurable through `ProjectConfig.modality_dirs`.

`open_project(root, attach=False)` turns it off, which is the right default
when you intend to link deliberately — an auto-attach that half-works is
harder to notice than one that did not run.

## Linking: data that is somewhere else and is staying there

The folder convention covers data laid out under the project root. The common
case is the other one: the micrographs are on the microscope's share, the
scattering on a beamline mount, the spectra in whatever folder somebody made
that afternoon, and none of it is going to move.

`link()` records where data is instead of collecting it:

```python
from pyDataOrg import Organizer

org = Organizer("../OrgDemo/cuau.json")          # the file is the store

org.link("CuAu05", "uvvis", "/mnt/specs/CuAu05/*.csv", stage="synthesis")
org.link("CuAu05", "tem",   "/mnt/scope/session17/")
org.link("CuAu05", "waxs1d", ["/beamline/2024_3/w1.dat"])
```

Three entry points, all returning a `Workbench`:

| | |
|---|---|
| `Organizer("x.json")` | one named document; its parent is only used to resolve relative paths |
| `open_project(root)` | an existing project directory — or a `.json`, which routes to `Organizer` |
| `new_organizer(root)` | an empty project directory, with the usual hidden store |

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

A link records the path **exactly as given**. Nothing is silently made
relative or absolute, because a rewritten store only works on the machine that
wrote it — the same reason ingest keeps instrument paths verbatim.

**A relative path is relative to the project root** — for an organizer, the
folder its JSON sits in; never the directory a notebook or the GUI happens to
be running from. Keep data beside the organizer and link it relatively, and
the folder is portable as one piece, with nothing to configure:

```python
org = Organizer("../OrgDemo/CuAu/cuau.json")
org.ingest("MetaData/Testing_dict.py")              # relative to cuau.json
org.link("CuAu05", "tem", "TEMData/CuAu05")         # recorded as TEMData/CuAu05/01.tif, …
```

A relative folder lists its files as relative paths, a `results/` fit is
linked relative, and the provenance of ingested stages names the metadata file
relative to the root — so a store built this way names nobody's home
directory, and opens unchanged wherever the folder is copied.

Data that lives elsewhere is linked by its absolute path. Portability is then
an alias. Each such link registers the mount its data sits on (found by walking
up to the first real mount point), mapping the prefix onto itself. That is a
no-op where the data was linked, and the one line to edit anywhere else:

```python
wb.project.add_alias("/mnt/instrument", ["/data/instrument"])    # on the next machine
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

Reading it back is `metadata` — the whole record of a stage, as it was
ingested or set, not just the columns flattened from it:

```python
wb.metadata("CuAu05")                    # {"synthesis": {...}, ...}: every stage
wb.metadata("CuAu05", "synthesis")       # one; a copy — editing it changes nothing
```

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
`engine="interactive"`. The dispatch lives in `pyDataOrg/viz/show.py`, so
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

## Results: analysis output, linked back

An analysis produces three things and they persist in two places, for a
reason:

| | |
|---|---|
| `values` | scalars — written onto the sample as `derived.*`, saved with the store, filterable beside the authored parameters |
| `curves` | the fitted line, the residuals — written **beside** the store as a `.npz` and linked back as a measurement |
| `diagnostics` | the window, the R², the point count — travel with the curves |

Arrays stay out of the store because a sample store that accumulates spectra
stops being something you can open in a text editor, and that readability is
most of its value.

```python
org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.6), link=True)
org.save()

later = Organizer("../OrgDemo/cuau.json")
later.results()                           # one row per stored result
later.result("CuAu05", "peak_fit")        # the AnalysisResult back
later.plot_result("CuAu05", "peak_fit")   # redrawn, not refitted
```

`folder=` puts the files somewhere else — a project's own `Results/` when
several organizers share one folder — and the link records it relative to the
organizer's folder (`../Project/Results/…`). `write=False, link=True` keeps
the values in the files only; `results(analysis="peak_fit")` reads them back
as a table.

```python
org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.6),
          write=False, link=True, folder="../Project/Results")
```

A kept result is also what makes the next run cheap: run the same analysis
with the same settings again and it is loaded, not recomputed
(`overwrite=True` to recompute) — see *One settings dict, three levels* in
[analysis.md](analysis.md).

A stored fit is linked as a measurement of modality **`fit`**, stage
`analysis`, role = ``{analysis}-{source_modality}`` — the modality is in the
role for the same reason it is in the derived column names: peak-fitting a
UV-Vis band and then a diffraction peak are *two* results, and a shared id
would make the second quietly replace the first. `result()` and
`plot_result()` take `modality=` to pick between them. It gets its own modality rather than
reusing the source's so that attaching a fit can never make
`plot(sample, "uvvis")` ambiguous between the spectrum and the curve drawn
through it. `plot(sample, "fit")` and `plot_result()` both reach it; the
ordinary dispatch knows a result bundle is not a plain array and does not try
to read it as one.

The file is a plain `.npz` — one entry per curve plus a JSON sidecar, readable
with `numpy.load` alone, because an archive format nobody else can open is not
an archive.

## Working with it: subsets, lazy frames, one fit at a time

Three things a session needs that a one-call convenience layer cannot give.

### Looking at the organiser

```python
org.describe()        # samples, stages, techniques, stored fits, readability
org.overview()        # the same thing as a dict, to branch on
org.tree(depth=2)     # structure, not data — of the *live* session
org.catalog()         # the sample x technique matrix; the gaps are the point
org.ids(query)        # answer a question without committing to it
```

`tree()` walks the current session rather than the file on disk. The
distinction is not pedantry: walking the saved file after twenty unsaved links
would show the earlier state and look entirely correct.

### Subsets

```python
plate = org.subset(["S01", "S03", "S07"], name="plate_A")
hot   = org.subset(query="`synthesis.temperature_C` >= 100")
```

A subset is a **deep copy**, not a view, so analysing it cannot write derived
values back into the parent by accident — the one thing a shared view would get
wrong. Aliases come along, so the data still resolves, and **nothing is
written** until you `save()` it.

For a one-off comparison a subset is overkill; `overlay`, `table` and
`catalog` all take `sample_ids=[...]` and leave the selection alone.

### Lazy frames

Eager reading is right until it is not. Forty spectra is 100 kB and arguing
about it costs more than reading it; four hundred micrographs is 12 GB, and a
notebook that reads them to show you the third one is a notebook you restart.

```python
frames = org.data("S01", "tem", lazy=True)
len(frames)                  # resolved up front — no file opened
array, info = frames[2]      # one file opened
for array, info in frames:   # one at a time, never all at once
    ...
stack, info = frames.load()  # all of them, having asked
```

It is a **sequence, not a generator**: a generator cannot be indexed, cannot
report its length, and is empty the second time you use it — all three of
which a session wants within five minutes. A single file holding a 3D volume
is memory-mapped, so its frames are planes and indexing one costs one plane.

### One fit, then the batch

```python
params = dict(x_range=(2.5, 3.6), n_peaks=1, background="linear")

trial = org.fit("S01", "waxs1d", **params)    # stores nothing, draws nothing
org.plot_fit(trial)                            # looking is a second call
org.batch("peak_fit", modality="waxs1d", link=True, **params)
```

Fitting and drawing are separate calls on purpose: a function that does both
can be used for neither on its own.

Settling the parameters on a sample you can look at, and only then spending
them on the whole set, is the same work as running the batch first and reading
its R² column afterwards — in the order that does not hide the mistake.

## Does it scale?

Keying on `sample_id` is not a small-campaign idea. With **10 000 samples**,
one measurement each, on an ordinary laptop: ingest 0.15 s, link 0.10 s, save
0.9 s (13 MB), load 0.4 s, `table()` 0.3 s, `filter()` 0.1 s, and
`availability()` — which actually touches the filesystem — 0.9 s.

Nothing in the model is per-pair or per-combination: a plate-based
high-throughput campaign uses exactly the same calls as a six-sample one. The
operations that touch the filesystem (`availability()`, `catalog(counts=True)`)
are the ones that will feel a slow mount, and they are the ones you can skip.

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

The whole loop, from an empty file to a fit you can read again next year.

```python
from pyDataOrg import Organizer

org = Organizer("../OrgDemo/cuau.json", name="Cu-Au CO2RR")
org.project.add_alias("/instrument/share", ["/mnt/instrument"])

# 1. Metadata somebody already wrote — a live dict, or a *_dict.py.
org.ingest(synthesis=Synthesis_dict)
org.ingest("MetaData/Reaction_dict.py")

# 2. Data nobody wrote down, one call per measurement.
for sample_id in org.project.sample_ids():
    org.link(sample_id, "tem", f"/mnt/scope/{sample_id}/")
    org.link(sample_id, "waxs1d", f"/beamline/2026_1/{sample_id}.dat")

# 3. Anything else worth filtering on.
org.set_params("CuAu05", stage="synthesis", operator="RH")

print(org.summary())
org.catalog()                      # what exists, and what does not

# 4. Filter, draw, fit — and keep the fits.
org.filter("`synthesis.conditions.temperature_C` >= 90")
org.plot("CuAu05", "uvvis", t=600)
org.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.6), link=True)
org.save()
```

Later, on another machine — one alias, and everything resolves:

```python
org = Organizer("../OrgDemo/cuau.json")
org.project.add_alias("/mnt/scope", ["/Volumes/scope"])

org.table()[["synthesis.conditions.temperature_C",
             "derived.waxs1d_peak1_center"]]
org.plot_result("CuAu05", "peak_fit")      # redrawn, not refitted
```

The lower-level objects stay reachable throughout — `org.project` is a
`Project`, `org.resolver` a `PathResolver` — so nothing here is a wall.
