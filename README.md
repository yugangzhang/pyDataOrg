# NanoOrganizer

NanoOrganizer is a modular framework for organizing nanoparticle experiment data, linking files to metadata, and visualizing/analyzing datasets in Python and Streamlit.

## Highlights

- Core Python API for run metadata + linked experimental files
- 9 supported data modalities (1D, 2D, image)
- Integrated Streamlit web suite (`nanoorganizer`) with 8 pages
- Advanced CSV Plotter with fitting workflows:
  - General multi-peak fitting (Gaussian, Lorentzian, Pseudo-Voigt)
  - SAXS-physics fitting (sphere/cube/octahedron, mono/poly, optional Porod)
  - ML-assisted seed + optional refinement scaffold
- Single and batch fit export (ZIP, CSV, JSON, NPZ, HTML plot, PNG when available)
- Server-side fit artifact persistence under `results/fitting_exports`

## Installation

```bash
# Core package
pip install NanoOrganizer

# Common extras
pip install NanoOrganizer[web,image]

# Dev/testing
pip install NanoOrganizer[dev]
```

Editable install from repo root:

```bash
pip install -e ".[web,image]"
```

## Launch Web Apps

Recommended unified app:

```bash
nanoorganizer
```

Restricted mode (folder browser locked to current directory):

```bash
nanoorganizer_user
```

Notes:
- `nanoorganizer` uses Streamlit multi-page app at `NanoOrganizer/web_app/Home.py`
- CLI currently launches on port `5647`
- Running `streamlit run ...` manually uses Streamlit default port unless overridden

Legacy single-tool launchers are still available:
- `nanoorganizer-viz`
- `nanoorganizer-csv`
- `nanoorganizer-csv-enhanced`
- `nanoorganizer-manage`
- `nanoorganizer-3d`
- `nanoorganizer-img`
- `nanoorganizer-multi`
- `nanoorganizer-hub`

## Web Suite Pages (Integrated App)

From the sidebar in `nanoorganizer`:

1. `CSV Plotter`
2. `Image Viewer`
3. `Multi Axes`
4. `3D Plotter`
5. `Data Viewer`
6. `Data Manager`
7. `Test Data Generator`
8. `Universal Plotter`

## CSV Plotter Fitting Workflows

The CSV Plotter (`NanoOrganizer/web_app/pages/1_📊_CSV_Plotter.py`) now supports:

- Synthetic 1D curve generation (one/two/multi-peak)
- Peak picking by point selection + manual add/remove
- Single-fit and batch-fit workflows (collapsible sections)
- Fitting backends:
  - `General Peaks`
  - `SAXS Physics`
  - `ML-Assisted (Preview)` scaffold
- Export options:
  - Download ZIP per single or batch fit
  - Save fit results to server (`results/fitting_exports/...`)

Export bundles include:
- `fitted_curve.csv`
- `fit_parameters.csv`
- `fit_metrics.csv`
- `fit_peaks.csv` (when applicable)
- `fit_arrays.npz`
- `fit_summary.json`
- `fit_plot.html`
- `fit_plot.png` (if `kaleido` available)

## Optional External Integration

For fitting backends:

- `pyFitting` is required for optimization-based fitting
- `pySAXSFitting` is used for SAXS model fitting and dip-analysis seeds

If these packages are not installed, NanoOrganizer attempts fallback imports from sibling repos (common local development setup).

## Core Python Quick Start

```python
from NanoOrganizer import (
    DataOrganizer,
    RunMetadata,
    ReactionParams,
    ChemicalSpec,
    save_time_series_to_csv,
    simulate_uvvis_time_series_data,
)

# Create project organizer
org = DataOrganizer("./MyProject")

# Create one run
meta = RunMetadata(
    project="Project_Au",
    experiment="2024-10-25",
    run_id="Au_Test_001",
    sample_id="Sample_001",
    reaction=ReactionParams(
        chemicals=[ChemicalSpec(name="HAuCl4", concentration=0.5)],
        temperature_C=80.0,
    ),
)
run = org.create_run(meta)

# Link simulated UV-Vis data
times, wls, abs_ = simulate_uvvis_time_series_data()
csv_files = save_time_series_to_csv(
    "./MyProject/uvvis",
    "uvvis",
    times,
    wls,
    abs_,
    x_name="wavelength",
    y_name="absorbance",
)
run.uvvis.link_data(csv_files, time_points=sorted(set(times)))

org.save()

# Reload and plot
org2 = DataOrganizer.load("./MyProject")
r = org2.get_run("Project_Au/2024-10-25/Au_Test_001")
r.uvvis.plot(plot_type="heatmap")
```

## Supported Data Types

| Type | Loader attr | Typical x/y columns or file types |
|---|---|---|
| UV-Vis | `run.uvvis` | `wavelength`, `absorbance` |
| SAXS 1D | `run.saxs` | `q`, `intensity` |
| WAXS 1D | `run.waxs` | `two_theta`, `intensity` |
| DLS | `run.dls` | `diameter_nm`, `intensity` |
| XAS | `run.xas` | `energy_eV`, `absorption` |
| SAXS 2D | `run.saxs2d` | `.npy`, `.png`, `.tif`, `.tiff` |
| WAXS 2D | `run.waxs2d` | `.npy`, `.png`, `.tif`, `.tiff` |
| SEM | `run.sem` | image files |
| TEM | `run.tem` | image files |

## Repository Structure (Key Paths)

```text
NanoOrganizer/
├── NanoOrganizer/
│   ├── core/
│   ├── loaders/
│   ├── simulations/
│   ├── viz/
│   ├── web/                 # legacy individual Streamlit apps
│   └── web_app/             # integrated multi-page Streamlit app
│       ├── Home.py
│       ├── app_cli.py
│       ├── components/
│       └── pages/
├── docs/
├── Demo/
├── TestData/
└── setup.py
```

## Tips

- Use slash-joined run keys: `Project/Experiment/RunID`
- Call `org.validate_all()` after linking files
- For 2D detector data, include calibration (`pixel_size_mm`, `sdd_mm`, `wavelength_A`)
- For image export from Plotly in web app, install `kaleido`

## License

MIT
