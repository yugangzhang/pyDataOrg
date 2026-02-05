# NanoOrganizer

A clean, modular, extensible framework for managing nanoparticle-synthesis data.
Organize metadata, link experimental datasets, load on demand, and visualize
everything — all from one unified Python interface.

---

## Package layout

```
NanoOrganizer/
├── core/               Metadata dataclasses, DataOrganizer, Run, file-link logic
│   ├── metadata.py     ChemicalSpec · ReactionParams · RunMetadata
│   ├── data_links.py   DataLink – lightweight file-reference container
│   ├── organizer.py    DataOrganizer – top-level run manager
│   ├── run.py          Run – single experiment + per-type loader accessors
│   └── utils.py        save_time_series_to_csv
├── loaders/            One loader class per data type (read files → std dict)
├── viz/                One plotter class per data type (std dict → matplotlib)
├── simulations/        Synthetic-data generators for demos & tests
└── web/                Streamlit read-only visualisation browser
    ├── cli.py          Console-script entry point (nanoorganizer-viz)
    └── app.py          Full Streamlit application
```

---

## Features

| Feature | Details |
|---|---|
| 9 data types | UV-Vis, SAXS 1D, WAXS 1D, DLS, XAS, SAXS 2D, WAXS 2D, SEM, TEM |
| Flexible metadata | Rich dataclasses: chemicals, reaction params, tags, notes, timestamps |
| Lazy loading | Files read only when `.load()` is called; metadata always instant |
| Any directory layout | Paths stored as absolute; no rigid folder convention required |
| Validation | One call checks every linked file still exists on disk |
| Per-type plotters | spectrum/profile/pattern, kinetics, heatmap, detector, azimuthal, image |
| Web browser | Interactive Streamlit app — cycle through runs and plot types in a browser |
| Extensible | Adding a new type is 8 well-documented steps; see `docs/adding_new_datatype.md` |

---

## Installation

```bash
# Core (numpy, scipy, matplotlib)
pip install NanoOrganizer

# With image support (Pillow)
pip install NanoOrganizer[image]

# With the web browser (streamlit)
pip install NanoOrganizer[web]

# Development / testing
pip install NanoOrganizer[dev]
```

For an editable install from the repo root:

```bash
pip install -e ".[web,image]"
```

---

## Quick start

```python
from NanoOrganizer import (
    DataOrganizer, RunMetadata, ReactionParams, ChemicalSpec,
    save_time_series_to_csv,
    simulate_uvvis_time_series_data,
)

# 1. Create an organizer (creates .metadata/ automatically)
org = DataOrganizer("./MyProject")

# 2. Describe the experiment
meta = RunMetadata(
    project="Project_Au",
    experiment="2024-10-25",
    run_id="Au_Test_001",
    sample_id="Sample_001",
    reaction=ReactionParams(
        chemicals=[ChemicalSpec(name="HAuCl4", concentration=0.5)],
        temperature_C=80.0,
    ),
    tags=["gold", "plasmon"],
    notes="First test run",
)
run = org.create_run(meta)

# 3. Simulate & link data
times, wls, abs_ = simulate_uvvis_time_series_data()
csv_files = save_time_series_to_csv(
    "./MyProject/uvvis", "uvvis",
    times, wls, abs_,
    x_name="wavelength", y_name="absorbance",
)
run.uvvis.link_data(csv_files, time_points=sorted(set(times)))

# 4. Persist metadata
org.save()

# 5. Later – reload from disk and plot
org  = DataOrganizer.load("./MyProject")
run  = org.get_run("Project_Au/2024-10-25/Au_Test_001")   # slash-joined key
data = run.uvvis.load()          # {'times', 'wavelengths', 'absorbance'}
run.uvvis.plot(plot_type="heatmap")
```

---

## Supported data types

| Type | Loader attr | CSV columns | Plot types |
|---|---|---|---|
| UV-Vis | `run.uvvis` | `wavelength`, `absorbance` | spectrum, kinetics, heatmap |
| SAXS 1D | `run.saxs` | `q`, `intensity` | profile, kinetics, heatmap |
| WAXS 1D | `run.waxs` | `two_theta`, `intensity` | pattern, kinetics, heatmap |
| DLS | `run.dls` | `diameter_nm`, `intensity` | size_dist, kinetics, heatmap |
| XAS | `run.xas` | `energy_eV`, `absorption` | xanes, kinetics, heatmap |
| SAXS 2D | `run.saxs2d` | `.npy` / `.png` / `.tif` | detector, azimuthal |
| WAXS 2D | `run.waxs2d` | `.npy` / `.png` / `.tif` | detector, azimuthal |
| SEM | `run.sem` | `.png` / `.tif` / `.jpg` | image |
| TEM | `run.tem` | `.png` / `.tif` / `.jpg` | image |

### 1-D time-series CSV convention

Each unique time point lives in its own CSV file.  The two-column header names
match the table above.  `save_time_series_to_csv` writes them automatically from
the long-format lists that every 1-D simulator returns.

### 2-D detector files (SAXS 2D / WAXS 2D)

Preferred format is NumPy `.npy` (float64, preserves full precision).  Loaders
also accept `.png` / `.tif` / `.tiff` via Pillow.  Pass detector-geometry
calibration when linking:

