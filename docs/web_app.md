# The web app

```bash
streamlit run NanoOrganizer/web_app/Home.py     # or the `viz` console command
```

The app used to be a flat list of single-technique pages. It is now a
**five-step workflow** plus a tools section, with technique chosen *inside* the
Visualize page from the modality registry — so adding a technique changes no
page. A **Demo** page in front of the workflow walks the three notebooks with
buttons; [`gui_demo.md`](gui_demo.md) is the illustrated tour.

## The pages

| | |
|---|---|
| **🎓 Demo** | Notebooks 10 → 11 → 12 with buttons, on a Cu–Au catalyst campaign of fifteen techniques: simulate it, build an organizer from it, look, plot every group, fit, batch and compare against the answer key — each step showing the Python it ran |
| **📁 Project** | Open a folder, map recorded paths onto this machine, read the metadata dicts, attach data folders, **link data from anywhere**, save — or generate an example project to explore |
| **🌳 Structure** | Drill into a folder, a metadata file or an archive, one layer at a time |
| **🔎 Explore & Filter** | Filter the sample table; this sets the **selection** every later page uses |
| **📈 Visualize** | Draw any measurement, grouped by what the data *is* |
| **🧪 Analyze** | Run an analysis on one sample or the whole selection; results become new, filterable columns |
| **📊 Compare** | Plot a measured quantity against a synthesis parameter |

The loop is the point: **filter → analyse → new columns → filter again.**

Structure sits outside that loop: it is what you open *before* a project
exists, when the question is still "what is in this directory".

## Demo: the three notebooks, with buttons

The fastest way to learn the app, and the package under it. Six tabs walk one
campaign from raw files to a structure–property plot, calling the same
functions as `notebook/10_simulate_data` → `11_build_organizer` →
`12_use_organizer`, in the same order.

The campaign is the **Cu–Au showcase**: an alloy nanocatalyst library for CO₂
electroreduction — eight alloys and one failed run, fifteen techniques across
four stages (synthesis, characterization, testing, computation), all following
from one hidden number, the gold fraction. Four techniques are declared in
metadata dicts; four more (TEM, SEM, DLS, tomography) arrive as bare folders
nobody wrote a record for, which is the case the page links by hand.

| tab | mirrors | does |
|---|---|---|
| **1 · Simulate** | notebook 10 | draws the model (one number, fifteen shadows), then `build_showcase_project(ROOT)` writes the files and four metadata dicts, and `showcase_truth()` the answer key |
| **2 · Build** | notebook 11 | `Organizer(cuau.json)` beside the data, `ingest("MetaData/…_dict.py")` the four modules, `link(s, m, "TEMData/CuAu05")` the four folder techniques by hand — every path relative to the organizer — then `catalog()`, `save()` |
| **3 · Look** | notebook 12 A–B | `describe()`, `tree()`, `ids(query)`, `frames()` with time and temperature from the filenames, `data()` eager and lazy — a tomogram memory-mapped one plane at a time |
| **4 · Visualize** | notebook 12 C | a 2×4 gallery of all four groups from `plot(s, m, ax=ax)`; any technique static or interactive (the tomogram as a rotatable isosurface); `overlay(technique, …)` for any curve or correlation technique — it follows the one picked above, and can be changed on its own |
| **5 · Analyze** | notebook 12 D | `fit_peaks(q, I)` on arrays, then `plot_fit(…, ax=ax)` as a separate call, the lattice parameter and Vegard's composition; a segmentation check with `segment()` then `plot_segmentation()`; then nine `batch()` calls |
| **6 · Compare** | notebook 12 E–F | composition three ways (EDS, WAXS, XPS) against the answer key, the plasmon band, three sizes, the CO volcano via `plot_compare`, and a stored fit reloaded off disk without refitting |

Every tab ends with **The same in Python** — the calls it just made, using
only the package's own functions — so nothing on the page is a GUI-only path.
A tab whose prerequisite is missing says which tab to go back to rather than
failing. No helper on the page both computes and draws: it calls an analysis,
then a plot.

