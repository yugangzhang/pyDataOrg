# NanoOrganizer: Metadata & Data Management for Nanoparticle Synthesis

A clean, modular, and robust system for managing experimental metadata and time-series data from high-throughput reactor synthesis.

## 🎯 Key Features

✅ **Flexible Metadata Management** - JSON-based, human-readable, version-control friendly  
✅ **Lazy Data Loading** - Load metadata instantly, load data only when needed  
✅ **Any Directory Structure** - You organize files your way, we just link to them  
✅ **Built-in Validation** - Automatically check if all data files exist  
✅ **Easy Visualization** - Simple plotting interface for all data types  
✅ **Extensible Design** - Easy to add new data types or analysis methods  

---

## 📁 What You Get

```

NanoOrganizer/                     [Package Directory]
├── __init__.py              [3.2 KB, ~90 lines]   → Public API
├── metadata.py              [2.3 KB, ~80 lines]   → Metadata classes
├── data_links.py            [1.5 KB, ~40 lines]   → File references
├── data_accessors.py        [22 KB, ~450 lines]   → Data loading & viz
├── run.py                   [3.7 KB, ~120 lines]  → Run class
├── organizer.py             [5.4 KB, ~170 lines]  → DataOrganizer
├── utils.py                 [2.3 KB, ~80 lines]   → Utilities
└── README_PACKAGE.md                              → Package docs

demo_nanoorganizer.py         # Complete working demo
quick_reference.py            # Quick reference guide for students
NanoOrganizer_Demo/           # Example database created by demo
├── .metadata/                # JSON metadata (lightweight, fast)
│   ├── index.json
│   └── Project_Cu2O_2024-10-20_Cu2O_V1_LowTemp.json
├── Project_Cu2O/             # Your actual data files
│   ├── UV_Vis/
│   ├── SAXS/
│   └── WAXS/
└── plots/                    # Generated visualizations
```

---

## 🚀 Quick Start

### 1. Create Your First Run

```python
from NanoOrganizer import (
    DataOrganizer, RunMetadata, ReactionParams, ChemicalSpec
)

# Initialize organizer
org = DataOrganizer("./MyProject")

# Define your experiment
metadata = RunMetadata(
    project="Project_Cu2O",
    experiment="2024-10-20",
    run_id="Cu2O_V1_LowTemp",
    sample_id="Sample_001",
    reaction=ReactionParams(
        chemicals=[
            ChemicalSpec(name="CuCl2", concentration=0.1, 
                        concentration_unit="mM", volume_uL=500),
            ChemicalSpec(name="NaOH", concentration=0.05, 
                        concentration_unit="mM", volume_uL=200),
        ],
        temperature_C=60.0,
        stir_time_s=300,
        reaction_time_s=1800,
        pH=7.5,
        solvent="Water",
        conductor="Dr. Zhang",
        description="Low temperature Cu2O synthesis"
    ),
    notes="First attempt",
    tags=["Cu2O", "optimization"]
)

# Create the run
run = org.create_run(metadata)
```

### 2. Link Your Data Files

```python
from NanoOrganizer import save_time_series_to_csv

# Option A: Save simulated/measured data to CSV
times = [0, 0, 0, ..., 30, 30, 30, ...]         # Time for each point
wavelengths = [200, 201, 202, ..., 200, 201, ...]  # Wavelengths
absorbance = [0.1, 0.12, 0.11, ..., 0.3, 0.32, ...]  # Absorbance

csv_files = save_time_series_to_csv(
    output_dir="./data/uvvis",
    prefix="uvvis",
    times=times,
    x_values=wavelengths,
    y_values=absorbance,
    x_name="wavelength",
    y_name="absorbance"
)

# Link to run
run.uvvis.link_data(
    csv_files, 
    time_points=[0, 30, 60, 120, 180, 300, 600],
    metadata={"instrument": "Agilent 8453"}
)

# Option B: Link existing CSV files
run.saxs.link_data(
    csv_files=["/path/to/saxs_001.csv", "/path/to/saxs_002.csv"],
    time_points=[0, 30, 60],
    metadata={"beamline": "CHESS"}
)

# Save everything
org.save()
```

### 3. Load and Visualize

```python
# Later: reload your data
org = DataOrganizer.load("./MyProject")

# Get a run
run = org.get_run("Project_Cu2O", "2024-10-20", "Cu2O_V1_LowTemp")

# Load data (lazy loading)
data = run.uvvis.load()
# Returns: {'times': array, 'wavelengths': array, 'absorbance': array}

# Plot data
run.uvvis.plot(plot_type="spectrum", time_point=180)
run.uvvis.plot(plot_type="kinetics", wavelength=520)
run.uvvis.plot(plot_type="heatmap")

run.saxs.plot(plot_type="profile", time_point=300, loglog=True)
run.saxs.plot(plot_type="kinetics", q_value=0.02)

run.waxs.plot(plot_type="pattern", time_point=300)
run.waxs.plot(plot_type="kinetics", two_theta_value=30)
```

---

## 📊 Supported Data Types

