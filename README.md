# NanoOrganizer

Organise experimental metadata, visualise any measurement, analyse in batch,
and compare across samples.

A laboratory accumulates data faster than it accumulates structure: a folder of
spectra here, a drive of micrographs there, a beamline mount, a potentiostat's
export folder, and the conditions that produced all of it in a notebook or a
script. NanoOrganizer gives that material one sample-centric model, so a
question like *which composition is the best CO₂-reduction catalyst, and why?*
is a filter, a batch and a plot rather than a week.

**The loop is the point: filter → analyse → new columns → filter again.**

![Eight panels from the Cu–Au campaign, all drawn by the package's own plot functions: a UV-Vis growth series coloured by time; the WAXS (111) peak of all eight alloys walking to lower q as gold is added; EDS spectra with the Cu and Au lines; the Faradaic efficiency of six CO₂-reduction products against potential; a TEM micrograph and an SEM micrograph on nanometre axes; a slab projection of a porous tomogram; and XPCS correlation functions](docs/images/campaign_gallery.png)

*Eight of the fifteen techniques in the walkthrough below — curves, images, a
volume and a correlation function — each drawn by one call into a figure the
reader made (step C).*

This page walks the whole loop on a generated campaign, in the order the three
workflow notebooks do — [`10_simulate_data`](notebook/10_simulate_data.ipynb)
→ [`11_build_organizer`](notebook/11_build_organizer.ipynb) →
[`12_use_organizer`](notebook/12_use_organizer.ipynb) — using only the
package's own functions, so every line below is something you would type on
your own data.

## Install

```bash
pip install -e ".[web,image]"
```

Dependencies are numpy, scipy, matplotlib and pandas; Pillow and scikit-image
for micrographs; Streamlit and Plotly for the GUI. Nothing else.

## Run the GUI

```bash
streamlit run NanoOrganizer/web_app/Home.py   # local, no login → http://localhost:8501
viz                                           # password + folder fence, port 8800
viz 8900                                      # the same, on another port
```

`streamlit run` is the plain local app. `viz` is the console command the
package installs: it asks for an access password, binds to every interface so
colleagues can reach it by hostname, and only lets the file pickers see the
folder you started it in, your home directory, and any extra roots you
configure — the mode for a shared machine.

**First thing to click: 🎓 Demo.** Six tabs — *Simulate, Build, Look,
Visualize, Analyze, Compare* — run the walkthrough below on the same Cu–Au
campaign with buttons, and show the Python each button runs. When it is built,
the organizer opens in the workflow pages (**Project → Structure → Explore &
Filter → Visualize → Analyze → Compare**), which drive the very same object a
notebook does, so the two cannot drift apart.
[`docs/gui_demo.md`](docs/gui_demo.md) is the guided tour, with screenshots;
[`docs/web_app.md`](docs/web_app.md) describes every page.

---

## Walkthrough: fifteen techniques, one hidden number

### The campaign

A library of **Cu–Au alloy nanocatalysts for CO₂ electroreduction**, made and
measured the way a real campaign is: eight compositions plus one synthesis that
failed, **fifteen techniques across four stages** (synthesis,
characterization, testing, computation), and a measurement matrix with holes
in it because beamtime is finite.

Everything in it follows from **one hidden number per sample — the gold
fraction *x***. Cu and Au mix at every composition, so the textbook
consequences all arrive together, each seen by a different instrument:

| what *x* does | who sees it |
|---|---|
| the lattice swells (Vegard's law) | **WAXS** — the (111) peak walks to lower *q* |
| one plasmon band moves 580 → 520 nm — an *alloy*, not a mixture, which would show two fixed bands | **UV-Vis** |
| gold segregates to the surface | **XPS** (surface) reads more gold than **EDS** (bulk) |
| particles grow with *x* | **TEM** (primaries), **DLS** (hydrated, intensity-weighted), **SEM** (agglomerates) — three sizes, all right |
| the d-band shifts, so CO binds differently | **DFT**, and the C–O stretch in **IR** |
| selectivity switches from hydrocarbons to CO | **electrochemistry** — and the CO current is a **Sabatier volcano** |

Raman, XAS, SAXS (1D and 2D), XPCS and tomography fill in the rest. Because the
generator knows *x*, the answer key comes with the data — the one thing real
data never lets you check.

### 0 · Get the data

```bash
python -m NanoOrganizer.demo --campaign     # writes ../OrgDemo/CuAu, beside this repository
```

(or run notebook `10_simulate_data`, or **Demo → 1 Simulate** in the GUI —
all three call the same generator.) Generated data goes under one parent,
`../OrgDemo` beside the repository by default; set `$NANOORGANIZER_DEMO_ROOT`
to move it.

What lands on disk is a campaign as the groups that ran it left it — one tree
per kind of instrument, none of them agreeing on a layout:

```
📁 CuAu  11 folders · 2 files · .csv 1, .txt 1 · 1 hidden
├── 📁 Computation  8 folders            DFT projected density of states
├── 📁 DLSData  8 folders                ← no record
├── 📁 Dynamics  3 folders               XPCS — three samples got beamtime
├── 📁 Electrochemistry  8 folders       LSVs, one Faradaic-efficiency file per product
├── 📁 MetaData  4 files · .py 4         what the operators wrote down
├── 📁 RawSpectra  1 folder              UV-Vis growth series, one file per frame
├── 📁 Scattering  8 folders             SAXS, WAXS, 2D detector frames
├── 📁 SEMData  8 folders                ← no record
├── 📁 Spectroscopy  8 folders           EDS, XPS, Raman, IR, XAS
├── 📁 TEMData  8 folders                ← no record
├── 📁 TomoData  2 folders               ← no record
├── 📄 README.txt  1.2 KB
└── 📄 truth.csv                         the answer key
```

*(The listing is `structure.tree(ROOT, depth=1)` — the same walk works on
any folder, JSON record, HDF5 group or `.npz`, reading shapes from headers
rather than loading data.)*

`MetaData/` holds **four dicts, one per stage**, keyed by sample id — the
synthesis conditions, and for every other stage the blocks that name the files
each technique wrote. Four techniques never made it into them: the TEM, SEM,
DLS and tomography folders were dropped on the share by whoever ran the
instrument that week. That is the normal state of affairs, and it is why the
next step links them by hand. `truth.csv` is the answer key.

Every path the metadata records is **relative to this folder**, and the
organizer the next step builds sits inside it — so the folder moves as one
piece. Copy it, zip it, open it on another machine: nothing names anyone's
home directory, and nothing needs reconfiguring.

### 1 · Build the organizer — notebook 11

An **organizer is one JSON file you name**. Not a directory layout and not a
hidden folder — a document you can copy, diff, version and email. It records
*where* things are; the data never moves.

```python
from NanoOrganizer import Organizer
from NanoOrganizer.demo import demo_root

ROOT = demo_root("CuAu")                     # ../OrgDemo/CuAu, beside this repository

org = Organizer(ROOT / "cuau.json", name="Cu-Au CO2RR library")   # empty if the file is new
for stage in ("Synthesis", "Characterization", "Testing", "Computation"):
    org.ingest(f"MetaData/{stage}_dict.py")  # relative to cuau.json; the stage is named by the dict
print(org.summary())                         # 9 samples, 118 measurements
```

`ingest` reads what somebody already wrote down. Any block of a record that
names files becomes a measurement; everything else is kept as a parameter and
flattens into a dotted, filterable column —
`synthesis.composition.nominal_x_Au`, `testing.performance.FE_CO_pct`,
`computation.descriptors.E_ads_CO_eV`.

`ingest` also takes **the dict itself**, which is what a notebook actually
has. Edit it and ingest again; `replace=True` makes it the whole truth for its
stage, so a popped key is really gone rather than lingering as a merge
artefact:

```python
import runpy

Synthesis_dict = runpy.run_path(str(ROOT / "MetaData" / "Synthesis_dict.py"))["Synthesis_dict"]
Synthesis_dict["CuAu04"]["conditions"]["hold_time_min"] = 75.0   # a transcription error, found later
org.ingest(synthesis=Synthesis_dict, replace=True)               # the keyword names the stage
```

Then **link what nobody wrote down** — one call per measurement, by hand,
because that is the only thing that is true:

```python
BY_HAND = {"tem": "TEMData", "sem": "SEMData", "dls": "DLSData", "tomo": "TomoData"}

for sample in org.ids():
    for modality, folder in BY_HAND.items():
        if (ROOT / folder / sample).is_dir():    # CuAu09 failed; tomography is on two samples
            extra = {"voxel_size_nm": 2.0} if modality == "tomo" else {}   # the reconstruction's voxel
            org.link(sample, modality, f"{folder}/{sample}",               # relative, like the dicts
                     stage="characterization", **extra)
```

`link` reads its third argument three ways:

| | |
|---|---|
| a **folder** | listed now, filtered by the technique's extensions — a snapshot you can audit (`note.txt` beside the TIFFs is left out without being asked) |
| a **glob** | kept live, re-expanded on every read, so frames written later appear |
| a **path or list** | stored verbatim |

Anything else you pass is kept with the link — the tomogram's voxel size here,
which step C reads back. A **relative** path is relative to the organizer's
folder, which is what lets this one travel with its data. Data that lives
somewhere else entirely is linked by its absolute path, recorded exactly as
given; each such link registers the **mount** it sits on as an alias, so moving
to another machine is one line per mount, not one edit per record.

```python
org.catalog()               # the sample × technique matrix: 9 × 16, 144 measurements
org.save()                  # one file: links, parameters, aliases
org.links_table().head()    # every link as a table; link_table(csv) reads it back
```

The catalog's gaps are the point. CuAu09 is an empty row — the synthesis
aborted, and it stays in the table because a filter that silently dropped it
would hide that it exists. XAS is on four samples, 2D SAXS and XPCS on three,
tomography on two; seeing which comparisons exist beats finding out halfway
through an argument. `links_table()` round-trips through `link_table()`
unchanged, because a spreadsheet is a better editor than a form when forty rows
need the same fix.

`attach_folders()` also exists, for data genuinely laid out as
`<Modality>Data/<SampleID>/` under one root — which the four bare folders here
happen to be. It is the exception, not the route this page leads with, because
almost no campaign is shaped that way.

### 2 · Use it — notebook 12

Six parts, in the order a session actually goes. The through-line is that
**nothing is a dead end**: you always get the arrays, so the moment an analysis
stops fitting what a convenience call assumed, you carry on with your own code.

**A · Look at it.** Reopening is the same call, and everything is back.

```python
org = Organizer(ROOT / "cuau.json")
org.describe()                               # samples, stages, techniques by group, what is readable here
print(org.tree(depth=2, limit=5))            # the file's structure — of the live session, not the last save

org.ids("`synthesis.composition.nominal_x_Au` >= 0.5")       # a question, without committing to it
gold_rich = org.subset(query="`synthesis.composition.nominal_x_Au` >= 0.5 "
                             "and `synthesis.status` == 'done'", name="gold-rich")
```

The first question returns the failed CuAu09 too — its recipe said 0.5 — which
is exactly why the subset asks for `status == 'done'` as well. A subset is a
**deep copy**, not a view, so analysing it cannot write derived values back
into the parent by accident; nothing is written until you `save()` it.
`org.filter(...)` instead makes the selection current for every later call
(`org.clear()` drops it).

**B · Load data** — all of it, or one frame at a time.

```python
x, Y, info = org.data("CuAu05", "uvvis")             # 14 frames × 551 points; info["t_s"] from the filenames
_, Y80, hot = org.data("CuAu05", "uvvis", T=80)      # the frame nearest 80 °C — the names carry both
org.frames("CuAu05", "uvvis").head()                 # one row per file: what each name admitted (t_s, T_c)

frames = org.data("CuAu05", "tem", lazy=True)        # 3 files resolved, nothing read
image, meta = frames[0]                              # one file opened; meta["nm_per_pixel"] from the TIFF
planes = org.data("CuAu01", "tomo", lazy=True)       # 128 planes of one memory-mapped .npy
plane, _ = planes[64]                                # one plane read, not the whole tomogram
q, W, _ = org.data("CuAu05", "waxs1d")
```

What comes back follows what the data *is*: a curve is `(x, Y, info)`, an
image `(array, info)`, a volume `(volume, info)`. `lazy=True` is the
difference between looking at the third of four hundred micrographs and
reading twelve gigabytes to do it.

**C · Visualise** — the arrays from B, into a figure you made. Every plot
function takes `ax=`, draws there, and returns what it drew on. This is the
gallery at the top of the page:

```python
import matplotlib.pyplot as plt
from NanoOrganizer.viz.plots import plot_curves, plot_image, plot_series
from NanoOrganizer.viz.show import project_volume

done = org.ids("`synthesis.status` == 'done'")
x_nominal = org.table(sample_ids=done)["synthesis.composition.nominal_x_Au"]

x, Y, info = org.data("CuAu05", "uvvis")
q = org.data("CuAu01", "waxs1d")[0]                 # one q grid for all
waxs = [org.data(s, "waxs1d")[1][0] for s in done]

eds, g2 = [], []
for s in ("CuAu01", "CuAu05", "CuAu08"):
    energy, counts, _ = org.data(s, "eds")
    eds.append((s, energy, counts[0]))
for s in ("CuAu01", "CuAu04", "CuAu08"):            # XPCS got three samples
    tau, G, _ = org.data(s, "xpcs_g2")
    g2.append((s, tau, G[0]))

potential, FE, fe = org.data("CuAu06", "ec", role="co2-rr-fe")
products = [(name[3:-4], potential, row)
            for name, row in zip(fe["labels"], FE)]

tem, tem_info = org.data("CuAu05", "tem", frame=0)
sem, sem_info = org.data("CuAu05", "sem", frame=0)
volume, _ = org.data("CuAu01", "tomo")
voxel = org.measurement("CuAu01", modality="tomo").meta["voxel_size_nm"]
slab, detail = project_volume(volume, projection="max projection", slab=16)

tem_nm = tem.shape[0] * tem_info["nm_per_pixel"]    # square frames
sem_nm = sem.shape[0] * sem_info["nm_per_pixel"]
slab_nm = slab.shape[0] * voxel

fig, axes = plt.subplots(2, 4, figsize=(21, 9))
plot_series(x, Y, info["t_s"], ax=axes[0, 0], xlabel="wavelength (nm)",
            ylabel="absorbance", colorbar_label="time (s)",
            title="UV-Vis · CuAu05 growth, coloured by time")
plot_series(q, waxs, x_nominal.values, ax=axes[0, 1], xlim=(2.5, 3.25),
            xlabel="q (Å⁻¹)", ylabel="intensity", colorbar_label="x(Au)",
            title="WAXS (111) · walks left as gold enters")
plot_curves(eds, ax=axes[0, 2], logy=True, xlim=(0.5, 11.0),
            xlabel="energy (keV)", ylabel="counts",
            title="EDS · Cu Kα 8.05, Au Lα 9.71 keV")
plot_curves(products, ax=axes[0, 3], marker="o", markersize=5,
            xlabel="potential (V vs RHE)",
            ylabel="Faradaic efficiency (%)",
            title="CO₂RR · CuAu06, where the charge goes")
plot_image(tem, ax=axes[1, 0], cmap="gray", colorbar=False,
           extent=(0, tem_nm, tem_nm, 0), xlabel="nm", ylabel="nm",
           title="TEM · primary particles, dark on film")
plot_image(sem, ax=axes[1, 1], cmap="gray", colorbar=False,
           extent=(0, sem_nm, sem_nm, 0), xlabel="nm", ylabel="nm",
           title="SEM · agglomerates, bright on support")
plot_image(slab, ax=axes[1, 2], cmap="magma", colorbar=False,
           extent=(0, slab_nm, slab_nm, 0), xlabel="nm", ylabel="nm",
           title=f"Tomography · CuAu01, {detail}")
plot_curves(g2, ax=axes[1, 3], logx=True, marker="o", markersize=4,
            xlabel="lag τ (s)", ylabel="g₂(τ)",
            title="XPCS · decay rate → aggregate size")
fig.tight_layout()
```

A series ordered by something continuous — time, composition — is coloured
along **one hue**, with a colour bar instead of a legend of fourteen
timestamps; categories get distinct hues. The micrographs are on nanometre
axes because each TIFF carried its calibration, and the tomogram because its
voxel size was recorded when it was linked. A slab projection is what anyone
actually looks at: a single plane through a packed aggregate is mostly gaps.

A projection says what is in there; only rotation says what shape it is. The
same volume, as something you can turn around:

```python
from NanoOrganizer.viz import interactive as iv

tomo = iv.volume_figure(volume, mode="volume", level=130, voxel_size=voxel, unit="nm")
# tomo.show()   — drag to rotate; mode="isosurface", "points" or "slices" for the other views
```

![A rotatable rendering of the CuAu01 tomogram: a roughly spherical aggregate about 150 nm across, its interior threaded with pores, on calibrated nanometre axes](docs/images/demo_tomogram.png)

`level` is a control rather than a constant, because that one number decides
what the structure appears to be. Large volumes are strided down before
rendering and the title says by how much — a browser does not degrade
gracefully on a 128³ translucent volume, it locks the tab.

**D · Fit one, look at it, *then* batch.** The fit is a function of two arrays
— no files, no project — and so is the composition it implies. Looking at
either is a second, separate call:

```python
from NanoOrganizer.analysis import fit_peaks, segment_micrograph
from NanoOrganizer.demo import materials as mat
from NanoOrganizer.viz.plots import plot_fit, plot_segmentation

fit = fit_peaks(q, W[0], n_peaks=2, x_range=(2.5, 3.6),
                shape="pseudo_voigt", background="linear")
fit                                                    # <PeakFitResult 2 peak(s) at [2.812, 3.247], R² = 0.9999>
lattice = mat.lattice_from_q(fit.params["peak1_center"])    # (111): a = 2π√3 / q = 3.870 Å
x_au = mat.fraction_from_lattice(lattice)              # Vegard backwards → 0.550; the generator used 0.55

seg = segment_micrograph(org.measurement("CuAu05", modality="tem"), org.resolver)

fig, axes = plt.subplots(1, 2, figsize=(14, 5.6), gridspec_kw={"width_ratios": [1.35, 1]})
plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, ax=axes[0], xlabel="q (Å⁻¹)",
         ylabel="intensity", title=f"CuAu05 · R² = {fit.r2:.4f} → x(Au) = {x_au:.3f}")
plot_segmentation(seg, ax=axes[1])                     # always look before trusting a size table
```

![Left: the CuAu05 WAXS pattern between 2.5 and 3.6 per ångström with the (111) and (200) peaks fitted as pseudo-Voigts on a linear background, R² 0.9999, and the residual panel split off beneath; right: the CuAu05 TEM micrograph with 58 particles outlined in red](docs/images/campaign_fit.png)

The residual panel is where a bad fit shows: a fitted line over data is
persuasive whatever it does, and residuals that stop being noise and start
having shape are the thing to look at. Even this one has a little shape under
each peak — a pseudo-Voigt is not exactly the generator's line profile — but at
under 1 % of the peak it moves the centre by nothing. Fit one peak across both
reflections instead and the centre still lands, R² still reads 0.82, and the
residual is nearly as tall as the (200) peak: the residual is the tell, not the
headline number. The outlines are the same check for sizing — over-splitting
and film texture both produce a plausible histogram.
Settling the parameters on one sample you can *see*, and only then spending
them on the whole set, is the same work as batching first and reading the R²
column afterwards — in the order that does not hide the mistake:

```python
org.batch("peak_fit", modality="waxs1d", link=True, x_range=(2.5, 3.6),
          n_peaks=2, shape="pseudo_voigt", background="linear")
org.batch("peak_fit", modality="uvvis", link=True, x_range=(470.0, 800.0),
          reduce="last_decile", background="linear")      # the end of the growth series
org.batch("curve_metrics", modality="eds", prefix="eds_cu_", x_min=7.7, x_max=8.4)
org.batch("curve_metrics", modality="eds", prefix="eds_au_", x_min=9.4, x_max=10.0)
org.batch("curve_metrics", modality="xps", role="cu2p", prefix="xps_cu_", x_min=929, x_max=937)
org.batch("curve_metrics", modality="xps", role="au4f", prefix="xps_au_", x_min=81.5, x_max=86.0)
org.batch("particle_sizing", modality="tem")
org.batch("particle_sizing", modality="sem", max_diameter_nm=500, min_circularity=0.5)
org.batch("curve_metrics", modality="dls", x_min=5, x_max=120)
org.results()[["sample_id", "modality", "ok", "fit_r2"]]
org.save()
```

Each batch writes its scalars back as columns beside the authored parameters —
`derived.waxs1d_peak1_center`, `derived.tem_d_mean`, `derived.eds_au_area` —
and reports its failures rather than skipping them. Every line is a decision
worth reading: `prefix=` keeps two windows on one spectrum in two columns;
`background="linear"` because an EDS line sits on bremsstrahlung and a plasmon
on an interband edge, and a flat background through a slope drags the centre
up it; `reduce="last_decile"` fits the *product* rather than a particle that
had not finished growing. `link=True` also writes the fitted *curves* beside
the organizer and links them onto their sample, which is what part F reads
back.

**E · Compare: ids → table → plot.** Each step is a thing you can look at:

```python
import pandas as pd
from NanoOrganizer.demo.signals import EDS_K_FACTOR_AU_CU, XPS_RSF
from NanoOrganizer.viz.plots import plot_compare

table = org.table(sample_ids=org.ids("`synthesis.status` == 'done'"))
truth = pd.read_csv(ROOT / "truth.csv").set_index("sample_id")   # the answer key

check = pd.DataFrame({
    "x_true": truth["x_Au"],
    "EDS (bulk)": mat.fraction_from_signals(
        table["derived.eds_au_area"], table["derived.eds_cu_area"],
        gold_factor=EDS_K_FACTOR_AU_CU),                        # Cliff–Lorimer
    "WAXS (Vegard)": mat.fraction_from_lattice(
        mat.lattice_from_q(table["derived.waxs1d_peak1_center"])),
    "XPS (surface)": mat.fraction_from_signals(
        table["derived.xps_au_area"], table["derived.xps_cu_area"],
        gold_factor=XPS_RSF["Au 4f7/2"], copper_factor=XPS_RSF["Cu 2p3/2"]),
    "band_true_nm": truth["true_lspr_nm"],
    "band_fitted_nm": table["derived.uvvis_peak1_center"],
    "TEM": table["derived.tem_d_mean"],
    "DLS": table["derived.dls_x_at_max"],
    "SEM": table["derived.sem_d_mean"],
}).reset_index()

composition = check.melt(id_vars=["sample_id", "x_true"], var_name="technique",
                         value_vars=["EDS (bulk)", "WAXS (Vegard)", "XPS (surface)"],
                         value_name="x_measured")
sizes = check.melt(id_vars=["sample_id", "x_true"], var_name="technique",
                   value_vars=["TEM", "DLS", "SEM"], value_name="diameter_nm")

fig, axes = plt.subplots(1, 4, figsize=(22, 5))
plot_compare(composition, "x_true", "x_measured", color_by="technique",
             label_points=False, ax=axes[0],
             xlabel="x(Au) the generator used", ylabel="x(Au) measured",
             title="Composition three ways — XPS sits above: Au segregates")
axes[0].axline((0, 0), slope=1, linestyle="--", color="0.6")
plot_compare(check, "band_true_nm", "band_fitted_nm", ax=axes[1],
             xlabel="band the generator used (nm)", ylabel="fitted band (nm)",
             title="One plasmon band that moves — an alloy")
axes[1].axline((550, 550), slope=1, linestyle="--", color="0.6")
plot_compare(sizes, "x_true", "diameter_nm", color_by="technique",
             label_points=False, logy=True, ax=axes[2],
             xlabel="x(Au)", ylabel="diameter (nm)",
             title="Three sizes, all of them right")
plot_compare(org.table(), "computation.descriptors.E_ads_CO_eV",
             "testing.performance.j_CO_mA_cm2", ax=axes[3],
             xlabel="ΔE(CO) from DFT (eV)", ylabel="CO partial current (mA cm⁻²)",
             title="Sabatier volcano, straight off the table")
fig.tight_layout()
```

![Four panels: gold fraction recovered from EDS and from WAXS on the parity line with XPS sitting above it; the fitted plasmon band against the generator's on a parity line, 580 to 520 nm; TEM, DLS and SEM diameters an order of magnitude apart on a log axis; and the CO partial current against the DFT CO binding energy, rising to a peak at CuAu05 and falling again](docs/images/campaign_compare.png)

Instruments that never met recover the same hidden number: **EDS** lands
within 0.021 of the generator's composition and **WAXS**, through Vegard's law,
within 0.001; the plasmon band is within **0.95 nm**. Two disagreements are
the information rather than error. **XPS** reads more gold than the bulk
because gold segregates to the surface — it tracks the generator's surface
composition to within 0.05. The **three sizes** span an order of magnitude and
all are right: TEM resolves primary particles, DLS the hydrated object weighted
by the sixth power of diameter, SEM at this magnification only the
agglomerates. And the last panel is why anyone builds a composition series:
DFT's CO binding energy, from a different stage of the campaign, predicts the
CO partial current — too weak and CO leaves before anything happens to it, too
strong and it never leaves — peaking at **CuAu05**, *x* = 0.55.

**F · Reopen, and go round again.** Nothing is refitted: the stored curves come
off disk.

```python
from NanoOrganizer.viz.plots import plot_peak_fit

later = Organizer(ROOT / "cuau.json")
later.results()                                              # what has been analysed, and how
result = later.result("CuAu05", "peak_fit", modality="waxs1d")   # read back, not recomputed

fig, ax = plt.subplots(figsize=(7, 5))
plot_peak_fit(result, ax=ax)                                 # the fit over its data, residuals beneath
```

A fit is a measurement of a measurement, so it needs no second mechanism: it
sits on its sample as modality `fit`, shows in `catalog()`, and survives the
organizer being reopened months later on another machine. `modality=` picks
between two fits of one sample — the plasmon band and the diffraction peak are
two results, not one.

> Every step above also has a one-call shortcut on the organizer — draw a
> measurement by sample and technique, overlay a technique across samples,
> fit one sample, segment one frame, redraw a stored fit. Notebook 12 shows
> them; this page uses the calls underneath, because those are the ones you
> keep when an analysis stops fitting what a shortcut assumed.

**It scales.** Keying on `sample_id` is not a small-campaign idea: **10 000
samples** ingest in 0.15 s, save in 0.9 s (13 MB), load in 0.4 s and filter in
0.1 s on an ordinary laptop. A plate-based campaign uses the same calls as this
nine-sample one.

---

## Analysis and plotting are separate calls

Two rules hold for every function in the package, and they are what made the
walkthrough above possible:

1. **Kernel and adapter.** Every analysis and every plot is written twice: a
   *kernel* that takes plain arrays (`fit_peaks(x, y)`, `plot_fit(x, y,
   y_fit)`) and a thin *adapter* that finds the data, calls the kernel and
   files the answer (`peak_fit(measurement, resolver)`, `plot_peak_fit(result)`).
   The numerical half is always callable on two arrays you made up.
2. **A plot draws; it never analyses.** Every plot function takes `ax=None`,
   draws only there when given one, and returns what it drew on — so it drops
   into anyone's grid. No function both computes a result and draws it: the
   analysis returns a result, the plot is handed it.

The interactive (Plotly) figures follow the same rule with `fig=` — draw into
an existing figure, at a cell of a subplot grid, and get it back:

```python
from plotly.subplots import make_subplots

grid = make_subplots(rows=1, cols=2,
                     subplot_titles=("CuAu06 · Faradaic efficiency", "CuAu05 · TEM"))
iv.curves_figure(products, fig=grid, row=1, col=1, marker="circle",
                 xlabel="potential (V vs RHE)", ylabel="FE (%)")
iv.image_figure(tem, fig=grid, row=1, col=2, colorscale="Greys_r")
# grid.show() — hover for the exact number, zoom into a particle
```

[`docs/kernel_adapter_rule.md`](docs/kernel_adapter_rule.md) states both rules
in full, with a reviewer checklist, and is written to be copied into another
project as-is.

## The model

```
Organizer / Project        one document (or folder): samples, path aliases, the store
 └── Sample(sample_id)     the thing that persists
      ├── stages           one execution each — synthesis, characterization, testing, computation — with its parameters
      ├── measurements     one body of data each, referenced not loaded
      └── derived          computed values — filterable beside the authored ones
```

A sample is the unit, not a run: one sample is made once, used several times,
and characterised for weeks by different instruments. Keying on the sample
survives re-measurement; keying on a run scatters it. Paths are stored
**exactly as the instrument recorded them** and mapped per machine, so a
project whose data is not currently mounted still browses — it reports as
unreadable rather than breaking.

## Technique is metadata, not a code path

Every call above took the technique as an argument. Reading and drawing
dispatch on what the data *is*:

| group | shapes | techniques shipped |
|---|---|---|
| Curves (1D) | curve, series | UV-Vis, Raman, IR, XPS, XAS, EDS, SAXS/WAXS 1D, XRD, DLS, electrochemistry, DFT DOS |
| Images & Maps (2D) | image, map | TEM, SEM, optical, cell, SAXS/WAXS 2D, GIWAXS |
| Volumes (3D) | volume, stack | tomography, z-stack |
| Correlation | corr, twotime | XPCS g₂, two-time |

Adding a technique is one registry entry and changes no page and no function:

```python
from NanoOrganizer.core.modality import Modality, register

register(Modality(key="pl", label="Photoluminescence", domain="wavelength",
                  shape="series", x_label="Wavelength (nm)",
                  y_label="Intensity (a.u.)", extensions=(".txt", ".csv"),
                  analyses=("peak_fit",), category="spectroscopy"))
```

## Analyses

Three technique-neutral analyses ship with the package, each a kernel you can
call on arrays and an adapter `batch` runs:

| analysis | kernel | what it does |
|---|---|---|
| `peak_fit` | `fit_peaks(x, y)` | one or more peaks plus a constant or linear background, on any 1D curve |
| `curve_metrics` | `measure_curve(x, y)` | height, position, area, centroid and threshold crossing in a window — no model fitted |
| `particle_sizing` | `size_from_image(image, nm_per_pixel)` | micrographs: Otsu plus watershed, calibrated to nm from the image's own metadata |

`curve_metrics`' threshold crossing is the same operation as *the potential at
10 mA cm⁻²*, *the onset of an absorption edge* and *the lag time at which a
correlation function has half decayed* — writing it once is the argument for a
modality registry in miniature. Above it measured line areas on EDS and XPS
and the peak of a DLS distribution with no change. Results carry their own
provenance: a fit window, an R² and a point count are part of a measurement,
not decoration.

Chemistry-specific analyses belong in a package of their own and register
themselves on import — the same adapter shape, under a new key:

```python
from NanoOrganizer.analysis import Analysis, register_analysis
from NanoOrganizer.analysis.curves import curve_metrics

register_analysis(Analysis(key="pl_band", func=curve_metrics,
                           label="PL band metrics", modalities=("pl",)))
```

| to add | do |
|---|---|
| a technique | `register()` a `Modality` |
| an analysis | `register_analysis()` an `Analysis` |
| a metadata format | `register_adapter()` an `Adapter` |
| a filename convention | `register_grammar()` a `FrameGrammar` |

## Other generated data

```bash
python -m NanoOrganizer.demo            # the same campaign as a ready project → ../OrgDemo/Showcase
python -m NanoOrganizer.demo --quick    # a small two-technique project       → ../OrgDemo/Quick
```

The first opens the campaign with folder conventions instead of building an
organizer by hand — what **Project → Generate an example one** in the GUI
does, and what `notebook/legacy/05_multimodal_demo` tours. The second is the
small project `notebook/legacy/00_quickstart` → `04_compare` walk.
[`docs/demo_data.md`](docs/demo_data.md) records what is in the campaign on
purpose — including the failed run, the sparse matrix, and the one technique
with no story to tell.

## Documentation

| | |
|---|---|
| [`notebook/README.md`](notebook/README.md) | which notebook to read, in what order |
| [`docs/gui_demo.md`](docs/gui_demo.md) | the GUI, step by step, on the Cu–Au campaign |
| [`docs/web_app.md`](docs/web_app.md) | every page of the GUI, and how to extend it |
| [`docs/sample_model.md`](docs/sample_model.md) | the data model, path aliases, ingest, linking, stored results |
| [`docs/analysis.md`](docs/analysis.md) | analyses, the registry, and decisions that affect the numbers |
| [`docs/kernel_adapter_rule.md`](docs/kernel_adapter_rule.md) | the kernel/adapter and plotting rules every function follows |
| [`docs/demo_data.md`](docs/demo_data.md) | the generated campaign, its physics, and what is in it on purpose |
| [`CLAUDE.md`](CLAUDE.md) | the house rules for anyone — person or coding assistant — changing the code |
| [`docs/archive/`](docs/archive/) | notes from earlier versions, kept for reference |

## Tests

```bash
pytest
```

The suite includes the kernels on synthetic data with known answers, and the
Streamlit pages driven through `AppTest` against generated projects — including
the fifteen-technique campaign that exercises all four visualisation groups at
once. No test needs a data mount.

The figures on this page are part of that: `python
scripts/make_readme_figures.py` rebuilds every one of them with the
walkthrough's own calls, in a scratch folder, so a figure that stops
reproducing means the pipeline changed.

## License

MIT — see [LICENSE](LICENSE).
