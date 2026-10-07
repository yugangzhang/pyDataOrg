# How the GUI works — a walkthrough with the demo

The web app is the package with buttons on it. It drives the same
`Organizer` object the notebooks use and calls the same functions, so this
walkthrough is also a tour of the Python API: every step below names the call
it makes.

The route is the **🎓 Demo** page. It does what the three workflow notebooks
do — `notebook/10_simulate_data` → `11_build_organizer` → `12_use_organizer` —
in six tabs, on a real-shaped campaign, then hands the result to the workflow
pages.

**The campaign.** A Cu–Au alloy nanocatalyst library for CO₂
electroreduction: eight alloys and one synthesis that failed, characterised by
**fifteen techniques across four stages** — UV-Vis, EDS, XPS, Raman, IR, SAXS
(1D and 2D), WAXS, XAS, XPCS, DLS, TEM, SEM, tomography, electrochemistry and
DFT. Everything in it follows from **one hidden number per sample, the gold
fraction x**, so techniques that never met can be checked against each other —
and against the answer key the generator keeps.

All screenshots were taken from a fresh run with the demo data written to
`/tmp/OrgDemo`.

---

## 1. Start the app

```bash
pip install -e ".[web,image]"                    # once: Streamlit, Plotly, Pillow, scikit-image
streamlit run NanoOrganizer/web_app/Home.py      # → http://localhost:8501
```

That is the open mode, for your own machine. On a shared machine use the
console command, which adds a password and fences the file browser:

```bash
viz                  # port 8800, asks for a password to set
viz 8900 s3cret      # port and password given
```

Either way the server binds every interface so the app is reachable by
hostname; set `NANOORGANIZER_HOST=127.0.0.1` to keep it local. Demo data goes
under `~/Repos/OrgDemo` — set `NANOORGANIZER_DEMO_ROOT` to put it elsewhere.

The sidebar lists the pages. **Workflow** is the part that matters:

| page | what it is for |
|---|---|
| 🔬 Overview | what the app is, and where to start |
| 🎓 **Demo** | this walkthrough: notebooks 10–12 as six tabs |
| 📁 Project | open or create an organizer, link data, edit parameters, save |
| 🌳 Structure | look inside a folder, a JSON file or an HDF5 file before organising it |
| 🔎 Explore & Filter | filter the sample table; this sets the **selection** every later page uses |
| 📈 Visualize | draw any measurement, chosen by what the data *is* |
| 🧪 Analyze | run an analysis on one sample or the whole selection |
| 📊 Compare | plot a fitted quantity against a synthesis parameter |

Below the page list, the sidebar always shows the open organizer and the
current selection, so a filter set on one page never silently narrows
another.

---

## 2. The Demo page, tab by tab

Open **🎓 Demo**. The **Demo folder** at the top is where everything goes —
`~/Repos/OrgDemo/CuAu` by default:

```
CuAu/
├── Campaign/     the files the instruments wrote, and four metadata dicts
├── truth.csv     the answer key
├── cuau.json     the organizer (tab 2)
└── results/      stored fits (tab 5)
```

Each tab starts with a caption saying which notebook part it mirrors, and ends
with **The same in Python**: the exact calls it just made, ready to paste into
a notebook. A tab whose prerequisite is missing says which tab to go back to.

### 1 · Simulate — `notebook/10`

![The Simulate tab: headline counts of 8 alloys plus one failed run, 15 techniques, 4 stages and 1 hidden number; six panels of the model against gold fraction — a straight Vegard lattice line, one plasmon band moving from 580 to 520 nm, three sizes an order of magnitude apart on a log axis, the surface richer in gold than the bulk, the d-band centre and CO binding energy, and a CO-current volcano; then after the button, 339 files and 15 MB on disk, the campaign's folder tree, CuAu05's characterization record, the sparse beamtime matrix and the answer-key table](images/gui_demo_simulate.png)