| Data Type | CSV Format | Plotting Modes |
|-----------|-----------|----------------|
| **UV-Vis** | `wavelength,absorbance` | spectrum, kinetics, heatmap |
| **SAXS** | `q,intensity` | profile, kinetics, heatmap |
| **WAXS** | `two_theta,intensity` | pattern, kinetics, heatmap |
| **SEM/TEM** | Image files (png, tif) | Display images |

---

## 🎨 Visualization Examples

### UV-Vis Plots
```python
# Single spectrum at t=180s
run.uvvis.plot(plot_type="spectrum", time_point=180)

# Growth kinetics at 520nm
run.uvvis.plot(plot_type="kinetics", wavelength=520)

# Full evolution heatmap
run.uvvis.plot(plot_type="heatmap")
```

### SAXS Plots
```python
# SAXS profile at t=300s
run.saxs.plot(plot_type="profile", time_point=300, loglog=True)

# Intensity vs time at q=0.02
run.saxs.plot(plot_type="kinetics", q_value=0.02)

# SAXS evolution heatmap
run.saxs.plot(plot_type="heatmap")
```

### Comparing Multiple Runs
```python
import matplotlib.pyplot as plt

run1 = org.get_run("Project_Cu2O", "2024-10-20", "Cu2O_V1_LowTemp")
run2 = org.get_run("Project_Cu2O", "2024-10-20", "Cu2O_V2_HighTemp")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
run1.uvvis.plot(plot_type="kinetics", wavelength=520, ax=axes[0])
run2.uvvis.plot(plot_type="kinetics", wavelength=520, ax=axes[1])
plt.show()
```

---

## 📝 CSV File Format

Each CSV file should contain data for **one time point**:

### UV-Vis Example (`uvvis_001.csv`)
```csv
wavelength,absorbance
200.0,0.05
201.0,0.06
202.0,0.07
...
```

### SAXS Example (`saxs_001.csv`)
```csv
q,intensity
0.01,1000.0
0.011,950.0
0.012,920.0
...
```

### WAXS Example (`waxs_001.csv`)
```csv
two_theta,intensity
10.0,50.0
10.1,52.0
10.2,51.5
...
```

**Time Information**:
- Provided via `time_points` parameter when linking
- Or extracted from filename (e.g., `uvvis_t0060s.csv` → 60 seconds)
- Or inferred from sequential order

---

## 🔍 Metadata Structure

Metadata is stored as clean, readable JSON:

```json
{
  "metadata": {
    "project": "Project_Cu2O",
    "experiment": "2024-10-20",
    "run_id": "Cu2O_V1_LowTemp",
    "reaction": {
      "chemicals": [
        {
          "name": "CuCl2",
          "concentration": 0.1,
          "concentration_unit": "mM",
          "volume_uL": 500
        }
      ],
      "temperature_C": 60.0,
      "pH": 7.5,
      "conductor": "Dr. Zhang"
    },
    "tags": ["Cu2O", "optimization"]
  },
  "data": {
    "uvvis": {
      "file_paths": ["/path/to/uvvis_001.csv", ...],
      "metadata": {"instrument": "Agilent 8453"},
      "time_points": [0, 30, 60, ...]
    }
  }
}
```

---

## 🛠️ Advanced Usage

### Custom Analysis
```python
import numpy as np

# Load data
data = run.uvvis.load()

# Extract peak positions over time
unique_times = np.unique(data['times'])
peak_positions = []

for t in unique_times:
    mask = data['times'] == t
    wl = data['wavelengths'][mask]
    abs_val = data['absorbance'][mask]
    
    peak_idx = np.argmax(abs_val)
    peak_positions.append(wl[peak_idx])

# Plot
import matplotlib.pyplot as plt
plt.plot(unique_times, peak_positions, 'o-')
plt.xlabel('Time (s)')
plt.ylabel('Peak Position (nm)')
plt.title('Plasmon Peak Shift')
plt.show()
```

### Data Validation
```python
# Check all runs
validation_results = org.validate_all()

# Check specific run
is_valid = run.uvvis.validate()
if not is_valid:
    print("Some UV-Vis files are missing!")
```

### Accessing Metadata
```python
# Access reaction parameters
temp = run.metadata.reaction.temperature_C
chemicals = run.metadata.reaction.chemicals
conductor = run.metadata.reaction.conductor

# Access tags and notes
tags = run.metadata.tags
notes = run.metadata.notes

# Access instrument metadata
instrument = run.uvvis.link.metadata.get('instrument')
beamline = run.saxs.link.metadata.get('beamline')
```

---

## 📚 Complete API Reference

### Main Classes

**`DataOrganizer`**
- `__init__(base_dir)` - Initialize organizer
- `create_run(metadata)` - Create new run
- `get_run(project, experiment, run_id)` - Get existing run
- `list_runs()` - List all runs
- `save()` - Save all metadata to JSON
- `load(base_dir)` - Load organizer from disk
- `validate_all()` - Validate all data files

