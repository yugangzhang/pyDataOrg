#!/usr/bin/env python3
"""
Standalone CSV Plotter - Quick visualization without NanoOrganizer metadata.

Launch with:
    streamlit run NanoOrganizer/web/csv_plotter.py

Or add to setup.py as:
    'nanoorganizer-csv=NanoOrganizer.web.csv_plotter_cli:main'
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import streamlit as st  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pathlib import Path  # noqa: E402
import io  # noqa: E402

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
MARKERS = ['o', 's', '^', 'v', 'D', 'p', '*', 'h', '<', '>']
LINESTYLES = ['-', '--', '-.', ':']
COLORMAPS = ['viridis', 'plasma', 'inferno', 'magma', 'cividis',
             'turbo', 'jet', 'hot', 'cool', 'gray', 'bone']

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def load_csv_file(file_path):
    """Load CSV file, try to auto-detect delimiter."""
    try:
        # Try comma first
        df = pd.read_csv(file_path, sep=',')
        if len(df.columns) == 1:
            # Try tab
            df = pd.read_csv(file_path, sep='\t')
        if len(df.columns) == 1:
            # Try space
            df = pd.read_csv(file_path, sep=r'\s+')
        return df
    except Exception as e:
        st.error(f"Error loading {file_path}: {e}")
        return None


def _save_fig_to_bytes(fig, format='png', dpi=300):
    """Save matplotlib figure to bytes buffer for download."""
    buf = io.BytesIO()
    fig.savefig(buf, format=format, dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    return buf


def browse_directory(base_dir, pattern="*.csv"):
    """Browse directory and find CSV files."""
    base_path = Path(base_dir)
    if not base_path.exists():
        return []

    # Find all CSV files recursively
    csv_files = list(base_path.rglob(pattern))
    return [str(f) for f in sorted(csv_files)]


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="CSV Plotter", layout="wide")
st.title("📊 Standalone CSV Plotter")
st.markdown("Quick visualization of CSV files - no metadata required!")

# ---------------------------------------------------------------------------
# Sidebar: Data Source
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 Data Source")

    data_source = st.radio(
        "Data location",
        ["Upload files", "Browse server"],
        help="Upload CSVs from your computer or browse server filesystem"
    )

    csv_files = []
    dataframes = {}

    if data_source == "Upload files":
        uploaded_files = st.file_uploader(
            "Upload CSV files",
            type=['csv', 'txt', 'dat'],
            accept_multiple_files=True,
            help="Upload one or more CSV files to plot"
        )

        if uploaded_files:
            for uploaded_file in uploaded_files:
                try:
                    df = pd.read_csv(uploaded_file)
                    dataframes[uploaded_file.name] = df
                    csv_files.append(uploaded_file.name)
                except Exception as e:
                    st.error(f"Error loading {uploaded_file.name}: {e}")

    else:  # Browse server
        default_dir = str(Path.cwd())
        server_dir = st.text_input("Server directory", value=default_dir)

        pattern = st.text_input("File pattern", value="*.csv", help="e.g., *.csv, *.txt, data*.csv")

        if st.button("🔍 Search"):
            found_files = browse_directory(server_dir, pattern)
            st.session_state['found_files'] = found_files

        if 'found_files' in st.session_state and st.session_state['found_files']:
            selected_files = st.multiselect(
                "Select files",
                st.session_state['found_files'],
                help="Select files to plot"
            )

            for file_path in selected_files:
                df = load_csv_file(file_path)
                if df is not None:
                    file_name = Path(file_path).name
                    dataframes[file_name] = df
                    csv_files.append(file_name)

    if not csv_files:
        st.info("👆 Upload or select CSV files to get started")
        st.stop()

    st.success(f"✅ Loaded {len(csv_files)} file(s)")

    # ---------------------------------------------------------------------------
    # Column Selection
    # ---------------------------------------------------------------------------

    st.header("📐 Column Selection")

    # Get all unique column names from all dataframes
    all_columns = set()
    for df in dataframes.values():
        all_columns.update(df.columns)
    all_columns = sorted(list(all_columns))

    if not all_columns:
        st.error("No columns found in CSV files")
        st.stop()

    # Auto-detect likely X and Y columns
    # Look for common names
    x_default = None
    y_default = None

    for col in all_columns:
        col_lower = col.lower()
        if x_default is None and any(kw in col_lower for kw in ['wavelength', 'q', 'theta', 'energy', 'time', 'x']):
            x_default = col
        if y_default is None and any(kw in col_lower for kw in ['intensity', 'absorbance', 'absorption', 'y', 'signal']):
            y_default = col

    # If still not found, use first two columns
    if x_default is None and len(all_columns) > 0:
        x_default = all_columns[0]
    if y_default is None and len(all_columns) > 1:
        y_default = all_columns[1]

    x_col = st.selectbox(
        "X-axis column",
        all_columns,
        index=all_columns.index(x_default) if x_default in all_columns else 0,
        help="Select the column for X-axis"
    )

    y_col = st.selectbox(
        "Y-axis column",
        all_columns,
        index=all_columns.index(y_default) if y_default in all_columns else (1 if len(all_columns) > 1 else 0),
        help="Select the column for Y-axis"
    )

    # ---------------------------------------------------------------------------
    # Plot Controls
    # ---------------------------------------------------------------------------

    st.header("⚙️ Plot Controls")

    # Plot type
    plot_type = st.radio(
        "Plot type",
        ["Line plot", "Scatter plot", "Line + Scatter"],
        horizontal=True
    )

    # Scale
    col1, col2 = st.columns(2)
    with col1:
        x_scale = st.radio("X Scale", ["linear", "log"], horizontal=True)
    with col2:
        y_scale = st.radio("Y Scale", ["linear", "log"], horizontal=True)

    # Style controls
    with st.expander("🎨 Style Options", expanded=True):
        show_legend = st.checkbox("Show legend", value=True)
        show_grid = st.checkbox("Show grid", value=True)
        line_width = st.slider("Line width", 0.5, 5.0, 2.0, 0.5)
        marker_size = st.slider("Marker size", 1, 15, 6, 1)
        line_alpha = st.slider("Opacity", 0.1, 1.0, 0.8, 0.1)

    # Labels
    with st.expander("📝 Labels", expanded=False):
        plot_title = st.text_input("Plot title", value="CSV Data Comparison")
        x_label = st.text_input("X-axis label", value=x_col)
        y_label = st.text_input("Y-axis label", value=y_col)

# ---------------------------------------------------------------------------
# Main Area: Plot
# ---------------------------------------------------------------------------

st.header(f"📈 Plot: {y_col} vs {x_col}")

# Create figure
fig, ax = plt.subplots(figsize=(12, 7))

# Plot each dataset
plotted_count = 0
for idx, (file_name, df) in enumerate(dataframes.items()):
    # Check if columns exist in this dataframe
    if x_col not in df.columns or y_col not in df.columns:
        st.warning(f"⚠️ {file_name}: missing columns {x_col} or {y_col}")
        continue

    # Get data
    x_data = df[x_col].values
    y_data = df[y_col].values

    # Remove NaN values
    mask = ~(np.isnan(x_data) | np.isnan(y_data))
    x_data = x_data[mask]
    y_data = y_data[mask]

    if len(x_data) == 0:
        st.warning(f"⚠️ {file_name}: no valid data")
        continue

    # Style
    color = COLORS[idx % len(COLORS)]
    marker = MARKERS[idx % len(MARKERS)]
    linestyle = LINESTYLES[idx % len(LINESTYLES)]
    label = file_name

    # Plot based on type
    if plot_type == "Line plot":
        ax.plot(x_data, y_data, color=color, linestyle=linestyle,
                linewidth=line_width, alpha=line_alpha, label=label)
    elif plot_type == "Scatter plot":
        ax.scatter(x_data, y_data, color=color, marker=marker,
                   s=marker_size*10, alpha=line_alpha, label=label)
    else:  # Line + Scatter
        ax.plot(x_data, y_data, color=color, linestyle=linestyle,
                linewidth=line_width, alpha=line_alpha, label=label,
                marker=marker, markersize=marker_size, markevery=max(1, len(x_data)//20))

    plotted_count += 1

if plotted_count == 0:
    st.error("No data could be plotted. Check your column selections.")
    st.stop()

# Apply settings
ax.set_xscale(x_scale)
ax.set_yscale(y_scale)
ax.set_xlabel(x_label, fontsize=12)
ax.set_ylabel(y_label, fontsize=12)
ax.set_title(plot_title, fontsize=14, fontweight='bold')

if show_grid:
    ax.grid(True, alpha=0.3, linestyle='--')

if show_legend and len(csv_files) > 1:
    ax.legend(loc='best', framealpha=0.9, fontsize=9)

# Show plot
st.pyplot(fig)

# Export button
st.divider()
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    export_filename = f"csv_plot_{x_col}_vs_{y_col}.png"
    buf = _save_fig_to_bytes(fig, dpi=300)
    st.download_button(
        label="💾 Download Plot (PNG, 300 DPI)",
        data=buf,
        file_name=export_filename,
        mime="image/png"
    )

with col2:
    # Export as SVG
    buf_svg = _save_fig_to_bytes(fig, format='svg', dpi=300)
    st.download_button(
        label="💾 Download (SVG)",
        data=buf_svg,
        file_name=export_filename.replace('.png', '.svg'),
        mime="image/svg+xml"
    )

with col3:
    st.metric("Files plotted", plotted_count)

plt.close(fig)

# ---------------------------------------------------------------------------
# Data Preview
# ---------------------------------------------------------------------------

with st.expander("📄 Data Preview"):
    for file_name, df in dataframes.items():
        st.subheader(file_name)
        st.dataframe(df.head(10))
        st.text(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
        st.text(f"Columns: {', '.join(df.columns)}")
        st.divider()

# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

with st.expander("📊 Statistics"):
    for file_name, df in dataframes.items():
        if x_col in df.columns and y_col in df.columns:
            st.subheader(file_name)
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**{x_col}**")
                st.text(f"Min: {df[x_col].min():.4f}")
                st.text(f"Max: {df[x_col].max():.4f}")
                st.text(f"Mean: {df[x_col].mean():.4f}")
                st.text(f"Std: {df[x_col].std():.4f}")

            with col2:
                st.markdown(f"**{y_col}**")
                st.text(f"Min: {df[y_col].min():.4f}")
                st.text(f"Max: {df[y_col].max():.4f}")
                st.text(f"Mean: {df[y_col].mean():.4f}")
                st.text(f"Std: {df[y_col].std():.4f}")

            st.divider()