Everything lives in **one folder**, `demo_root("CuAu")` — `../OrgDemo/CuAu`
beside the source checkout, or under `$NANOORGANIZER_DEMO_ROOT`: the
campaign's files and `MetaData/`, the answer key `truth.csv`, the organizer
`cuau.json` and its stored fits in `results/` — the same files notebooks 10–12
write, so a notebook and the page can take turns on them. Every path the
organizer records is **relative to that folder**, so the folder moves, zips
and opens elsewhere as one piece, and `cuau.json` names nobody's home
directory. Simulating again rewrites the whole folder — the page says so
first, and lets go of the organizer it held. *Start over* removes only
`cuau.json` and `results/`, and only in a folder the generator made. The page
holds its organizer separately from the workflow pages until **Use this
organizer in the workflow pages** hands it over. In restricted mode a demo
folder outside the allowed roots is refused.

### Paths on screen are relative

No page shows an absolute path. A location is displayed with
`NanoOrganizer.core.pathmap.display_path` — relative to the folder the app was
started in (`../OrgDemo/CuAu`), or under `~` when that would take more than
three `..` — in captions, tables, code blocks and the default value of every
path box. What you type may be relative too: it is read against the app's
working directory and turned absolute before anything is opened, created or
checked against the allowed roots, so the security rules see the same path
they always did. A source linked on **Project** that sits inside the project
folder is recorded relative to it, like the Demo page's links.

[`gui_demo.md`](gui_demo.md) is the walkthrough, with screenshots.

## One selection, shared

Every page works on one `Workbench` held in `st.session_state`, so the basket
built on Explore is the basket Analyze and Compare act on. It is shown in the
sidebar on every page with a one-click **Clear** — a filter applied on one page
silently narrowing another page's results is exactly the surprise shared state
causes, so it is never invisible.

It is the same `Workbench` the notebooks use. A page and a notebook cannot
drift apart in behaviour, because there is only one implementation.

## Project: building an organizer, not just opening one

Everything `notebook/11_build_organizer` does has buttons, in the same order.
The page is the only one that writes, so all of it lives here.

**Open or create.** The path box takes either shape a project comes in:

* a **folder** — `MetaData/`, data folders, a store in `.nanoorganizer/`;
* a path ending in **`.json`** — a single-document organizer, the kind
  `Organizer("lab.json")` writes in a notebook.

They are the same object, so an organizer built in a notebook opens here with
its links, parameters, derived values and stored fits intact, and one built
here opens in a notebook. *Nothing yet* creates an empty one — a folder gets
the usual hidden store, a `.json` name gets a single document. Either way an
existing store is refused, because silently opening it when the user asked to
create one would be the wrong kind of helpful.

**Samples and their conditions.** An editable grid, one row per sample, one
column per parameter of the selected stage — `wb.set_params()` with a
spreadsheet on top. Add a column to record something new, add a row to create
a sample (a synthesis that failed has no files and is still a result), delete
a row to forget one. The stage that actually carries parameters is offered
first, so a project whose stages sort badly does not open on a blank grid.

**Link data from anywhere.** *Attach data folders* needs the
`<Modality>Data/<SampleID>/` layout under the project root. This does not:
pick a sample, a technique, and either a folder or a glob, and the files stay
exactly where they are. Nothing is copied.

The section says how many files match **before** you commit, because a link
that silently matches nothing is the failure worth spending a preview on. A
folder is listed now; *Keep it live* records a glob instead, so frames written
later appear — the one to use while a run is still going. *Extra extensions*
links files the technique does not normally claim. Links are listed back with
their recorded path and file count, and can be removed one at a time.

*Link a whole campaign from a table* takes a CSV — `sample_id`, `modality`,
`source`, optionally `stage` / `role` / `aux`, anything else becoming metadata.

**Save and export.** Saving writes `.nanoorganizer/` into the project folder
and nothing else. Three exports:

| | |
|---|---|
| **Links (CSV)** | one row per measurement, and the one that **comes back** — re-importable above or through `wb.link_table()` |
| **Sample table (CSV)** | parameters and derived values, for reading elsewhere |
| **Store (JSON)** | the whole organizer |

