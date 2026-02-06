# NanoOrganizer Web GUI Suite

Complete guide to all web-based visualization and management tools.

---

## 🚀 Installation

Install with web GUI support:

```bash
pip install -e ".[web,image]"
```

This installs all required dependencies:
- Streamlit (web framework)
- Pandas (data handling)
- Pillow (image support)
- Matplotlib (plotting)

---

## 📊 Four Integrated GUIs

NanoOrganizer provides four complementary web applications:

### 1. **Data Viewer** (`nanoorganizer-viz`) ⭐ Main visualization tool

**Purpose**: Advanced visualization and comparison of NanoOrganizer projects

**Launch**:
```bash
nanoorganizer-viz
```

**Features**:
- ✅ Multi-dataset overlay (compare 2-10+ runs)
- ✅ Advanced plot controls (log/linear scales)
- ✅ Colormap selection for heatmaps/images
- ✅ Side-by-side image comparison
- ✅ Export plots (PNG 300 DPI)
- ✅ Interactive data exploration

**Best for**: Daily analysis of experimental data, comparing runs, creating publication figures

---

### 2. **CSV Plotter** (`nanoorganizer-csv`) 📈 Quick plotting

**Purpose**: Fast plotting of CSV files without NanoOrganizer metadata

**Launch**:
```bash
nanoorganizer-csv
```

**Features**:
- 📤 Upload CSVs or browse server files
- 🔍 Auto-detect columns (X, Y axes)
- 📊 Overlay multiple files
- 🎨 Line/scatter/combined plots
- 📐 Log/linear scales
- 💾 Export PNG/SVG
- 📊 Statistics view

**Best for**: Quick data checks, comparing CSVs from different sources, ad-hoc plotting

---

### 3. **Data Manager** (`nanoorganizer-manage`) 🔧 Project creation

**Purpose**: Create projects, organize metadata, link data files

**Launch**:
```bash
nanoorganizer-manage
```

**Features**:
- 🆕 Create new NanoOrganizer projects
- 📝 Fill metadata forms (chemicals, reactions, etc.)
- 🔗 Link data files by type (UV-Vis, SAXS, etc.)
- 🗂️ Browse server filesystem
- 💾 Save projects to disk
- 👀 View existing runs

**Best for**: Initial project setup, organizing new experimental campaigns, batch metadata entry

---

### 4. **3D Plotter** (`nanoorganizer-3d`) 📊 Volumetric visualization

**Purpose**: 3D visualization (XYZ + color dimension)

**Launch**:
```bash
nanoorganizer-3d
```

**Features**:
- 📊 Surface plots
- 🕸️ Wireframe plots
- ⚫ 3D scatter plots
- 🗺️ 2D contour projections
- 🎨 Multiple colormaps
- 📐 Adjustable view angles
- 💾 Export high-quality plots

**Best for**: Time-series heatmaps as 3D surfaces, spatial data, volumetric analysis

---

## 🔄 Typical Workflow

### Workflow 1: Starting from scratch

```
1. Create project     → nanoorganizer-manage
2. Link data files    → nanoorganizer-manage
3. Save metadata      → nanoorganizer-manage
4. Visualize & export → nanoorganizer-viz
```

### Workflow 2: Quick analysis (no project)

```
1. Have CSV files     → nanoorganizer-csv
2. Upload/select      → Auto-detect columns
3. Plot & compare     → Export results
```

### Workflow 3: Python + GUI hybrid

```python
# In Jupyter/Python script
from NanoOrganizer import DataOrganizer, RunMetadata, ...

org = DataOrganizer("./MyProject")
# ... create runs, link data programmatically ...
org.save()
```

```bash
# Then launch GUI for interactive exploration
nanoorganizer-viz
```

---

## 🎯 Feature Comparison

