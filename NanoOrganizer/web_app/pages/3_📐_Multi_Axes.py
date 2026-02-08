#!/usr/bin/env python3
"""
Multi-Axes Plotter - Create complex multi-panel figures.

Features:
- Multiple subplots with flexible layouts
- Assign specific data to specific axes
- Dynamic layout adjustment
- Publication-ready multi-panel figures
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.gridspec as gridspec  # noqa: E402

import streamlit as st  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pathlib import Path  # noqa: E402
import io  # noqa: E402
import sys  # noqa: E402

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.folder_browser import folder_browser  # noqa: E402
from components.floating_button import floating_sidebar_toggle  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
MARKERS = ['o', 's', '^', 'v', 'D', 'p', '*', 'h']

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def load_data_file(file_path):
    """Load CSV, TXT, or NPZ file."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    try:
        if suffix == '.npz':
            data = np.load(file_path)
            df_dict = {}
            for key in data.files:
                arr = data[key]
                if arr.ndim == 1:
                    df_dict[key] = arr
                elif arr.ndim == 2:
                    df_dict[key] = arr.flatten()
            return pd.DataFrame(df_dict)
        else:
            df = pd.read_csv(file_path, sep=',')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep='\t')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep=r'\s+')
            return df
    except Exception as e:
        st.error(f"Error loading {Path(file_path).name}: {e}")
        return None


def browse_directory(base_dir, pattern="*.csv"):
    """Browse directory and find files."""
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    files = list(base_path.rglob(pattern))
    return [str(f) for f in sorted(files)]


