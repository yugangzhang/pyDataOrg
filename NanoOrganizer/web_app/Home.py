#!/usr/bin/env python3
"""
NanoOrganizer Web App - All tools in one place on port 8501!

Run with:
    streamlit run NanoOrganizer/web_app/Home.py

Or use console command:
    nanoorganizer
"""

import streamlit as st
from pathlib import Path
from NanoOrganizer.web_app.components.security import (
    format_allowed_roots,
    initialize_security_context,
    require_authentication,
)

st.set_page_config(
    page_title="NanoOrganizer",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

initialize_security_context()
require_authentication()

# ---------------------------------------------------------------------------
# Home Page
# ---------------------------------------------------------------------------

st.title("🔬 NanoOrganizer")
st.markdown("### Complete Web Suite for Nanoparticle Synthesis Data")

if st.session_state.get("user_mode"):
    if st.session_state.get("secure_mode"):
        st.info(
            f"🔒 **Secure Mode** — allowed folders: `{format_allowed_roots()}` "
            f"(password required)"
        )
    else:
        st.info(
            f"🔒 **Restricted Mode** — browsing locked to: "
            f"`{st.session_state['user_start_dir']}`"
        )

st.divider()

# ---------------------------------------------------------------------------
# Welcome Section
# ---------------------------------------------------------------------------

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("""
    ## Welcome! 👋

    All tools run on **one port**. Use the sidebar 👈 to switch between pages.

    ### Beamline data explorers (CMS SAXS/MAXS auto-reduction output):

    📈 **SAXS 1D Explorer** — overlay circular-average I(q) curves; filter by
    filename / keyword / acquisition time; full styling (xlim/ylim, per-curve
    color, marker, line style, width, size, opacity), waterfall stacking, and
    CSV export.

    🗺️ **SAXS 2D + 1D** — q–φ heatmap beside its circular average, auto-paired
    by filename; step through frames by time, overlay multiple 1D curves.

    ### General-purpose tools:

    🎨 **CSV Plotter** — quick plotting with full per-curve styling (CSV/NPZ)

    🖼️ **Image Viewer** — view 2D images, stacks, and detector data

    📐 **Multi-Axes** — publication-ready multi-panel figures

    📊 **3D Plotter** — interactive 3D visualization with Plotly

    🔧 **Data Manager** — create projects and organize metadata
    """)

with col2:
    st.info("""
    **Quick Start:**

    1. Generate test data first
       → Go to "Test Data Generator"

    2. Try the CSV Plotter
       → Load generated CSVs
       → Customize styling

    3. View images
       → Load generated stacks
       → Browse frames

    4. Create multi-panel figure
       → Use Multi-Axes tool
    """)

# ---------------------------------------------------------------------------
# Features Overview
# ---------------------------------------------------------------------------

st.divider()
st.header("🎯 Key Features")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    ### 📊 Visualization
    - Multi-dataset overlay
    - Log/linear scales
    - 15+ colormaps
    - Interactive 3D (Plotly)
    - Beautiful plots (Seaborn)
    """)

with col2:
    st.markdown("""
    ### 🎨 Customization
    - Per-curve colors
    - 12 marker types
    - 4 line styles
    - Opacity control
    - Custom layouts
    """)

with col3:
    st.markdown("""
    ### 💾 Export
    - PNG (300 DPI)
    - SVG (vector)
    - Interactive HTML
    - Publication-ready
    - Batch export
    """)

# ---------------------------------------------------------------------------
# System Info
# ---------------------------------------------------------------------------

st.divider()
st.header("💻 System Information")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Port", "8501")

with col2:
    st.metric("Tools", "7")

with col3:
    try:
        import NanoOrganizer
        st.metric("Version", NanoOrganizer.__version__)
    except:
        st.metric("Version", "N/A")

with col4:
    # Check if test data exists
    test_data_dir = Path(__file__).parent.parent.parent / "TestData"
    if test_data_dir.exists():
        st.metric("Test Data", "✅ Ready")
    else:
        st.metric("Test Data", "⚠️ Generate")

# ---------------------------------------------------------------------------
# Quick Links
# ---------------------------------------------------------------------------

st.divider()
st.header("📚 Documentation")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **Getting Started:**
    - `QUICK_START_PHASE5.md` - Quick start guide
    - `COMPLETE_WEB_SUITE.md` - Complete overview
    - `PHASE5_IMPROVEMENTS.md` - All features

    **Installation:**
    - `INSTALLATION_NEXT_STEPS.md` - Setup guide
    - `verify_installation.py` - Check installation
    """)

with col2:
    st.markdown("""
    **User Guides:**
    - `docs/WEB_GUI_GUIDE.md` - Complete user manual
    - `docs/adding_new_datatype.md` - Extend the system
    - `README.md` - Package overview

    **Help:**
    - GitHub: [Issues](https://github.com/yugangzhang/Nanoorganizer/issues)
    - Email: yuzhang@bnl.gov
    """)

# ---------------------------------------------------------------------------
# Tips
# ---------------------------------------------------------------------------

st.divider()

with st.expander("💡 Tips & Tricks"):
    st.markdown("""
    ### General Tips

    **Navigation:**
    - Use sidebar to switch between tools
    - Each tool maintains its own state
    - Can work on multiple tools simultaneously (use browser tabs)

    **Data Loading:**
    - CSV Plotter: Upload or browse server files
    - Data Viewer: Requires NanoOrganizer project
    - All tools support NPZ files

    **Styling:**
    - CSV Plotter has most detailed per-curve controls
    - Use Seaborn themes for prettier plots
    - Export as SVG for publications (editable in Illustrator/Inkscape)

    **Performance:**
    - Large datasets may take time to load
    - Use "Browse server" instead of upload for big files
    - Image viewer downsamples very large images

    ### Keyboard Shortcuts

    - `r` - Rerun the app
    - `c` - Clear cache
    - `Ctrl+K` - Open command palette
    - `Ctrl+S` - Settings
    """)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()

st.markdown("""
<div style='text-align: center; color: gray; padding: 20px;'>
    <p>NanoOrganizer v1.0 | Brookhaven National Laboratory | CFN</p>
    <p>🔬 Built with Streamlit, Plotly, Seaborn, and ❤️</p>
</div>
""", unsafe_allow_html=True)
