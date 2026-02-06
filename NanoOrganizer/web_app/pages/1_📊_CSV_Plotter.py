#!/usr/bin/env python3
"""
Enhanced CSV/NPZ Plotter - Quick visualization with per-curve styling.

Features:
- CSV, TXT, DAT, NPZ file support
- Individual color/marker selection per curve
- Smart filename display
- Multi-curve overlay
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402

import streamlit as st  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pathlib import Path  # noqa: E402
import io  # noqa: E402

# ---------------------------------------------------------------------------
# Styling options
# ---------------------------------------------------------------------------
COLORS_NAMED = {
    'Blue': '#1f77b4', 'Orange': '#ff7f0e', 'Green': '#2ca02c',
    'Red': '#d62728', 'Purple': '#9467bd', 'Brown': '#8c564b',
    'Pink': '#e377c2', 'Gray': '#7f7f7f', 'Olive': '#bcbd22',
    'Cyan': '#17becf', 'Navy': '#000080', 'Magenta': '#FF00FF',
    'Yellow': '#FFD700', 'Teal': '#008080', 'Lime': '#00FF00'
}

MARKERS_DICT = {
    'Circle': 'o', 'Square': 's', 'Triangle Up': '^', 'Triangle Down': 'v',
    'Diamond': 'D', 'Pentagon': 'p', 'Star': '*', 'Hexagon': 'h',
    'Plus': '+', 'X': 'x', 'Point': '.', 'None': 'None'
}

LINESTYLES_DICT = {
    'Solid': '-', 'Dashed': '--', 'Dash-dot': '-.', 'Dotted': ':',
    'None': 'None'
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def shorten_path(path_str, max_length=40):
    """Shorten long file paths for display."""
    if len(path_str) <= max_length:
        return path_str

    path = Path(path_str)
    filename = path.name

    if len(filename) > max_length - 3:
        return "..." + filename[-(max_length-3):]

    # Show ... parent .../filename
    parent = str(path.parent)
    if len(parent) + len(filename) + 4 > max_length:
        return ".../" + filename
    else:
        remaining = max_length - len(filename) - 4
        return parent[:remaining] + ".../" + filename


def load_data_file(file_path):
    """Load CSV, TXT, DAT, or NPZ file."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    try:
        if suffix == '.npz':
            data = np.load(file_path)
            # Convert to dataframe (assumes 1D or 2D arrays)
            df_dict = {}
            for key in data.files:
                arr = data[key]
                if arr.ndim == 1:
                    df_dict[key] = arr
                elif arr.ndim == 2:
                    # Flatten or take first column
                    df_dict[key] = arr.flatten()
            return pd.DataFrame(df_dict)
        else:
            # Try CSV/TXT with different delimiters
            df = pd.read_csv(file_path, sep=',')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep='\t')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep=r'\s+')
            return df
    except Exception as e:
        st.error(f"Error loading {path.name}: {e}")
        return None


