# The generated example projects

Two projects ship as generators rather than as files. Nothing is committed,
nothing is downloaded, and either can be deleted freely.

```bash
python -m NanoOrganizer.demo --campaign     # the showcase as raw data → ../OrgDemo/CuAu
python -m NanoOrganizer.demo                # the showcase as a project → ../OrgDemo/Showcase
python -m NanoOrganizer.demo --quick        # the small one            → ../OrgDemo/Quick
python -m NanoOrganizer.demo ~/elsewhere/Showcase --no-images
```

Both refuse to overwrite a directory that does not carry their own marker
file, so pointing one at real data cannot destroy it.

**The showcase is the workflow's data.** Notebooks `10` → `11` → `12`, the web
app's **🎓 Demo** page and the README walkthrough all run on it, laid out like
this — one folder holding the campaign as its instruments left it, the answer
key, and the organizer built from it:

```
../OrgDemo/CuAu/   beside the repository (demo_root("CuAu"))
├── MetaData/ …    build_showcase_project() — the data and the four *_dict.py
├── truth.csv      showcase_truth(), the answer key
├── cuau.json      the organizer: four dicts ingested, four folders linked by hand
└── results/       stored fits, linked back onto their samples
```

Every path the generator writes into the metadata is **relative to the
folder**, and the organizer links relative too, so the folder moves as one
piece and nothing in it names a home directory. Rebuilding replaces the whole
folder — organizer and stored fits included.

`--campaign` writes the first two and stops, because building the organizer
is the lesson. Without it the same campaign goes to `Showcase/` and is opened
with folder conventions — what **Project → Generate an example one** does, and
what `notebook/legacy/05_multimodal_demo` tours.

| | `build_demo_project` | `build_showcase_project` |
|---|---|---|
| samples | 6 | 8 + 1 failed |
| techniques | UV-Vis, TEM | 15 |
| stages | 1 | 4 |
| groups | curve, image | all four |
| size on disk | ~1 MB | ~16 MB |
| build time | ~2 s | ~1 s |

## The showcase: a Cu–Au alloy library for CO₂ reduction

Everything in it is derived from **one hidden number per sample**, the gold
atomic fraction *x*. Fifteen techniques see fifteen different shadows of that
one number, which is the point: a framework is only worth having if
measurements from different instruments can be brought back together and shown
to agree.

### Why this material

Cu and Au are miscible at every composition, so a composition series is a real
material rather than a thought experiment, and the textbook consequences are
available at once:

* the lattice parameter follows **Vegard's law**, so a diffraction peak
  position measures composition;
* the particles keep **one** plasmon band moving from ~580 nm (Cu) to ~520 nm
  (Au) — the classic evidence that an alloy formed, rather than a mixture of
  two kinds of particle, which would show two fixed bands instead;
* gold segregates to the surface, so XPS and EDS disagree informatively;
* selectivity switches from hydrocarbons on Cu to CO on Au, and the CO
  *partial current* peaks in between — a Sabatier volcano, with the DFT CO
  binding energy as its descriptor.

### What each technique measures

| technique | group | what it sees | recoverable |
|---|---|---|---|
| UV-Vis | curve (series) | in-situ growth, plasmon band | band position → *x* |
| EDS | curve | Cu Kα and Au Lα lines | bulk *x* via Cliff–Lorimer |
| XPS | curve | Cu 2p with its Cu(II) satellite, Au 4f doublet | **surface** *x* |
| Raman | curve | Cu₂O phonons, carbon D and G, SERS gain | oxide content |
| IR (SEIRAS) | curve | adsorbed CO atop a metal site | C–O stretch → binding |
| XAS | curve | Cu K-edge, as-made and after reaction | oxidation state |
| SAXS | curve | sphere form factor | particle size |
| WAXS | curve | fcc 111/200/220/311/222 | lattice parameter → *x* |
| DLS | curve | intensity-weighted size distribution | hydrodynamic size |
| Electrochemistry | curve | HER and OER LSVs, CO₂RR LSV, FE per product | activity, selectivity |
| DFT | curve | surface-projected density of states | d-band centre |
| TEM | image | primary particles, dark on a light film | diameter |
| SEM | image | agglomerates, **bright** on a dark support | agglomerate size |
| 2D SAXS | image | the detector frame the 1D curve came from | — |
| XPCS | correlation | g₂ of the aggregates in a viscous medium | diffusion → size |

![Eight panels from the campaign: a UV-Vis growth series coloured by time, the WAXS (111) peak of all eight alloys walking left as gold is added, EDS spectra, Faradaic efficiency against potential, a TEM and an SEM micrograph on nanometre axes, a tomography slab projection, and XPCS correlation functions](images/campaign_gallery.png)