| Feature | Data Viewer | CSV Plotter | Data Manager | 3D Plotter |
|---------|-------------|-------------|--------------|------------|
| **Needs NanoOrganizer project** | ✅ Yes | ❌ No | Creates it | ❌ No |
| **Multi-dataset overlay** | ✅ Yes | ✅ Yes | ❌ N/A | ❌ Single |
| **Metadata forms** | ❌ View only | ❌ N/A | ✅ Yes | ❌ N/A |
| **File linking** | ❌ No | ❌ No | ✅ Yes | ❌ No |
| **Export plots** | ✅ PNG | ✅ PNG/SVG | ❌ N/A | ✅ PNG/SVG |
| **3D visualization** | ❌ 2D only | ❌ 2D only | ❌ N/A | ✅ Yes |
| **Server file browsing** | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| **Best use case** | Daily viz | Quick plots | Setup | Special viz |

---

## 💡 Tips & Tricks

### Data Viewer (`nanoorganizer-viz`)

**Multi-run comparison**:
1. Select multiple runs from dropdown
2. Choose plot type (spectrum, kinetics, etc.)
3. Adjust line styles in sidebar
4. Toggle log/linear scales
5. Download high-res PNG

**Image comparison**:
1. Select 2+ runs with SEM/TEM data
2. Images appear side-by-side
3. Change colormap to highlight features

### CSV Plotter (`nanoorganizer-csv`)

**Quick workflow**:
1. Upload multiple CSVs
2. Auto-detect should pick correct columns
3. If not, manually select X and Y columns
4. Choose line/scatter/both
5. Adjust opacity for overlapping data

**Server browsing**:
- Use wildcards: `uvvis_*.csv`, `data_2024*.txt`
- Navigate to parent directory first
- Select subset of found files

### Data Manager (`nanoorganizer-manage`)

**Efficient data entry**:
1. Create run with metadata first
2. Save project immediately
3. Then link data files in batches
4. Save again after linking

**Chemicals list**:
- Add all chemicals before creating run
- Use consistent naming for later searches
- Volume in μL, concentration in mM

### 3D Plotter (`nanoorganizer-3d`)

**Best view angles**:
- Surface: elev=30, azim=-60
- Wireframe: elev=20, azim=-45
- Scatter: rotate interactively (not available in Streamlit)

**Data format**:
- CSV with 3-4 columns: X, Y, Z, [Color]
- Can handle gridded or scattered data
- Auto-interpolates scattered data to grid

---

## 🔌 Network Access

All GUIs run as web servers on port 8501 by default.

### Local access (same machine):
```
http://localhost:8501
```

### Remote access (from another machine):

**Option 1: SSH tunnel (secure)**
```bash
# On your local machine
ssh -L 8501:localhost:8501 user@server.com

# Then browse to http://localhost:8501
```

**Option 2: Firewall rule (less secure)**
```bash
# On the server
sudo firewall-cmd --add-port=8501/tcp --permanent
sudo firewall-cmd --reload

# Then browse to http://server.ip:8501
```

---

## 🐛 Troubleshooting

### "Module not found" errors
```bash
# Reinstall with web support
pip install -e ".[web,image]"
```

### "Port already in use"
```bash
# Use different port
streamlit run NanoOrganizer/web/app.py --server.port 8502
```

### Browser opens on server
```bash
# Already fixed in CLI scripts with --server.headless true
# If running manually:
streamlit run app.py --server.headless true
```

### Can't access from remote machine
- Check firewall rules
- Use SSH tunnel instead
- Verify server IP and port

---

## 🆘 Getting Help

- **GitHub Issues**: https://github.com/yugangzhang/Nanoorganizer/issues
- **Documentation**: See `docs/` directory
- **Examples**: See `example/` directory

---

## 🔄 Updating

After pulling new changes:

```bash
# Reinstall in editable mode
pip install -e ".[web,image]"

# Verify new commands are available
nanoorganizer-viz --help
nanoorganizer-csv --help
nanoorganizer-manage --help
nanoorganizer-3d --help
```

---

## 📝 Summary

Four GUIs for different needs:

1. **nanoorganizer-viz** - Main tool, daily use, comparison ⭐
2. **nanoorganizer-csv** - Quick plotting, no setup needed
3. **nanoorganizer-manage** - Project creation and organization
4. **nanoorganizer-3d** - Special 3D visualizations

Use them independently or as part of an integrated workflow!