Before anything is written, the tab draws **the model**: one number, fifteen
shadows. Gold widens the lattice (Vegard's law, which WAXS reads), moves the
single plasmon band (the sign of an alloy, not a mixture), grows the
particles, segregates to the surface, deepens the d-band and weakens CO
binding — and CO binding sets the selectivity, so the CO current is a
volcano.

**Simulate the campaign** then writes what the campaign left behind, and the
answer key beside it:

```python
from NanoOrganizer.demo import build_showcase_project, showcase_truth

build_showcase_project(ROOT / "Campaign")                 # files + four metadata dicts
showcase_truth().to_csv(ROOT / "truth.csv", index=False)  # what the generator used
```

What landed is shown three ways. The **tree** (`structure.tree`, which reads
layout, not data) shows instrument folders that do not agree. The **record**
for one sample shows that the operators wrote one metadata module per stage,
and that any block naming files will become a measurement. And four folders —
`TEMData/`, `SEMData/`, `DLSData/`, `TomoData/` — have **no record at all**:
tab 2 links them by hand. The sparse matrix says which samples got the
beamtime-limited techniques; a real campaign is never complete.

### 2 · Build — `notebook/11`

![The Build tab: the organizer at /tmp/OrgDemo/CuAu/cuau.json with 9 samples and 144 measurements; the ingested table of nominal gold fraction, status, CO Faradaic efficiency and CO current, with CuAu09 marked error; the catalog as a shaded sample-by-technique matrix of file counts — 14 UV-Vis frames, 9 electrochemistry files, 3 TEM and 3 SEM images per sample, sparse XAS, XPCS, SAXS 2D and tomography, and an all-zero row for CuAu09; and a saved confirmation of 213 kB](images/gui_demo_build.png)

Four buttons, in order:

| button | call | what you see |
|---|---|---|
| **Create Organizer(cuau.json)** | `org = Organizer(ROOT / "cuau.json", name="Cu-Au CO2RR library")` | an empty organizer — one JSON file you name |
| **Ingest the four metadata dicts** | `org.ingest(CAMPAIGN / "MetaData" / f"{stage}_dict.py")` per stage | nine samples, their conditions, results and DFT descriptors; most measurements came in with the dicts |
| **Link the four folder techniques by hand** | `org.link(sample, "tem", folder, stage="characterization")`, and the same for SEM, DLS, tomography | the catalog fills in: 144 measurements in all |
| **Save cuau.json** | `org.save()` | the file on disk, plus the re-importable links table |

Linking a folder keeps only files matching the technique's extensions, so the
`note.txt` beside each set of micrographs is left out. Paths are recorded
exactly as given, and the data never moves. `CuAu09`, the failed synthesis,
stays in the catalog as an empty row: leaving it out would bias every later
comparison.

If `cuau.json` already exists — perhaps written by notebook 11 — the first
button becomes **Reopen cuau.json** and brings back everything in it. **Start
over** deletes only `cuau.json` and `results/`, never the campaign, and asks
for confirmation first.

### 3 · Look — `notebook/12` parts A–B

![The Look tab: describe() listing 9 samples, four stages, curves, images, a correlation and a volume, 144 readable measurements; the tree of cuau.json; an ids() query for gold fraction at least 0.5 returning CuAu05 to CuAu09, with a note that the failed CuAu09 answers too; the frames() table of the UV-Vis growth series with times and temperatures parsed from filenames; and the shapes data() returns, eager and lazy, including one memory-mapped plane of the tomogram](images/gui_demo_look.png)

What the organizer holds, without reading any data:

* `describe()` gives the counts, stages, techniques by group and
  readability; `tree()` walks the live session one layer at a time.
* `ids(query)` answers a question without changing the selection. The default
  query — gold fraction ≥ 0.5 — returns `CuAu09` too: a failed run keeps its
  nominal parameters, which is exactly the surprise worth meeting here rather
  than in a figure.
* `frames("CuAu05", "uvvis")` lists one row per file, with the time (`t_s`)
  *and* the temperature (`T_c`) each filename gave. `data(..., t=600)` and
  `data(..., T=60)` select the nearest frame by either.
* `data(..., lazy=True)` returns the file list without opening anything; a
  file is read only when indexed. A tomogram held in one `.npy` is
  memory-mapped, so `planes[64]` reads one plane, not the volume.

### 4 · Visualize — `notebook/12` part C

![The Visualize tab for CuAu01: a two-by-four gallery — UV-Vis growth series coloured by time, WAXS on a log axis, SAXS log-log, Faradaic efficiency per product against potential, a TEM micrograph and an SEM micrograph in grey on nanometre axes, a tomogram slab projection, and an XPCS correlation function; below it the tomogram rendered as a rotatable 3D isosurface on nanometre axes; and an overlay of the WAXS (111) reflection for CuAu01, 03, 05 and 08 moving from 3.01 to 2.67 inverse ångström as gold is added](images/gui_demo_visualize.png)

**Four groups, one call each.** The gallery draws all four visualisation
groups for one sample — curves, images, a volume, a correlation function —
each with one `org.plot(sample, technique, ax=ax)` into a figure the page
made:

```python
fig, axes = plt.subplots(2, 4, figsize=(16, 7.6))
org.plot("CuAu01", "uvvis", ax=axes[0, 0])              # coloured by time
org.plot("CuAu01", "ec", role="co2-rr-fe", ax=axes[0, 3])
org.plot("CuAu01", "tem", ax=axes[1, 0], cmap="gray")   # on nanometre axes
org.plot("CuAu01", "tomo", ax=axes[1, 2], slab=16)      # a slab projection
```

The figure follows what the data *is*: the UV-Vis series is coloured by
acquisition time from the filenames, SAXS is log-log because the technique's
registry entry says so, and the micrographs sit on nanometre axes because the
TIFFs carried their pixel size. `CuAu01` is the default because it got
everything — the tomogram, XPCS and the 2D detector images.

**Any technique, either engine.** Pick any of the sample's techniques and
switch **Engine** to *interactive* for the Plotly version. The showpiece is
the tomogram: an isosurface you can turn around, on the voxel size recorded
when it was linked — or a translucent volume, a point cloud, or three
orthogonal slices.

**Overlay.** `org.overlay("waxs1d", sample_ids=…, ax=ax)` puts one curve per
sample on a shared axis. Zoomed on the (111) reflection, it shows Vegard's law
by eye: gold opens the lattice, and the peak walks to lower q.

### 5 · Analyze — `notebook/12` part D

![The Analyze tab: fit controls set to CuAu05, window 2.50–3.60, two peaks, pseudo-Voigt, linear background; the two-peak fit drawn over the data with residuals beneath and R² 0.9999; the (111) at 2.8123 per ångström, lattice parameter 3.8698 Å and gold fraction 0.550 from Vegard, +0.000 against the answer key; a TEM frame of CuAu05 with 58 particles outlined in red; the nine batch calls listed; and 72 of 72 analyses succeeded across 9 batches](images/gui_demo_analyze.png)

**The kernel first.** The page takes CuAu05's WAXS arrays and fits them
directly; the (111) position gives the lattice parameter, and Vegard's law run
backwards gives the composition:

```python
q, I, info = org.data("CuAu05", "waxs1d")
fit = fit_peaks(q, I[0], n_peaks=2, x_range=(2.5, 3.6),
                shape="pseudo_voigt", background="linear")     # the analysis
plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, ax=ax)         # the picture
x_au = mat.fraction_from_lattice(mat.lattice_from_q(fit.params["peak1_center"]))
```

It lands on **x = 0.550** — the generator's value. The fit and the figure are
**two separate calls**: `fit_peaks` computes and draws nothing, and `plot_fit`
draws and computes nothing. Change a control and both run again. Set
**Peaks** to 1: the sharp (111) still pins the centre, so the composition
barely moves — but R² drops and the residual grows a second peak. The
residual is the tell, not the headline number.

**Look before you trust a size.** `org.segment("CuAu05", "tem")` segments one
frame and returns the label map; `org.plot_segmentation(seg, ax=ax)` draws the
outlines over it. A size histogram looks plausible whether the outlines were
right or not, so this is the check behind the TEM batch.

**Then the batches.** **Run the campaign's analyses** spends the parameters on
every sample — nine `batch()` calls: the WAXS peaks and the plasmon band
(`peak_fit`, with `link=True` so their curves are stored), the EDS and XPS
line areas (`curve_metrics`, one prefix per line), TEM and SEM sizes
(`particle_sizing`) and the DLS peak (`curve_metrics`). Each writes its
numbers back as `derived.*` columns; the page reports every batch's
successes, and the reasons for any failure.

### 6 · Compare — `notebook/12` parts E–F

![The Compare tab: EDS composition within ±0.021, WAXS within ±0.000, the plasmon band within 1.0 nm, and CuAu05 the best CO producer at x = 0.55; three panels — EDS and WAXS compositions on the parity line, XPS lying above the bulk, a little short of the true surface curve, and the fitted plasmon band on its truth line; three sizes on a log axis, SEM agglomerates near 200 nm, DLS near 25 nm and TEM near 10 nm; the CO partial current against DFT CO binding energy rising to CuAu05 and falling again — a volcano; and a stored CuAu05 WAXS fit reloaded from disk with its residuals](images/gui_demo_compare.png)

This tab goes ids → table → numbers → plots, and checks every number against
the answer key:

* **Composition three ways.** EDS (an X-ray detector on an electron
  microscope) lands within ±0.021 of the true gold fraction; WAXS (a
  diffractometer in another room) on it. XPS, which sees only the top
  nanometres, lands *above* the bulk — by 0.07 on average, close to the
  true surface enrichment — because gold segregates out. The disagreement is
  the physics.
* **One band, not two.** The fitted plasmon band is within 1 nm of the truth
  at every composition — a single band moving smoothly is how an alloy shows
  itself.
* **Three sizes, all right.** TEM sees primary particles (~10 nm), DLS the
  hydrated, intensity-weighted object (~25 nm), SEM the agglomerates
  (~200 nm). An order of magnitude apart, and each correct for what it sees.
* **The volcano, straight off the table.** `plot_compare` puts the authored CO
  partial current against the DFT CO binding energy: it rises, peaks at
  `CuAu05`, and falls — the Sabatier principle, and the reason anyone builds a
  composition series.

```python
x_eds = mat.fraction_from_signals(t["derived.eds_au_area"], t["derived.eds_cu_area"],
                                  gold_factor=EDS_K_FACTOR_AU_CU)
plot_compare(table, "computation.descriptors.E_ads_CO_eV",
             "testing.performance.j_CO_mA_cm2", ax=ax, title="Sabatier volcano")
```

**Reload from disk and redraw** opens a *fresh* `Organizer` from the saved
file and draws a stored fit with `plot_peak_fit(result, ax=ax)`. The curves
come off disk; nothing is refitted.

```python
later = Organizer(ROOT / "cuau.json")
result = later.result("CuAu05", "peak_fit", modality="waxs1d")
plot_peak_fit(result, ax=ax)
```

---

## 3. Carry on in the workflow pages

The demo organizer is the page's own until you hand it over. **Use this
organizer in the workflow pages**, at the bottom of the Demo page, makes it
the one every workflow page works on; the sidebar now names it.

![The bottom of the Demo page after the hand-over: a confirmation that this organizer is open in the workflow pages, and the sidebar now showing "Cu-Au CO2RR library, 9 samples, 17 modalities, all samples"](images/gui_handover.png)

**🔎 Explore & Filter** sets the selection. Filter on a number, a category, a
flag or a pandas expression. **Select these** makes the result the basket that
Visualize, Analyze and Compare act on. The table below has every parameter and
every derived column, including the fits from tab 5.

![The Explore & Filter page on the Cu–Au organizer: a filter builder on a numeric column, "9 of 9" matching samples, Select these and Use all samples buttons, and the start of the wide sample table](images/gui_explore.png)

**📈 Visualize** draws any measurement in the selection. Its tabs are grouped
by what the data is, not by instrument — *Curves (1D)*, *Images & Maps (2D)*,
*Volumes (3D)*, *Correlation* — and only the groups present appear. *Compare
samples* puts one curve per sample on a shared axis; *One sample in detail*
shows every frame of one sample. **Plot controls** gives colours, markers, log
axes, limits and figure size, and every figure can be static (matplotlib) or
interactive (Plotly).

![The Visualize page: Curves (1D) with DLS chosen, Compare samples mode, one intensity-weighted size distribution per sample on a log diameter axis — the main peak moving from about 22 to 32 nm with composition, and a small aggregate population near 200 nm](images/gui_visualize.png)

**🧪 Analyze** runs any registered analysis on one sample or the selection.
Its option form is generated from the analysis function's signature. A single
run writes nothing; a batch writes derived columns.

**📊 Compare** plots any derived column against any parameter. Colour it by a
category and the page warns when the spread between groups beats the spread
within one, which is a sign that the grouping and the x axis are confounded.

![The Compare page: X nominal_x_Au, Y uvvis_peak1_center, no colouring, and the eight alloys falling in a smooth line from 579 nm for pure copper to 519 nm for pure gold](images/gui_compare.png)

---

## 4. The same files from a notebook

The Demo page writes the same files notebooks 10–12 do, so the two take turns
on them:

```python
from NanoOrganizer import Organizer
from NanoOrganizer.demo import demo_root

org = Organizer(demo_root("CuAu", "cuau.json"))   # what the page built
org.describe()
org.results()                                     # the fits from tab 5
```

The reverse also works. Run notebooks 10 and 11, then **Reopen cuau.json** on
the Demo page, or open it from **📁 Project** by pasting the path to the
`.json` file. Its links, parameters, derived values and stored fits come back
intact.

| to learn | read |
|---|---|
| the pages in depth, and how to extend them | [`web_app.md`](web_app.md) |
| what is in the campaign on purpose | [`demo_data.md`](demo_data.md) |
| the data model behind the organizer | [`sample_model.md`](sample_model.md) |
| the analyses and the kernel/adapter rule | [`analysis.md`](analysis.md), [`kernel_adapter_rule.md`](kernel_adapter_rule.md) |
| the same walk in code | `notebook/10_simulate_data` → `11_build_organizer` → `12_use_organizer` |