```python
run.saxs2d.link_data(
    npy_files,
    time_points=[0, 30, 60, 120],
    pixel_size_mm=0.172,
    sdd_mm=3000.0,
    wavelength_A=1.0,
)
```

The calibration values are stored in the link metadata and used automatically
by the azimuthal-average plotter to convert pixel radius → *q* (SAXS) or 2θ
(WAXS).

---

## Web app

Launch the interactive browser:

```bash
nanoorganizer-viz
```

The app auto-detects the bundled `Demo/` directory.  Use the sidebar to pick a
run, data type, and plot type; dynamic selector controls appear as needed.

Requires the `web` extra (`pip install NanoOrganizer[web]`).

---

## API reference

### Core

| Class / function | Purpose |
|---|---|
| `DataOrganizer(base_dir)` | Create or open a project directory |
| `DataOrganizer.load(base_dir)` | Reload an existing project from disk |
| `org.create_run(metadata)` | Register a new `Run` |
| `org.get_run("proj/exp/id")` | Retrieve a `Run` by slash-joined key |
| `org.list_runs()` | All run keys |
| `org.save()` | Persist all metadata as JSON |
| `org.validate_all()` | Check every linked file exists |
| `RunMetadata(...)` | Dataclass: project, experiment, run_id, sample_id, reaction, … |
| `ReactionParams(...)` | Dataclass: chemicals, temperature_C, … |
| `ChemicalSpec(...)` | Dataclass: name, concentration, concentration_unit, volume_uL |
| `save_time_series_to_csv(…)` | Write long-format data → one CSV per time point |

### Loaders (attached automatically to every `Run`)

| Attribute | Class | `load()` dict keys |
|---|---|---|
| `run.uvvis` | `UVVisLoader` | times, wavelengths, absorbance |
| `run.saxs` | `SAXSLoader` | times, q, intensity |
| `run.waxs` | `WAXSLoader` | times, two_theta, intensity |
| `run.dls` | `DLSLoader` | times, diameters, intensity |
| `run.xas` | `XASLoader` | times, energy, absorption |
| `run.saxs2d` | `SAXS2DLoader` | times, images, qx, qy, pixel_size_mm, sdd_mm, wavelength_A |
| `run.waxs2d` | `WAXS2DLoader` | times, images, qx, qy, pixel_size_mm, sdd_mm, wavelength_A |
| `run.sem` | `ImageLoader` | PIL Image (via `load(index=N)`) |
| `run.tem` | `ImageLoader` | PIL Image (via `load(index=N)`) |

Common loader methods: `link_data(files, …)`, `load()`, `plot(plot_type=…)`, `validate()`.

### Plotters

Each plotter is instantiated from `PLOTTER_REGISTRY[key]()` and exposes:

```python
plotter.plot(data_dict, plot_type="…", ax=ax, **kwargs)
```

`kwargs` accepted by individual plot types (e.g. `time_point`, `wavelength`,
`q_value`, `two_theta_value`, `energy`) are documented in the SELECTORS table
in `web/app.py` and in each plotter's docstring.

### Simulations

| Function | Returns |
|---|---|
| `simulate_uvvis_time_series_data(…)` | (times, wavelengths, absorbance) long-format |
| `simulate_saxs_time_series_data(…)` | (times, q, intensity) long-format |
| `simulate_waxs_time_series_data(…)` | (times, two_theta, intensity) long-format |
| `simulate_dls_time_series_data(…)` | (times, diameters, intensity) long-format |
| `simulate_xas_time_series_data(…)` | (times, energy, absorption) long-format |
| `simulate_saxs2d_time_series_data(…)` | (npy_paths, calibration_dict) |
| `simulate_waxs2d_time_series_data(…)` | (npy_paths, calibration_dict) |
| `create_fake_image_series(…)` | list of PNG paths |

---

## Tips & best practices

- **Slash-joined keys everywhere.** `get_run("Project/Experiment/RunID")` is the
  canonical way to look up a run after saving and reloading.
- **Validate early.** Call `org.validate_all()` after linking data to catch
  missing files before you need them.
- **Calibration in metadata.** For 2-D detectors, always pass `pixel_size_mm`,
  `sdd_mm`, and `wavelength_A` to `link_data()`.  They travel with the JSON and
  are used automatically during plotting.
- **Long-format ↔ CSV.** All 1-D simulators return long-format lists.  Feed them
  directly to `save_time_series_to_csv`; no reshaping needed.
- **Lazy loading.** `load()` is called only when you actually need the data.
  Switching between runs in the web app or in a notebook adds no I/O penalty.
- **Extending.** To add a new data type, follow the 8-step guide in
  [`docs/adding_new_datatype.md`](docs/adding_new_datatype.md).

---

## Demo

A pre-populated demo project lives in `Demo/`.  Load it in Python:

```python
org = DataOrganizer.load("./Demo")
run = org.get_run("Project_Cu2O/2024-10-25/Cu2O_Growth_Study_001")
run.uvvis.plot(plot_type="heatmap")
```

Or browse it in the web app:

```bash
nanoorganizer-viz
```

A full notebook that exercises every data type end-to-end is in
`example/full_demo.ipynb`.

---

## License

MIT