def _save_fig_to_bytes(fig, format='png', dpi=300):
    """Save matplotlib figure to bytes buffer."""
    buf = io.BytesIO()
    fig.savefig(buf, format=format, dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

if 'axes_assignments' not in st.session_state:
    st.session_state['axes_assignments'] = {}

if 'dataframes_multi' not in st.session_state:
    st.session_state['dataframes_multi'] = {}

if 'file_paths_multi' not in st.session_state:
    st.session_state['file_paths_multi'] = {}

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.title("📐 Multi-Axes Plotter")
st.markdown("Create complex multi-panel figures with flexible layouts")

# Floating sidebar toggle button (bottom-left)
floating_sidebar_toggle()

# ---------------------------------------------------------------------------
# Sidebar: Load Data
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 Load Data")

    data_source = st.radio(
        "Data source",
        ["Upload files", "Browse server"]
    )

    if data_source == "Upload files":
        uploaded_files = st.file_uploader(
            "Upload data files",
            type=['csv', 'txt', 'dat', 'npz'],
            accept_multiple_files=True
        )

        if uploaded_files:
            for uploaded_file in uploaded_files:
                try:
                    temp_path = Path(f"/tmp/{uploaded_file.name}")
                    with open(temp_path, 'wb') as f:
                        f.write(uploaded_file.getbuffer())

                    df = load_data_file(str(temp_path))
                    if df is not None:
                        st.session_state['dataframes_multi'][uploaded_file.name] = df
                        st.session_state['file_paths_multi'][uploaded_file.name] = uploaded_file.name
                except Exception as e:
                    st.error(f"Error: {e}")

    else:  # Browse server
        st.markdown("**🗂️ Interactive Folder Browser**")
        st.markdown("Click folders to navigate, select files with checkboxes:")

        # File pattern selector
        st.markdown("**📋 File Type Filter:**")
        pattern = st.selectbox(
            "Extension pattern",
            ["*.csv", "*.npz", "*.txt", "*.dat", "*.*"],
            help="Filter files by extension",
            label_visibility="collapsed"
        )

        st.info("💡 Tip: Use '🔍 Advanced Filters' below for name-based filtering")

        # Use folder browser component
        selected_files = folder_browser(
            key="multi_axes_browser",
            show_files=True,
            file_pattern=pattern,
            multi_select=True
        )

        # Load button
        if selected_files and st.button("📥 Load Selected Files", key="multi_load_btn"):
            for full_path in selected_files:
                df = load_data_file(full_path)
                if df is not None:
                    file_name = Path(full_path).name
                    st.session_state['dataframes_multi'][file_name] = df
                    st.session_state['file_paths_multi'][file_name] = full_path
                    st.success(f"✅ Loaded {file_name}")

    # Get dataframes from session state
    dataframes = st.session_state['dataframes_multi']
    file_paths = st.session_state['file_paths_multi']

    # Clear button
    if dataframes:
        if st.button("🗑️ Clear All Data", key="clear_multi_data"):
            st.session_state['dataframes_multi'] = {}
            st.session_state['file_paths_multi'] = {}
            st.session_state['axes_assignments'] = {}
            st.rerun()

    if not dataframes:
        st.info("👆 Upload or select data files to get started")
        st.stop()

    st.success(f"✅ Loaded {len(dataframes)} file(s)")

    # ---------------------------------------------------------------------------
    # Layout Configuration
    # ---------------------------------------------------------------------------

    st.header("📐 Layout")

    layout_type = st.radio(
        "Layout type",
        ["Grid (rows × cols)", "Custom positions"],
        help="Grid for regular layouts, custom for complex arrangements"
    )

    if layout_type == "Grid (rows × cols)":
        col1, col2 = st.columns(2)
        with col1:
            n_rows = st.number_input("Rows", 1, 5, 2, 1)
        with col2:
            n_cols = st.number_input("Columns", 1, 5, 2, 1)

        n_axes = n_rows * n_cols
        axes_labels = [f"({i//n_cols+1},{i%n_cols+1})" for i in range(n_axes)]

    else:  # Custom
        n_axes = st.number_input("Number of axes", 1, 9, 4, 1)
        axes_labels = [f"Axis {i+1}" for i in range(n_axes)]

    # Figure size
    st.subheader("📏 Figure Size")
    col1, col2 = st.columns(2)
    with col1:
        fig_width = st.slider("Width (inches)", 6, 20, 12, 1)
    with col2:
        fig_height = st.slider("Height (inches)", 4, 16, 8, 1)

# ---------------------------------------------------------------------------
# Main Area: Data Assignment
# ---------------------------------------------------------------------------

st.header("🎯 Data Assignment")

st.markdown("Assign data files to specific axes for plotting")

# Create tabs for each axis
tabs = st.tabs(axes_labels)

for ax_idx, (tab, ax_label) in enumerate(zip(tabs, axes_labels)):
    with tab:
        st.subheader(f"Configure {ax_label}")

        # Select which datasets to plot on this axis
        selected_datasets = st.multiselect(
            "Select datasets",
            list(dataframes.keys()),
            key=f"datasets_{ax_idx}",
            help="Select one or more datasets to plot on this axis"
        )

        if not selected_datasets:
            st.info("No datasets selected for this axis")
            continue

        # Get columns from first dataset
        first_df = dataframes[selected_datasets[0]]
        all_cols = list(first_df.columns)

        col1, col2 = st.columns(2)
        with col1:
            x_col = st.selectbox(
                "X-axis column",
                all_cols,
                key=f"x_{ax_idx}",
                help="Column to use for X-axis"
            )

        with col2:
            y_col = st.selectbox(
                "Y-axis column",
                all_cols,
                index=min(1, len(all_cols)-1),
                key=f"y_{ax_idx}",
                help="Column to use for Y-axis"
            )

        # Plot style
        col1, col2, col3 = st.columns(3)
        with col1:
            x_scale = st.radio(
                "X scale",
                ["linear", "log"],
                key=f"xscale_{ax_idx}",
                horizontal=True
            )
        with col2:
            y_scale = st.radio(
                "Y scale",
                ["linear", "log"],
                key=f"yscale_{ax_idx}",
                horizontal=True
            )
        with col3:
            show_legend = st.checkbox(
                "Show legend",
                value=True,
                key=f"legend_{ax_idx}"
            )

        # Labels
        col1, col2, col3 = st.columns(3)
        with col1:
            title = st.text_input(
                "Title",
                value=f"{ax_label}",
                key=f"title_{ax_idx}"
            )
        with col2:
            xlabel = st.text_input(
                "X label",
                value=x_col,
                key=f"xlabel_{ax_idx}"
            )
        with col3:
            ylabel = st.text_input(
                "Y label",
                value=y_col,
                key=f"ylabel_{ax_idx}"
            )

        # Store assignment
        st.session_state['axes_assignments'][ax_idx] = {
            'datasets': selected_datasets,
            'x_col': x_col,
            'y_col': y_col,
            'x_scale': x_scale,
            'y_scale': y_scale,
            'show_legend': show_legend,
            'title': title,
            'xlabel': xlabel,
            'ylabel': ylabel
        }

# ---------------------------------------------------------------------------
# Create Figure
# ---------------------------------------------------------------------------

st.divider()
st.header("📊 Multi-Panel Figure")

# Create figure and axes
if layout_type == "Grid (rows × cols)":
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(fig_width, fig_height))
    if n_axes == 1:
        axes = np.array([axes])
    axes = axes.flatten()
