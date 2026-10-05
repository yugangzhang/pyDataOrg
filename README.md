# NanoOrganizer

Organise experimental metadata, visualise any measurement, analyse in batch,
and compare across samples.

A laboratory accumulates data faster than it accumulates structure: a folder of
spectra here, a drive of micrographs there, and the conditions that produced
them in a notebook or a script. NanoOrganizer gives that material one
sample-centric model, so a question like *does the band shift with synthesis
temperature?* is a filter and a plot rather than an afternoon.

**The loop is the point: filter → analyse → new columns → filter again.**

```python
from NanoOrganizer import open_project

wb = open_project("/data/MyProject")
wb.filter("`synthesis.conditions.temperature_C` >= 90")
wb.batch("peak_fit")                     # writes derived columns back
wb.plot_compare("synthesis.conditions.temperature_C", "derived.peak1_center")
```

## Install

```bash
pip install -e ".[web,image]"
```

Dependencies are numpy, scipy, matplotlib and pandas; Pillow and scikit-image
for micrographs, Streamlit for the GUI. Nothing else.

## Try it without any data

Two complete projects are generated on demand. Nothing is downloaded, and
nothing is hidden: both are built from a control variable the pipeline is meant
to recover, and the generator will tell you what it was.

```bash
python -m NanoOrganizer.demo ~/NanoOrganizerDemo     # the full showcase
python -m NanoOrganizer.demo ~/NanoQuick --quick     # small and fast
```

or from the web app: **Project → No project yet? Generate an example one**.

**The showcase** is a synthetic Cu–Au alloy nanocatalyst library for CO₂
electroreduction, characterised the way a real campaign would be: fifteen
techniques across four stages, a sparse measurement matrix, and one synthesis
that failed. Everything in it follows from one number per sample — the gold
fraction — so independent techniques can be checked against each other.

```python
from NanoOrganizer import open_project
from NanoOrganizer.demo import build_showcase_project, showcase_truth

wb = open_project(build_showcase_project("~/NanoOrganizerDemo"))
wb.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.6), n_peaks=2,
         background="linear")            # the (111) peak measures composition
showcase_truth()                          # what the generator actually used
```

EDS, WAXS and UV-Vis each recover the composition to within a few percent;
TEM, DLS and SEM report three different sizes, all of them correct; and the CO
partial current peaks at an intermediate composition — a Sabatier volcano with
the DFT CO binding energy as its descriptor.

`notebook/05_multimodal_demo` is the tour. `notebook/00_quickstart` →
`04_compare` walk the same pipeline on the smaller project.

## The model

```
Project                    a directory of samples, its path aliases, its store
 └── Sample(sample_id)     the thing that persists
      ├── stages           one execution each, with its own provenance
      ├── measurements     one body of data each, referenced not loaded
      └── derived          computed values — filterable beside the authored ones
```

A sample is the unit, not a run: one sample is made once, used several times,
and characterised for weeks by different instruments. Keying on the sample
survives re-measurement; keying on a run scatters it.

Paths are stored **exactly as the instrument recorded them** and mapped per
machine, so a project whose data is not currently mounted still browses — it
reports as unreadable rather than breaking.

## Technique is metadata, not a code path

Visualisation dispatches on what the data *is*:

| group | shapes | techniques shipped |
|---|---|---|
| Curves (1D) | curve, series | UV-Vis, Raman, IR, XPS, XAS, EDS, SAXS/WAXS 1D, XRD, DLS, electrochemistry, DFT DOS |
| Images & Maps (2D) | image, map | TEM, SEM, optical, cell, SAXS/WAXS 2D, GIWAXS |
| Volumes (3D) | volume, stack | tomography, z-stack |
| Correlation | corr, twotime | XPCS g₂, two-time |

Adding a technique is one registry entry and changes no page:

```python
from NanoOrganizer.core.modality import Modality, register

register(Modality(key="pl", label="Photoluminescence", domain="wavelength",
                  shape="series", x_label="Wavelength (nm)",
                  y_label="Intensity (a.u.)", extensions=(".txt", ".csv"),
                  analyses=("peak_fit",), category="spectroscopy"))
```

## The web app

```bash
streamlit run NanoOrganizer/web_app/Home.py      # or: viz
```

Five pages sharing one selection — **Project → Explore & Filter → Visualize →
Analyze → Compare** — plus general-purpose plotting tools. The GUI drives the
same `Workbench` object the notebooks use, so the two cannot drift apart.

## Analyses

Three technique-neutral analyses ship with the package:

| | |
|---|---|
| `peak_fit` | one or more peaks plus a constant or linear background, on any 1D curve |
| `curve_metrics` | height, position, area, centroid and threshold crossing in a window — no model fitted |
| `particle_sizing` | micrographs: Otsu plus watershed, calibrated to nm from the image's own metadata |

`curve_metrics`' threshold crossing is the same operation as *the potential at
10 mA cm⁻²*, *the onset of an absorption edge* and *the lag time at which a
correlation function has half decayed*. Writing it once is the argument for a
modality registry in miniature.

An analysis that applies to several modalities prefixes its derived columns
with the modality it ran on — `derived.uvvis_peak1_center` beside
`derived.waxs1d_peak1_center` — so fitting two techniques cannot silently
overwrite one result with the other.

Chemistry-specific analyses belong in a package of their own and register
themselves on import:

```python
from NanoOrganizer.analysis import Analysis, register_analysis

register_analysis(Analysis(key="my_assay", func=my_assay, label="…",
                           modalities=("uvvis",), stages=("reaction",)))
```

Results carry their own provenance. A fit window, an R² and a point count are
part of a measurement, not decoration — and a batch reports its failures rather
than skipping them.

## Documentation

| | |
|---|---|
| [`docs/sample_model.md`](docs/sample_model.md) | the data model, path aliases, ingest |
| [`docs/analysis.md`](docs/analysis.md) | analyses, the registry, and decisions that affect the numbers |
| [`docs/web_app.md`](docs/web_app.md) | the GUI, and how to extend it |
| [`docs/demo_data.md`](docs/demo_data.md) | the generated example projects, and what is in them on purpose |
| [`docs/archive/`](docs/archive/) | notes from earlier versions, kept for reference |

## Extending it

| to add | do |
|---|---|
| a technique | `register()` a `Modality` |
| an analysis | `register_analysis()` an `Analysis` |
| a metadata format | `register_adapter()` an `Adapter` |
| a filename convention | `register_grammar()` a `FrameGrammar` |

## Tests

```bash
pytest
```

205 tests, including the Streamlit pages driven through `AppTest` against both
generated projects — the small one, and the fifteen-technique showcase that
exercises all four visualisation groups at once. No test needs a data mount.

## License

MIT — see [LICENSE](LICENSE).