Eight of the fifteen, covering all four visualisation groups. The micrographs
are on nanometre axes drawn from each image's own calibration — the generator
writes it into the TIFF the way a microscope would, and `particle_sizing`
reads it back from there rather than being told.

### Things that are in it on purpose

**Two routes in.** Most measurements are declared in `MetaData/*.py`; TEM, SEM,
tomography and DLS arrive as `<Modality>Data/<SampleID>/` folders with no
record at all. The workflow links those four by hand, one `org.link` per
sample and technique; the project route picks them up by folder convention.

**A sparse matrix.** XAS is on four samples, tomography on two, XPCS and 2D
SAXS on three. Beamtime is finite, and `Project.availability()` exists to show
exactly this. The Cu K-edge is deliberately *not* on the pure-gold sample: a
technique that cannot apply is not the same as one that was skipped.

**A failed run.** `CuAu09` aborted, has `status == "error"` and no data. A demo
whose table is uniformly tidy teaches the wrong lesson.

**Techniques that disagree.** TEM measures primary particles, DLS the hydrated
object weighted by the sixth power of diameter, SEM the agglomerates. EDS
measures the bulk, XPS the surface. All five are right; the gaps between them
are the information.

![Four panels: gold fraction recovered from EDS and from WAXS on the parity line with XPS sitting above it; the fitted plasmon band against the generator's; TEM, DLS and SEM diameters an order of magnitude apart on a log axis; and the CO partial current against the DFT CO binding energy, peaking at CuAu05](images/campaign_compare.png)

The first two panels are the check that the project is self-consistent: two
instruments that never met land on the same composition, and one plasmon band
moves the way an alloy's does. XPS sitting above the parity line is the
segregation, and the three sizes span an order of magnitude. The right-hand
panel is what the whole project exists to produce: a Sabatier volcano whose
descriptor — the CO binding energy — came from a different stage of the
campaign than the current that it predicts.

**A measurement with no story.** Oxygen evolution was run on every sample and
the trend across the series is ~60 mV. It is in the project to be looked at and
set aside.

### Where the honest limits are

The physics is simplified. Line energies, lattice parameters and detector
resolution are real; self-absorption, instrument drift and matrix effects are
not there, and the Faradaic efficiencies sum to exactly 100. **The project
exists to check the pipeline, not to validate an analysis.**

Two residual biases are worth knowing because they are instructive rather than
accidental:

* The fitted d-band centre sits ~0.1 eV below the generator's value. That is
  the integration window, not noise — a d-band centre is only defined together
  with the window it was integrated over.
* The XAS edge position measured at half height is not the generator's edge
  parameter, because the white line contributes before half height. The
  *ranking* by oxidation state is recovered; the absolute position is a matter
  of definition.

### The answer key

```python
from NanoOrganizer.demo import showcase_truth
showcase_truth()
```

One row per sample with every quantity a technique in the project is supposed
to be able to recover. `NanoOrganizer/demo/materials.py` holds the model
itself, one documented function per property — change a number there and the
whole project follows.

## Layout on disk

```
CuAu/                (or Showcase/)
  MetaData/            Synthesis_dict.py, Characterization_dict.py,
                       Testing_dict.py, Computation_dict.py
  RawSpectra/          UV-Vis growth series, one .npy per frame + the axis
  Spectroscopy/<id>/   eds.dat, xps_Cu2p.dat, xps_Au4f.dat, raman.dat,
                       ir_seira.dat, xas_Cu_K_*.dat
  Scattering/<id>/     saxs_1d.dat, waxs_1d.dat, saxs2d_*.npy
  Dynamics/<id>/       xpcs_g2.dat
  Electrochemistry/<id>/  her_lsv.dat, oer_lsv.dat, co2rr_lsv.dat, FE_*.dat
  Computation/<id>/    pdos.dat
  TEMData/ SEMData/ TomoData/ DLSData/      picked up by folder convention
```

Curves are two-column text with a self-describing header, so they open in
anything. UV-Vis frames are single-column `.npy` on a shared axis file, which
is what exercises `FrameSeries` and the frame-name grammars.

## Modifying it

`build_showcase_project` takes `fractions`, `n_frames`, `n_micrographs`,
`image_size`, `tomo_size`, `seed`, `with_images`, `with_tomography` and
`include_failed_run`. The tomogram is the one large file, so it is the first
thing to turn down.

The figures on this page and in the README are rebuilt by

```bash
python scripts/make_readme_figures.py
```

which writes the campaign into a scratch folder and draws it with the README
walkthrough's own calls — the same organizer, loaders and plot functions a
notebook uses. Nothing in them is special-cased for the documentation, so a
figure that stops reproducing means the pipeline changed.

To change the science rather than the size, edit
`NanoOrganizer/demo/materials.py`: every property is one function of *x*, and
`showcase_truth` reads the same functions the generator does, so the answer key
cannot drift from the data.