else:
    # Custom layout with gridspec
    fig = plt.figure(figsize=(fig_width, fig_height))
    gs = gridspec.GridSpec(n_rows, n_cols, figure=fig)
    axes = [fig.add_subplot(gs[i]) for i in range(n_axes)]

# Plot on each axis
for ax_idx, ax in enumerate(axes):
    assignment = st.session_state['axes_assignments'].get(ax_idx, {})

    if not assignment or not assignment.get('datasets'):
        # Empty axis
        ax.text(0.5, 0.5, f"No data\n{axes_labels[ax_idx]}",
               ha='center', va='center', transform=ax.transAxes,
               fontsize=12, color='gray')
        ax.set_xticks([])
        ax.set_yticks([])
        continue

    # Plot datasets
    datasets = assignment['datasets']
    x_col = assignment['x_col']
    y_col = assignment['y_col']

    for idx, file_name in enumerate(datasets):
        df = dataframes[file_name]

        if x_col not in df.columns or y_col not in df.columns:
            continue

        x_data = df[x_col].values
        y_data = df[y_col].values

        # Remove NaN
        mask = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data = x_data[mask]
        y_data = y_data[mask]

        if len(x_data) == 0:
            continue

        # Plot
        color = COLORS[idx % len(COLORS)]
        marker = MARKERS[idx % len(MARKERS)]

        ax.plot(x_data, y_data,
               color=color,
               marker=marker,
               markersize=4,
               linewidth=2,
               alpha=0.8,
               label=Path(file_name).stem,
               markevery=max(1, len(x_data)//20))

    # Apply settings
    ax.set_xscale(assignment['x_scale'])
    ax.set_yscale(assignment['y_scale'])
    ax.set_xlabel(assignment['xlabel'], fontsize=10)
    ax.set_ylabel(assignment['ylabel'], fontsize=10)
    ax.set_title(assignment['title'], fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.3, linestyle='--')

    if assignment['show_legend'] and len(datasets) > 1:
        ax.legend(loc='best', fontsize=8, framealpha=0.9)

plt.tight_layout()

# Show figure
st.pyplot(fig)

# Export
st.divider()
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    buf = _save_fig_to_bytes(fig, dpi=300)
    st.download_button(
        label="💾 Download Figure (PNG, 300 DPI)",
        data=buf,
        file_name="multi_panel_figure.png",
        mime="image/png"
    )

with col2:
    buf_svg = _save_fig_to_bytes(fig, format='svg')
    st.download_button(
        label="💾 Download (SVG)",
        data=buf_svg,
        file_name="multi_panel_figure.svg",
        mime="image/svg+xml"
    )

with col3:
    st.metric("Axes", n_axes)

plt.close(fig)

# ---------------------------------------------------------------------------
# Tips
# ---------------------------------------------------------------------------

with st.expander("💡 Usage Tips"):
    st.markdown("""
    ### Creating Multi-Panel Figures

    **1. Load Data**
    - Upload or browse for multiple CSV/NPZ files
    - Each file can be plotted on one or more axes

    **2. Configure Layout**
    - Grid layout: Simple rows×columns arrangement
    - Custom positions: More flexible arrangements (future feature)

    **3. Assign Data to Axes**
    - Use tabs to configure each subplot
    - Select which datasets appear on each axis
    - Choose X/Y columns independently for each axis
    - Customize scales, labels, and legends

    **4. Export**
    - High-quality PNG (300 DPI) for presentations
    - SVG for publications and further editing

    ### Example Use Cases

    - **Compare techniques**: UV-Vis on top, SAXS on bottom
    - **Time series**: Multiple time points in grid
    - **Multi-component**: Different samples side-by-side
    - **Publication figures**: Create complex multi-panel layouts
    """)