**`Run`**
- `.metadata` - RunMetadata object
- `.uvvis` - UVVisData accessor
- `.saxs` - SAXSData accessor
- `.waxs` - WAXSData accessor
- `.sem` - ImageData accessor
- `.tem` - ImageData accessor

**`UVVisData` / `SAXSData` / `WAXSData`**
- `link_data(csv_files, time_points, metadata)` - Link data files
- `load()` - Load data (lazy loading)
- `validate()` - Check if files exist
- `plot(plot_type, ...)` - Visualize data

**`RunMetadata`**
```python
RunMetadata(
    project: str,              # Project name
    experiment: str,           # Usually date (2024-10-20)
    run_id: str,              # Unique run identifier
    sample_id: str,           # Sample identifier
    reaction: ReactionParams, # Reaction conditions
    notes: str = "",          # Additional notes
    tags: List[str] = []      # Tags for searching
)
```

**`ReactionParams`**
```python
ReactionParams(
    chemicals: List[ChemicalSpec],
    temperature_C: float = 25.0,
    stir_time_s: float = 0.0,
    reaction_time_s: float = 0.0,
    pH: Optional[float] = None,
    solvent: str = "Water",
    conductor: str = "Unknown",
    description: str = ""
)
```

**`ChemicalSpec`**
```python
ChemicalSpec(
    name: str,
    concentration: float,
    concentration_unit: str = "mM",
    volume_uL: float = 0.0
)
```

---

## 💡 Tips & Best Practices

### Organization
- Use descriptive project/experiment/run_id names
- Include dates in experiment names (e.g., "2024-10-20")
- Add meaningful tags for easy searching

### Data Files
- Keep raw data files organized by technique
- Use consistent naming (uvvis_001.csv, uvvis_002.csv, ...)
- Include headers in CSV files

### Metadata
- Record all experimental conditions
- Add notes about anything unusual
- Include operator name and instrument details

### Workflow
1. Create run → Link data → Save → Validate
2. Always `save()` after adding data
3. Validate before important analysis

### Memory Management
- Data is loaded lazily (only when you call `.load()`)
- This makes the system fast for large datasets
- You can load/unload data as needed

### Plotting
- Use `plot_type="heatmap"` for overview
- Use `plot_type="kinetics"` to track specific features
- Use `plot_type="spectrum/profile/pattern"` for snapshots

### Backup
- The `.metadata` folder is small - easy to backup
- Your data files stay where you put them
- Version control friendly (JSON metadata)

---

## 🧪 Running the Demo

```bash
# Install dependencies
pip install numpy matplotlib

# Run the complete demo
python demo_nanoorganizer.py

# This will create:
# - NanoOrganizer_Demo/ with example data
# - Plots showing all visualization types
# - JSON metadata files
```

---

## 📖 Example Workflow

```python
# 1. Setup
from NanoOrganizer import *

org = DataOrganizer("./MyProject")

# 2. Create run with metadata
run = org.create_run(metadata)

# 3. Generate and save data
times, wls, abs = your_measurement_function()
csv_files = save_time_series_to_csv(
    "./data/uvvis", "uvvis", times, wls, abs,
    x_name="wavelength", y_name="absorbance"
)

# 4. Link data
run.uvvis.link_data(csv_files, time_points=[0, 30, 60, ...])

# 5. Save
org.save()

# 6. Later: load and analyze
org = DataOrganizer.load("./MyProject")
run = org.get_run("Project", "Experiment", "Run")
data = run.uvvis.load()

# 7. Visualize
run.uvvis.plot(plot_type="heatmap")

# 8. Custom analysis
import numpy as np
peak_positions = extract_peaks(data)
plt.plot(peak_positions)
```

---

## 🤝 For Students

This system is designed to be:
- **Easy to use** - Simple, clean API
- **Well documented** - Check `quick_reference.py` for examples
- **Flexible** - Works with any directory structure
- **Fast** - Lazy loading for large datasets
- **Safe** - Validation checks prevent errors

Start with the demo, then adapt it for your experiments!

---

## 📄 Files Included

1. **NanoOrganizer.py** - Main module (1000+ lines, production-ready)
2. **demo_nanoorganizer.py** - Complete working demo
3. **quick_reference.py** - Quick reference for students
4. **NanoOrganizer_Demo/** - Example database with:
   - 2 experimental runs
   - UV-Vis, SAXS, WAXS time-series data
   - Generated plots
   - JSON metadata

---

## 🎉 Features Summary

| Feature | Status |
|---------|--------|
| JSON metadata storage | ✅ |
| Flexible directory structure | ✅ |
| Lazy data loading | ✅ |
| Data validation | ✅ |
| UV-Vis support | ✅ |
| SAXS support | ✅ |
| WAXS support | ✅ |
| Image support (SEM/TEM) | ✅ |
| Built-in plotting | ✅ |
| Time-series analysis | ✅ |
| Comparison plots | ✅ |
| Extensible design | ✅ |

---

## 📞 Questions?

Check:
1. `demo_nanoorganizer.py` - Complete working example
2. `quick_reference.py` - Common usage patterns
3. The inline documentation in `NanoOrganizer.py`

Happy experimenting! 🔬✨