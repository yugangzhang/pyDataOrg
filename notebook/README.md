# Notebooks

A worked pipeline on **generated** projects — no data to download, nothing to
configure.

| | |
|---|---|
| `00_quickstart` | build the quick demo project, open it, see what resolves |
| `01_explore_filter` | the table, finding columns, filtering, the basket |
| `02_visualize` | curves, time-coded series, images, segmentation |
| `03_analyze_batch` | single runs, batches, derived columns |
| `04_compare` | structure–property plots, checked against the generator's truth |
| `05_multimodal_demo` | **the full tour** — fifteen techniques, one hidden number |
| `06_build_organizer` | build one yourself: link data wherever it lives, then plot by sample and technique |

Run `00`–`04` in order; they share one small project (UV-Vis and TEM, six
samples) written to `~/DemoProject`.

`05` stands alone and is the one to read if you want to see what the framework
is actually for. It builds the **showcase**: a synthetic Cu–Au alloy
nanocatalyst library for CO₂ reduction, with

* fifteen techniques across all four visualisation groups — UV-Vis, IR, Raman,
  XPS, XAS, EDS, SAXS (1D and 2D), WAXS, DLS, XPCS, electrochemistry, DFT,
  TEM, SEM and tomography;
* four stages — synthesis, characterization, testing, computation;
* a sparse measurement matrix, because beamtime is finite;
* one failed synthesis with no data at all.

Both projects have a hidden control variable the pipeline is meant to recover,
so the notebooks can check the answer — the one thing real data never lets you
do. In the showcase it is the gold fraction, and three independent techniques
recover it to within a couple of percent.

```python
from NanoOrganizer.demo import showcase_truth
showcase_truth()      # the answer key
```

`06` is the one to read if your data is **not** laid out the way `00`–`05`
assume — which is the usual situation. It opens an empty organizer and links
the showcase's files in from where they already are, then shows what that buys:
`wb.catalog()` for the sample × technique matrix, `wb.plot(sample, modality)`
for any of the four groups, `wb.frames()` and `t=` / `T=` for the layer below a
measurement, `wb.overlay()` across samples, and `links_table()` ↔
`link_table()` for the export round trip. It depends only on `05`'s generated
data, not on `05` itself.

Everything in `06` also has buttons on the **📁 Project** page, and it is the
same object either way: an organizer this notebook saves opens in the GUI with
its links, parameters and derived values intact, and one built with the buttons
opens here.

Or from a shell, without opening a notebook at all:

```bash
python -m NanoOrganizer.demo ~/NanoOrganizerDemo
```
