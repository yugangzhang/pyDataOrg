#!/usr/bin/env python3
"""
NanoOrganizer Hub - Central launcher for all web GUIs.

This is the main entry point that launches on port 8501.
From here, users can access all four specialized GUIs.
"""

import streamlit as st
from pathlib import Path
import subprocess
import sys

st.set_page_config(
    page_title="NanoOrganizer Hub",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------------
# Main Hub
# ---------------------------------------------------------------------------

st.title("🔬 NanoOrganizer Hub")
st.markdown("### Central launcher for all visualization and management tools")

st.divider()

# ---------------------------------------------------------------------------
# Tool Cards
# ---------------------------------------------------------------------------

col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Data Viewer")
    st.markdown("""
    **Main visualization tool for NanoOrganizer projects**

    Features:
    - Multi-dataset overlay
    - Log/linear scales
    - Image comparison
    - High-quality exports

    **Use when:** Analyzing experimental runs, creating publication figures
    """)

    if st.button("🚀 Launch Data Viewer", key="viz", use_container_width=True):
        st.info("Opening Data Viewer...")
        st.markdown("""
        **To launch manually:**
        ```bash
        streamlit run NanoOrganizer/web/app.py --server.port 8502
        ```
        Then navigate to: http://130.199.242.142:8502
        """)

    st.divider()

    st.subheader("🔧 Data Manager")
    st.markdown("""
    **Create and manage NanoOrganizer projects**

    Features:
    - Create new projects
    - Fill metadata forms
    - Link data files
    - Browse server filesystem

    **Use when:** Starting new experimental campaigns, organizing data
    """)

    if st.button("🚀 Launch Data Manager", key="manage", use_container_width=True):
        st.info("Opening Data Manager...")
        st.markdown("""
        **To launch manually:**
        ```bash
        streamlit run NanoOrganizer/web/data_manager.py --server.port 8503
        ```
        Then navigate to: http://130.199.242.142:8503
        """)

with col2:
    st.subheader("📈 CSV Plotter")
    st.markdown("""
    **Quick plotting without metadata**

    Features:
    - Upload or browse CSVs
    - Auto-detect columns
    - Multi-curve overlay
    - Custom colors & markers
    - NPZ file support

    **Use when:** Quick data checks, comparing files from different sources
    """)

    if st.button("🚀 Launch CSV Plotter", key="csv", use_container_width=True):
        st.info("Opening CSV Plotter...")
        st.markdown("""
        **To launch manually:**
        ```bash
        streamlit run NanoOrganizer/web/csv_plotter.py --server.port 8504
        ```
        Then navigate to: http://130.199.242.142:8504
        """)

    st.divider()

    st.subheader("📊 3D Plotter")
    st.markdown("""
    **3D visualization (XYZ + color)**

    Features:
    - Surface/wireframe/scatter
    - Adjustable view angles
    - Multiple colormaps
    - Synthetic data generation

    **Use when:** Visualizing volumetric data, time-series heatmaps as 3D
    """)

    if st.button("🚀 Launch 3D Plotter", key="3d", use_container_width=True):
        st.info("Opening 3D Plotter...")
        st.markdown("""
        **To launch manually:**
        ```bash
        streamlit run NanoOrganizer/web/plotter_3d.py --server.port 8505
        ```
        Then navigate to: http://130.199.242.142:8505
        """)

# Second row
st.divider()

col3, col4 = st.columns(2)

with col3:
    st.subheader("🖼️ 2D Image Viewer")
    st.markdown("""
    **Dedicated 2D image visualization**

    Features:
    - Load image stacks
    - Browse through frames
    - Colormap selection
    - Adjustable intensity
    - Side-by-side comparison

    **Use when:** Viewing detector images, microscopy stacks, heatmaps
    """)

    if st.button("🚀 Launch Image Viewer", key="img", use_container_width=True):
        st.info("Opening Image Viewer...")
        st.markdown("""
        **To launch manually:**
        ```bash
        streamlit run NanoOrganizer/web/image_viewer.py --server.port 8506
        ```
        Then navigate to: http://130.199.242.142:8506
        """)

with col4:
    st.subheader("📐 Multi-Axes Plotter")
    st.markdown("""
    **Create complex multi-panel figures**

    Features:
    - Multiple subplots
    - Assign data to axes
    - Flexible layouts
    - Publication-ready exports

    **Use when:** Creating multi-panel figures, comparing different data types
    """)

    if st.button("🚀 Launch Multi-Axes Plotter", key="multi", use_container_width=True):
        st.info("Opening Multi-Axes Plotter...")
        st.markdown("""
        **To launch manually:**
        ```bash
        streamlit run NanoOrganizer/web/multi_axes_plotter.py --server.port 8507
        ```
        Then navigate to: http://130.199.242.142:8507
        """)

# ---------------------------------------------------------------------------
# Quick Launch Commands
# ---------------------------------------------------------------------------

st.divider()
st.subheader("⚡ Quick Launch Commands")

with st.expander("📋 Command Reference", expanded=False):
    st.markdown("""
    ### Option 1: Use separate terminals (recommended)

    Open separate terminal windows for each tool:

    ```bash
    # Terminal 1: Data Viewer
    streamlit run NanoOrganizer/web/app.py --server.port 8502

    # Terminal 2: CSV Plotter
    streamlit run NanoOrganizer/web/csv_plotter.py --server.port 8504

    # Terminal 3: 3D Plotter
    streamlit run NanoOrganizer/web/plotter_3d.py --server.port 8505

    # Terminal 4: Image Viewer
    streamlit run NanoOrganizer/web/image_viewer.py --server.port 8506
    ```

    ### Option 2: Background processes

    ```bash
    streamlit run NanoOrganizer/web/app.py --server.port 8502 &
    streamlit run NanoOrganizer/web/csv_plotter.py --server.port 8504 &
    streamlit run NanoOrganizer/web/plotter_3d.py --server.port 8505 &
    streamlit run NanoOrganizer/web/image_viewer.py --server.port 8506 &
    ```

    ### View running Streamlit apps

    ```bash
    ps aux | grep streamlit
    ```

    ### Kill all Streamlit apps

    ```bash
    pkill -f streamlit
    ```
    """)

# ---------------------------------------------------------------------------
# System Info
# ---------------------------------------------------------------------------

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Hub Port", "8501")

with col2:
    st.metric("Available Tools", "6")

with col3:
    try:
        import NanoOrganizer
        st.metric("NanoOrganizer", NanoOrganizer.__version__)
    except:
        st.metric("NanoOrganizer", "Not installed")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()

st.markdown("""
### 💡 Usage Tips

**Multiple tools simultaneously:**
- Each tool runs on its own port (8502-8507)
- You can have all tools open at once
- Each tool maintains its own state
- Use separate browser tabs for each tool

**Firewall setup:**
```bash
# Open ports for all tools
sudo firewall-cmd --permanent --add-port=8501-8507/tcp
sudo firewall-cmd --reload
```

**SSH tunneling (if needed):**
```bash
# On your local machine
ssh -L 8501:localhost:8501 user@server
ssh -L 8502:localhost:8502 user@server
ssh -L 8503:localhost:8503 user@server
# ... etc
```

### 📚 Documentation
- `docs/WEB_GUI_GUIDE.md` - Complete guide
- `INSTALLATION_NEXT_STEPS.md` - Setup instructions
- `PHASE_IMPLEMENTATION_SUMMARY.md` - Feature list
""")

# ---------------------------------------------------------------------------
# Auto-launch options (for future implementation)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("🔧 Settings")

    st.subheader("Server Info")
    st.text("Hub: http://130.199.242.142:8501")

    st.divider()

    st.subheader("Tool Ports")
    st.text("Data Viewer:  8502")
    st.text("Data Manager: 8503")
    st.text("CSV Plotter:  8504")
    st.text("3D Plotter:   8505")
    st.text("Image Viewer: 8506")
    st.text("Multi-Axes:   8507")

    st.divider()

    st.subheader("Quick Links")
    st.markdown("[Data Viewer](http://130.199.242.142:8502)")
    st.markdown("[CSV Plotter](http://130.199.242.142:8504)")
    st.markdown("[3D Plotter](http://130.199.242.142:8505)")

    st.divider()

    if st.button("📖 View Documentation"):
        st.info("Documentation available in docs/ folder")
