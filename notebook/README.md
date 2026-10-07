# Notebooks

Two tracks, both on **generated** data — nothing to download, nothing to
configure.

## The workflow: simulate → build → use

Start here. It is the shape a real campaign actually has — on a campaign big
enough to be worth organising: a **Cu–Au alloy nanocatalyst library for CO₂
electroreduction**, eight alloys and one failed synthesis, **fifteen
techniques across four stages**, all following from one hidden number per
sample, the gold fraction *x*.

| | |
|---|---|
| `10_simulate_data` | the campaign on disk: four metadata dicts that describe most of it, four techniques in bare folders that nobody described, a sparse matrix, and the answer key |
| `11_build_organizer` | `Organizer("cuau.json")` — `ingest` the four dicts, `link` the four folders by hand |
| `12_use_organizer` | reopen it and work, in six parts |

Run them in order; `11` and `12` use what `10` leaves in
`~/Repos/OrgDemo/CuAu`:

```
~/Repos/OrgDemo/CuAu/
├── Campaign/      the data and MetaData/*_dict.py   (10)
├── truth.csv      the answer key                     (10)
├── cuau.json      the organizer                      (11)
└── results/       stored fits                        (12)
```

`10` calls `NanoOrganizer.demo.build_showcase_project`. The same function is
behind `python -m NanoOrganizer.demo --campaign` (all of `10` in one command)
and the web app's **🎓 Demo** page, which walks `10` → `11` → `12` with
buttons — so the three routes write identical files and cannot drift apart.

`12` is laid out the way a session actually goes:

| | |
|---|---|
| **A** | load it, look at it (`describe`, `tree`, `catalog`), carve out a `subset` |
| **B** | load data — curves, images, a memory-mapped tomogram — eager, or `lazy=True` one frame at a time |
| **C** | visualise all four kinds of data — the quick call, your own figure from B, a rotatable tomogram |
| **D** | fit one diffraction pattern on arrays, turn it into a composition, *then* batch nine analyses across the campaign |
| **E** | compare: three routes to one composition, three sizes that disagree for a reason, and the Sabatier volcano straight off the table |
| **F** | reload, read the stored fits back, go round again |

Because the data is simulated, part E checks the answers: composition from
diffraction and from EDS lands on the generator's value (within 0.02), the
plasmon band within 1 nm, XPS reads the gold-rich *surface* rather than the
bulk, and the CO current peaks at the intermediate composition.

The through-line is that **nothing is a dead end**: every quick call has a
lower-level one underneath handing you the arrays, because the moment an
analysis gets interesting it stops fitting whatever the convenience function
assumed.

Two rules show up in every cell that draws. Analysing and drawing are **two
calls** — `fit_peaks` returns a result, `plot_fit` draws it — and every plot
takes **`ax=`**, draws into the figure you made, and returns the axes it drew
on. See [`docs/kernel_adapter_rule.md`](../docs/kernel_adapter_rule.md).

The organizer is **one JSON file you name** — not a directory layout, not a
hidden folder. A document you can copy, diff and version, holding where every
sample's data is, what it was made from, and what the analyses found. The data
itself never moves.

```python
org = Organizer(demo_root("CuAu", "cuau.json"))

org.ingest(CAMPAIGN / "MetaData" / "Testing_dict.py")    # what somebody wrote down
org.link("CuAu05", "tem", str(CAMPAIGN / "TEMData" / "CuAu05"))   # what nobody did
org.save()
```

**There is no auto-attach in this track, on purpose.** The four bare folders
happen to be named `<Modality>Data/<SampleID>/`, so `attach_folders()` would
find them — but almost no real campaign is laid out that way, and teaching it
as the normal route builds a habit that breaks on contact with one. These
notebooks link by hand, which is what you would actually do.

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

`legacy/05` is the same Cu–Au campaign `10`–`12` use, opened the older way —
as a directory project with `open_project`, the four bare folders picked up by
`attach_folders` — and with a few extra analyses (IR, the DFT d-band centre,
oxygen evolution) worth reading once you have done `12`.

## Both tracks hide a number on purpose

Each generated project has a control variable the pipeline is meant to
recover, so the notebooks can check the answer — the one thing real data never
lets you do. In the Cu–Au campaign (`10`–`12`, `legacy/05`) it is the gold
fraction, and diffraction and EDS recover it to within a couple of percent; in
the small project (`legacy/00`–`04`) it is the synthesis temperature.

```python
from NanoOrganizer.demo import showcase_truth
showcase_truth()      # the answer key; 10 also writes it to CuAu/truth.csv
```

Or from a shell, without opening a notebook at all:

```bash
python -m NanoOrganizer.demo --campaign       # what 10 writes
```

## Where generated data goes

Everything these notebooks write lands under **one parent**,
`NanoOrganizer.demo.demo_root()` — `~/Repos/OrgDemo` by default. Set
`$NANOORGANIZER_DEMO_ROOT` to put it somewhere else. Nothing is written to your
home directory itself, so a few runs cannot leave a scatter of folders behind.

```
~/Repos/OrgDemo/
├── CuAu/           10 -> 12: the campaign, the answer key, cuau.json, results/
├── DemoProject/    legacy 00 -> 04: the small project
└── Showcase/       legacy 05: the same campaign, as a directory project
```

## The same objects, with buttons

Everything in these notebooks is on the web app, driving the same `Workbench`:

```bash
streamlit run NanoOrganizer/web_app/Home.py       # or: viz
```

**🎓 Demo** is these three notebooks with buttons — simulate, ingest, link,
look, fit, batch, compare — each step showing the Python it ran.
**📁 Project** opens either shape — a project folder, or a path ending in
`.json` for an organizer a notebook wrote — and can create, link, edit
parameters and export without any Python. [`docs/gui_demo.md`](../docs/gui_demo.md)
walks through it with screenshots. A notebook and the GUI cannot drift
apart, because there is one implementation.