The links CSV is a genuine round trip: a pattern exports as that pattern, a
folder as its folder, and explicit paths as a `;`-joined list whenever listing
the folder would not reproduce them exactly — so a re-import can never quietly
link a different set of files. That is the reason it exists: a spreadsheet is
a better editor than a form when forty rows need the same fix.

These call `wb.link()`, `wb.link_folder()`, `wb.link_table()`,
`wb.links_table()` and `wb.set_params()` — see
[`sample_model.md`](sample_model.md#linking-data-that-is-somewhere-else-and-is-staying-there)
and `notebook/11_build_organizer`.

## Visualize dispatches on shape, not technique

The tabs are the four visualisation groups from
`NanoOrganizer/core/modality.py`:

| tab | shapes | techniques |
|---|---|---|
| **Curves (1D)** | curve, series | UV-Vis, Raman, IR, XPS, XAS, EDS, SAXS/WAXS 1D, XRD, DLS, electrochemistry, DFT DOS |
| **Images & Maps (2D)** | image, map | TEM, SEM, optical, cell, SAXS/WAXS 2D, GIWAXS |
| **Volumes (3D)** | volume, stack | tomography, z-stack |
| **Correlation** | corr, twotime | XPCS g₂, two-time |

The dispatch itself is library code in `NanoOrganizer/viz/show.py`, which is
what `wb.plot(sample, modality)` calls in a notebook. The page keeps its own
widget layer — sliders and colour pickers have no meaning in a notebook — but
the decisions that affect the *numbers* are shared: which frame a time or a
temperature selects, how a long series is strided down, where an image's
display range comes from, and how a volume is projected.

Only the groups present in the current selection are shown. A volume is drawn
as a single plane or as a **slab** projection: projecting the full depth of a
dense sample saturates, because everything is in front of something. Technique and stage
are selectors inside a tab; they change axis captions and defaults, not the code
path. Microscopy modalities additionally get a *Check the particle
segmentation* panel, because a size distribution should never be trusted
without looking at the outlines.

## Two rendering engines

Every drawing tab offers **Static** (matplotlib — the figure you would put in
a paper) and **Interactive** (Plotly — zoom a shoulder, read a pixel under the
cursor, rotate a volume). Volumes default to interactive, because a projection
answers *what is in there* and only rotation answers *what shape is it*;
everything else defaults to static.

![A rotatable rendering of the demo tomogram: a roughly spherical aggregate about 150 nm across, its interior threaded with pores, on calibrated nanometre axes](images/demo_tomogram.png)

*The demo tomogram in `volume` mode. The axes are in nanometres because the
measurement carries its voxel size; the title records the striding.*

The controls themselves live in `web_app/components/plot_controls.py` and
return a frozen settings object, so all four tabs share one vocabulary and a
control added there appears everywhere it applies:

| group | controls |
|---|---|
| curves | colour, marker, line style, width, marker size, opacity, log x/y, manual limits, grid, legend and its position, title and axis labels, figure size |
| images | colormap, log intensity, contrast percentile or manual range, equal aspect, origin, colour bar, draw as a 3D surface |
| volumes | isosurface / translucent volume / point cloud / orthogonal slices, threshold, opacity, shells, detail budget, slice positions — or the flat slice and slab projections |
| a stack of curves (`series_controls`, for `plot_series`) | which curves (evenly spaced, log spaced, every n-th, all, or listed — `series_indices`), colour map and what it spans, legend and its format, limits, log x/y, title, figure size |

`axis_limits` and `figure_size` are the two small pieces the panels are made
of, for a page that wants only those. Another package's pages use the same
panels: a project package's spectra can take `series_controls` unchanged.

Two traps worth knowing. Plotly's `Greys` runs white→black and its `RdBu` runs
red→blue — both the opposite way from the matplotlib colormaps of the same
name, so the mapping in `COLORMAPS` reverses them; without that, switching a
TEM micrograph to interactive turns the particles from dark to bright. And
Plotly has no `Bone` scale at all: asking for one raises. `tests/test_interactive.py`
checks every offered name against both.

Volumes are strided down before rendering and the figure title says by how
much. That is not politeness — a browser does not slow down gracefully on a
128³ translucent volume, it locks the tab.

## Structure reads layout, not data

Folders, JSON, HDF5, `.npz` and Python metadata modules all open the same way:
a node, its children, click one, repeat. A breadcrumb keeps every ancestor one
click away, so descending into the wrong branch costs nothing.

Shapes and dtypes come from file headers, so a 4 GB tomogram is described
without being opened, and nothing on the page loads a dataset or plots. An
address is a path optionally followed by `::` and a path inside the file —
`run.h5::entry/instrument` — which is what lets "descend into a folder" and
"descend into a file" be the same operation.

The traversal is `NanoOrganizer.structure`, so the same walk works from a
notebook: `print(structure.tree(path, depth=3))`.

Reading a `.py` metadata module **executes it**. The page says so before it
happens, and the allowed-roots rule applies here exactly as it does to the
folder picker — a structure browser must not become a way around it.

## Analyze builds its own controls

The settings form is generated from the analysis itself
(`web_app/components/settings_form.py`, from `Analysis.settings_for()` — the
method's keyword-only settings, or the adapter's options): a bool becomes a
toggle, a number a number box, a string a text box or a choice, a list of
numbers one text box (`316, 400`). A registered analysis therefore gets a
working form with no change to the page — the same principle as the modality
registry. `settings_form(key, widget_key, current)` returns the whole settings
dict `run`, `batch` and `run_method` take; *current* (say
`wb.kept_settings(key)`) is where the controls start, `settings_code` writes
the dict as a line for a notebook.

Settings whose default is `None` sit behind a "set" toggle (an `Optional[bool]`
is auto / yes / no). For these analyses `None` means *work it out from the
data* (the watershed seed spacing, the particle polarity), and silently
replacing that with a number would change results without anyone asking.

A single run does **not** write to the store by default; a batch does. An
exploratory click should not quietly change the results table.

## Compare checks for a confound

When points are coloured by a grouping column, the page compares the spread of
the y value *between* groups against the spread *within* any one group. If
between beats within, it says the grouping may be confounded with the x axis
and that you should compare within one group first. If every group holds a
single sample it says that instead — the two effects are then arithmetically
inseparable, and no warning dressed up as statistics would help.

It also reports the case where every group holds a single sample, since the
two effects are then arithmetically inseparable and no warning dressed up as
statistics would help.

## Tools

Retained general-purpose utilities, mounted from the old pages folder:
**Universal Plotter**, **Test Data Generator**, **Data Manager**. Each is
optional — a missing file is skipped rather than taking the app down.

## What happened to the old pages

Navigation is declared with `st.navigation`, which **disables `pages/`
auto-discovery**. The older single-purpose pages (CSV Plotter, Image Viewer, Multi-Axes, 3D
Plotter, Data Viewer) remain on disk and can still be run directly:

```bash
streamlit run NanoOrganizer/web_app/pages/2_CSV_Plotter.py
```

They are superseded by Visualize and the Universal Plotter. Re-listing one is a
single line in `sections` in `Home.py`.

## Extending it

- **A new technique** → one `register()` in `core/modality.py`. Visualize picks
  it up; no page changes.
- **A new analysis** → one `register_analysis()` in `analysis/__init__.py`.
  Analyze offers it, builds its form, and batches it.
- **A new authoring format** → one `register_adapter()` in `ingest/__init__.py`.

## Testing

`tests/test_webapp.py` drives the real pages through Streamlit's `AppTest`
against a synthetic project, so it needs no data mount. It clicks through the
interactions that matter rather than only checking that pages render.

`tests/test_webapp_demo.py` clicks through the Demo page — simulate, build,
fit, batch, compare, reload, hand over, start over — against the Cu–Au
campaign written into the test's own temporary folder, and checks that the
page recovers the hidden composition. A gallery panel that cannot be drawn is
reported as a warning, and the tests refuse warnings.

`tests/test_webapp_showcase.py` repeats the render checks against the
fifteen-technique demo project. That is the case the generalisation was for —
four visualisation groups, three stages, and a sample with no data at all —
and a two-technique fixture cannot exercise it.

One trap worth knowing: `AppTest.exception` is an **ElementList**, empty rather
than `None` when the page ran cleanly. Assert `not app.exception`; asserting
`app.exception is None` fails on every passing page.
