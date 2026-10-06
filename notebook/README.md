# Notebooks

Two tracks, both on **generated** data — nothing to download, nothing to
configure.

## The workflow: simulate → build → use

Start here. It is the shape a real campaign actually has.

| | |
|---|---|
| `10_simulate_data` | a rig writing files: three instruments, three folder trees, three naming conventions, none agreeing |
| `11_build_organizer` | `Organizer("lab.json")` — `ingest` what was written down, `link` what was not |
| `12_use_organizer` | reopen it and work, in six parts |

Run them in order; `11` and `12` use what `10` leaves in
`~/Repos/OrgDemo/Lab`.

`12` is laid out the way a session actually goes:

| | |
|---|---|
| **A** | load it, look at it (`describe`, `tree`, `catalog`), carve out a `subset` |
| **B** | load data — eager, or `lazy=True` one frame at a time |
| **C** | visualise — the quick call, or your own figure from B |
| **D** | `fit` one, check it, *then* `batch` the same parameters |
| **E** | compare: ids → table → plot |
| **F** | reload, read the stored fits back, go round again |

The through-line is that **nothing is a dead end**: every quick call has a
lower-level one underneath handing you the arrays, because the moment an
analysis gets interesting it stops fitting whatever the convenience function
assumed.

The organizer is **one JSON file you name** — not a directory layout, not a
hidden folder. A document you can copy, diff and version, holding where every
sample's data is, what it was made from, and what the analyses found. The data
itself never moves.

```python
org = Organizer(demo_root("Lab", "lab.json"))

org.ingest(synthesis=Synthesis_dict)       # the live dict, not a path to it
org.link("S03", "tem", "/mnt/scope/S03/")  # what nobody wrote down
org.save()
```

**There is no auto-attach in this track, on purpose.** `attach_folders()`
exists and works, but it needs `<Modality>Data/<SampleID>/` under one root —
a layout almost nobody has. Teaching it as the normal route builds a habit
that breaks on contact with a real campaign, so these notebooks link by hand,
which is what you would actually do.

## Does this scale?

Yes — keying on `sample_id` is not a small-campaign idea. With **10 000
samples** and one measurement each, on an ordinary laptop:

| | |
|---|---|
| ingest 10 000 records | 0.15 s |
| link 10 000 measurements | 0.10 s |
| save / load | 0.9 s / 0.4 s (13 MB) |
| `table()` (10 000 × 19) | 0.3 s |
| `filter()` | 0.1 s |
| `availability()` — touches the filesystem | 0.9 s |

Nothing in the model is per-pair or per-combination, so a plate-based
high-throughput campaign uses exactly the same calls as a six-sample one.
`tests/test_organizer.py` keeps a guard on it.

## The pipeline tour

Kept in [`legacy/`](legacy/). The older track, on a project that *is* laid out
as a directory.

| | |
|---|---|
| `legacy/00_quickstart` | build the demo project, open it, link its micrographs, see what resolves |
| `legacy/01_explore_filter` | the table, finding columns, filtering, the basket |
| `legacy/02_visualize` | curves, time-coded series, images, segmentation |
| `legacy/03_analyze_batch` | single runs, batches, derived columns |
| `legacy/04_compare` | structure–property plots, checked against the generator's truth |
| `legacy/05_multimodal_demo` | **the full tour** — fifteen techniques, one hidden number |

Run `legacy/00`–`04` in order; they share one small project (UV-Vis and TEM, six
samples) written to `~/Repos/OrgDemo/DemoProject`.

`legacy/05` stands alone and is the one to read for what the framework is *for*. It
builds a synthetic Cu–Au alloy nanocatalyst library for CO₂ reduction, with

* fifteen techniques across all four visualisation groups — UV-Vis, IR, Raman,
  XPS, XAS, EDS, SAXS (1D and 2D), WAXS, DLS, XPCS, electrochemistry, DFT,
  TEM, SEM and tomography;
* four stages — synthesis, characterization, testing, computation;
* a sparse measurement matrix, because beamtime is finite;
* one failed synthesis with no data at all.

## Both tracks hide a number on purpose

Each generated project has a control variable the pipeline is meant to
recover, so the notebooks can check the answer — the one thing real data never
lets you do. In `10`–`12` it is the synthesis temperature, recovered
independently from a plasmon band and from a diffraction line width. In the
showcase it is the gold fraction, and three techniques recover it to within a
couple of percent.

```python
from NanoOrganizer.demo import showcase_truth
showcase_truth()      # the answer key
```

Or from a shell, without opening a notebook at all:

```bash
python -m NanoOrganizer.demo ~/Repos/OrgDemo/Showcase
```

## Where generated data goes

Everything these notebooks write lands under **one parent**,
`NanoOrganizer.demo.demo_root()` — `~/Repos/OrgDemo` by default. Set
`$NANOORGANIZER_DEMO_ROOT` to put it somewhere else. Nothing is written to your
home directory itself, so a few runs cannot leave a scatter of folders behind.

```
~/Repos/OrgDemo/
├── Lab/            10 -> 12: scattered raw data + lab.json
├── DemoProject/    00 -> 04: the small project
└── Showcase/       05: the fifteen-technique campaign
```

## The same objects, with buttons

Everything in these notebooks is on the web app, driving the same `Workbench`:

```bash
streamlit run NanoOrganizer/web_app/Home.py       # or: viz
```

**📁 Project** opens either shape — a project folder, or a path ending in
`.json` for an organizer a notebook wrote — and can create, link, edit
parameters and export without any Python. A notebook and the GUI cannot drift
apart, because there is one implementation.