def _save_fig_to_bytes(fig, format='png', dpi=300):
    """Save matplotlib figure to bytes buffer for download."""
    buf = io.BytesIO()
    fig.savefig(buf, format=format, dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    return buf


def browse_directory(base_dir, pattern="*.*"):
    """Browse directory and find files matching pattern."""
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    files = list(base_path.rglob(pattern))
    return [str(f) for f in sorted(files)]


# ---------------------------------------------------------------------------
# Initialize session state
# ---------------------------------------------------------------------------

if 'curve_styles' not in st.session_state:
    st.session_state['curve_styles'] = {}

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Enhanced CSV Plotter", layout="wide")
st.title("📊 Enhanced CSV/NPZ Plotter")
st.markdown("Quick visualization with per-curve styling - supports CSV, TXT, DAT, NPZ")

# ---------------------------------------------------------------------------
# Sidebar: Data Source
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 Data Source")

    data_source = st.radio(
        "Data location",
        ["Upload files", "Browse server"],
        help="Upload files from your computer or browse server filesystem"
    )

    dataframes = {}
    file_paths = {}  # Store full paths

    if data_source == "Upload files":
        uploaded_files = st.file_uploader(
            "Upload data files",
            type=['csv', 'txt', 'dat', 'npz'],
            accept_multiple_files=True,
            help="Upload CSV, TXT, DAT, or NPZ files"
        )

        if uploaded_files:
            for uploaded_file in uploaded_files:
                try:
                    # Save temporarily to load
                    temp_path = Path(f"/tmp/{uploaded_file.name}")
                    with open(temp_path, 'wb') as f:
                        f.write(uploaded_file.getbuffer())

                    df = load_data_file(str(temp_path))
                    if df is not None:
                        dataframes[uploaded_file.name] = df
                        file_paths[uploaded_file.name] = uploaded_file.name
                except Exception as e:
                    st.error(f"Error loading {uploaded_file.name}: {e}")

    else:  # Browse server
        default_dir = str(Path.cwd())
        server_dir = st.text_input("Server directory", value=default_dir)

        pattern = st.text_input("File pattern", value="*.csv",
                               help="e.g., *.csv, *.npz, data*.txt")

        if st.button("🔍 Search"):
            found_files = browse_directory(server_dir, pattern)
            st.session_state['found_files_csv'] = found_files

        if 'found_files_csv' in st.session_state and st.session_state['found_files_csv']:
            found_files = st.session_state['found_files_csv']
            if found_files:
                st.success(f"Found {len(found_files)} files")

                # Show shortened paths in selector
                file_display = {shorten_path(f, 50): f for f in found_files}

                selected_display = st.multiselect(
                    "Select files",
                    list(file_display.keys()),
                    help="Select files to plot (showing shortened paths)"
                )

                for display_name in selected_display:
                    full_path = file_display[display_name]
                    df = load_data_file(full_path)
                    if df is not None:
                        file_name = Path(full_path).name
                        dataframes[file_name] = df
                        file_paths[file_name] = full_path

    if not dataframes:
        st.info("👆 Upload or select files to get started")
        st.stop()

    st.success(f"✅ Loaded {len(dataframes)} file(s)")

    # ---------------------------------------------------------------------------
    # Column Selection
    # ---------------------------------------------------------------------------

    st.header("📐 Column Selection")

    # Get all unique column names
    all_columns = set()
    for df in dataframes.values():
        all_columns.update(df.columns)
    all_columns = sorted(list(all_columns))

    if not all_columns:
        st.error("No columns found")
        st.stop()

    # Auto-detect likely X and Y columns
    x_default = None
    y_default = None

    for col in all_columns:
        col_lower = col.lower()
        if x_default is None and any(kw in col_lower for kw in
                                     ['wavelength', 'q', 'theta', 'energy', 'time', 'x']):
            x_default = col
        if y_default is None and any(kw in col_lower for kw in
                                     ['intensity', 'absorbance', 'absorption', 'y', 'signal']):
            y_default = col

    if x_default is None and len(all_columns) > 0:
        x_default = all_columns[0]
    if y_default is None and len(all_columns) > 1:
        y_default = all_columns[1]

    x_col = st.selectbox(
        "X-axis column",
        all_columns,
        index=all_columns.index(x_default) if x_default in all_columns else 0,
        help="Select column for X-axis"
    )

    y_col = st.selectbox(
        "Y-axis column",
        all_columns,
        index=all_columns.index(y_default) if y_default in all_columns else
             (1 if len(all_columns) > 1 else 0),
        help="Select column for Y-axis"
    )

    # ---------------------------------------------------------------------------
    # Global Plot Controls
    # ---------------------------------------------------------------------------

    st.header("⚙️ Global Controls")

    # Scale
    col1, col2 = st.columns(2)
    with col1:
        x_scale = st.radio("X Scale", ["linear", "log"], horizontal=True)
    with col2:
        y_scale = st.radio("Y Scale", ["linear", "log"], horizontal=True)

    # Global style
    with st.expander("🎨 Global Style", expanded=False):
        show_grid = st.checkbox("Show grid", value=True)
        show_legend = st.checkbox("Show legend", value=True)

    # Labels
    with st.expander("📝 Labels", expanded=False):
        plot_title = st.text_input("Plot title", value="Data Comparison")
        x_label = st.text_input("X-axis label", value=x_col)
        y_label = st.text_input("Y-axis label", value=y_col)

# ---------------------------------------------------------------------------
# Main Area: Per-Curve Styling
# ---------------------------------------------------------------------------

st.header("🎨 Per-Curve Styling")

# Create expanders for each curve
curve_settings = {}

for file_name in dataframes.keys():
    with st.expander(f"🔧 {shorten_path(file_paths.get(file_name, file_name), 60)}", expanded=False):
        col1, col2, col3, col4, col5 = st.columns(5)

        # Initialize defaults if not in session state
        if file_name not in st.session_state['curve_styles']:
            idx = list(dataframes.keys()).index(file_name)
            st.session_state['curve_styles'][file_name] = {
                'color': list(COLORS_NAMED.keys())[idx % len(COLORS_NAMED)],
                'marker': list(MARKERS_DICT.keys())[idx % len(MARKERS_DICT)],
                'linestyle': 'Solid',
                'linewidth': 2.0,
                'alpha': 0.8
            }

        with col1:
            color_name = st.selectbox(
                "Color",
                list(COLORS_NAMED.keys()),
                index=list(COLORS_NAMED.keys()).index(
                    st.session_state['curve_styles'][file_name]['color']
                ),
                key=f"color_{file_name}"
            )
            curve_settings[file_name] = {'color': COLORS_NAMED[color_name]}

        with col2:
            marker_name = st.selectbox(
                "Marker",
                list(MARKERS_DICT.keys()),
                index=list(MARKERS_DICT.keys()).index(
                    st.session_state['curve_styles'][file_name]['marker']
                ),
                key=f"marker_{file_name}"
            )
            curve_settings[file_name]['marker'] = MARKERS_DICT[marker_name]

        with col3:
            linestyle_name = st.selectbox(
                "Line Style",
                list(LINESTYLES_DICT.keys()),
                index=list(LINESTYLES_DICT.keys()).index(
                    st.session_state['curve_styles'][file_name]['linestyle']
                ),
                key=f"linestyle_{file_name}"
            )
            curve_settings[file_name]['linestyle'] = LINESTYLES_DICT[linestyle_name]

        with col4:
            linewidth = st.slider(
                "Line Width",
                0.5, 5.0,
                st.session_state['curve_styles'][file_name]['linewidth'],
                0.5,
                key=f"linewidth_{file_name}"
            )
            curve_settings[file_name]['linewidth'] = linewidth

        with col5:
            alpha = st.slider(
                "Opacity",
                0.1, 1.0,
                st.session_state['curve_styles'][file_name]['alpha'],
                0.1,
                key=f"alpha_{file_name}"
            )
            curve_settings[file_name]['alpha'] = alpha

        # Update session state
        st.session_state['curve_styles'][file_name].update({
            'color': color_name,
            'marker': marker_name,
            'linestyle': linestyle_name,
            'linewidth': linewidth,
            'alpha': alpha
        })

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

st.divider()
st.header(f"📈 Plot: {y_col} vs {x_col}")

fig, ax = plt.subplots(figsize=(12, 7))

plotted_count = 0
for file_name, df in dataframes.items():
    # Check if columns exist
    if x_col not in df.columns or y_col not in df.columns:
        st.warning(f"⚠️ {file_name}: missing columns {x_col} or {y_col}")
        continue

    # Get data
    x_data = df[x_col].values
    y_data = df[y_col].values

    # Remove NaN
    mask = ~(np.isnan(x_data) | np.isnan(y_data))
    x_data = x_data[mask]
    y_data = y_data[mask]

    if len(x_data) == 0:
        st.warning(f"⚠️ {file_name}: no valid data")
        continue

    # Get styling
    style = curve_settings.get(file_name, {})

    # Plot
    marker = style.get('marker', 'None')
    marker = None if marker == 'None' else marker

    linestyle = style.get('linestyle', '-')
    linestyle = '' if linestyle == 'None' else linestyle

    ax.plot(
        x_data, y_data,
        color=style.get('color', '#1f77b4'),
        marker=marker,
        linestyle=linestyle,
        linewidth=style.get('linewidth', 2.0),
        alpha=style.get('alpha', 0.8),
        label=shorten_path(file_name, 30),
        markersize=6,
        markevery=max(1, len(x_data)//20) if marker else None
    )

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

if show_legend and len(dataframes) > 1:
    ax.legend(loc='best', framealpha=0.9, fontsize=9)

# Show plot
st.pyplot(fig)

# Export
st.divider()
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    buf = _save_fig_to_bytes(fig, dpi=300)
    st.download_button(
        label="💾 Download Plot (PNG, 300 DPI)",
        data=buf,
        file_name=f"plot_{x_col}_vs_{y_col}.png",
        mime="image/png"
    )

with col2:
    buf_svg = _save_fig_to_bytes(fig, format='svg')
    st.download_button(
        label="💾 Download (SVG)",
        data=buf_svg,
        file_name=f"plot_{x_col}_vs_{y_col}.svg",
        mime="image/svg+xml"
    )

with col3:
    st.metric("Curves", plotted_count)

plt.close(fig)

# ---------------------------------------------------------------------------
# Data Preview & Statistics
# ---------------------------------------------------------------------------

col1, col2 = st.columns(2)

with col1:
    with st.expander("📄 Data Preview"):
        for file_name, df in dataframes.items():
            st.subheader(shorten_path(file_name, 50))
            st.dataframe(df.head(10))
            st.text(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
            st.divider()

with col2:
    with st.expander("📊 Statistics"):
        for file_name, df in dataframes.items():
            if x_col in df.columns and y_col in df.columns:
                st.subheader(shorten_path(file_name, 50))
                col_a, col_b = st.columns(2)

                with col_a:
                    st.markdown(f"**{x_col}**")
                    st.text(f"Min:  {df[x_col].min():.4f}")
                    st.text(f"Max:  {df[x_col].max():.4f}")
                    st.text(f"Mean: {df[x_col].mean():.4f}")

                with col_b:
                    st.markdown(f"**{y_col}**")
                    st.text(f"Min:  {df[y_col].min():.4f}")
                    st.text(f"Max:  {df[y_col].max():.4f}")
                    st.text(f"Mean: {df[y_col].mean():.4f}")

                st.divider()
