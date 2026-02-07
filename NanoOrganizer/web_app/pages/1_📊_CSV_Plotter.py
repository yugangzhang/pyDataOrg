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
import sys  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.folder_browser import folder_browser  # noqa: E402

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

if 'dataframes_csv' not in st.session_state:
    st.session_state['dataframes_csv'] = {}

if 'file_paths_csv' not in st.session_state:
    st.session_state['file_paths_csv'] = {}

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Enhanced CSV Plotter", layout="wide")

# Add custom CSS and JavaScript for bottom sidebar toggle
st.markdown("""
<style>
.bottom-toggle-btn {
    position: fixed;
    bottom: 20px;
    left: 20px;
    z-index: 999;
    background-color: #ff4b4b;
    color: white;
    padding: 10px 18px;
    border-radius: 25px;
    font-size: 18px;
    border: none;
    box-shadow: 0 3px 10px rgba(0,0,0,0.3);
    cursor: pointer;
    transition: all 0.3s;
}
.bottom-toggle-btn:hover {
    background-color: #ff6b6b;
    transform: scale(1.1);
}
</style>

<button class="bottom-toggle-btn" onclick="
    // Find and click the Streamlit sidebar toggle button
    const toggleButton = window.parent.document.querySelector('[data-testid=\\'collapsedControl\\']');
    if (toggleButton) {
        toggleButton.click();
    } else {
        // If sidebar is open, find the close button
        const closeButton = window.parent.document.querySelector('[kind=\\'header\\'] button');
        if (closeButton) closeButton.click();
    }
">☰</button>
""", unsafe_allow_html=True)

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
                        st.session_state['dataframes_csv'][uploaded_file.name] = df
                        st.session_state['file_paths_csv'][uploaded_file.name] = uploaded_file.name
                except Exception as e:
                    st.error(f"Error loading {uploaded_file.name}: {e}")

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

        st.info("💡 Tip: Use '🔍 Advanced Filters' below for name-based filtering (contains, not contains, etc.)")

        # Use folder browser component
        selected_files = folder_browser(
            key="csv_plotter_browser",
            show_files=True,
            file_pattern=pattern,
            multi_select=True
        )

        # Load button
        if selected_files and st.button("📥 Load Selected Files", key="csv_load_btn"):
            for full_path in selected_files:
                df = load_data_file(full_path)
                if df is not None:
                    file_name = Path(full_path).name
                    st.session_state['dataframes_csv'][file_name] = df
                    st.session_state['file_paths_csv'][file_name] = full_path
                    st.success(f"✅ Loaded {file_name}")

    # Get dataframes from session state
    dataframes = st.session_state['dataframes_csv']
    file_paths = st.session_state['file_paths_csv']

    # Clear button
    if dataframes:
        if st.button("🗑️ Clear All Data", key="clear_csv_data"):
            st.session_state['dataframes_csv'] = {}
            st.session_state['file_paths_csv'] = {}
            st.session_state['curve_styles'] = {}
            st.rerun()

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

    # Auto-detect likely X column
    x_default = None
    for col in all_columns:
        col_lower = col.lower()
        if x_default is None and any(kw in col_lower for kw in
                                     ['wavelength', 'q', 'theta', 'energy', 'time', 'x']):
            x_default = col

    if x_default is None and len(all_columns) > 0:
        x_default = all_columns[0]

    x_col = st.selectbox(
        "X-axis column (common for all files)",
        all_columns,
        index=all_columns.index(x_default) if x_default in all_columns else 0,
        help="Select X-axis column - will be used for all files"
    )

    # Per-file Y column selection
    st.markdown("**Y-axis columns (per file):**")
    st.info("💡 Select multiple Y columns from each file to plot them as separate curves")

    # Store Y column selections in session state
    if 'y_column_selections' not in st.session_state:
        st.session_state['y_column_selections'] = {}

    file_y_columns = {}  # {file_name: [y_col1, y_col2, ...]}

    for file_name, df in dataframes.items():
        available_y_cols = [col for col in df.columns if col != x_col]

        if not available_y_cols:
            st.warning(f"⚠️ {file_name}: No Y columns available (only X column found)")
            continue

        # Auto-detect Y columns for first time
        if file_name not in st.session_state['y_column_selections']:
            # Default: select columns with keywords
            default_y = []
            for col in available_y_cols:
                col_lower = col.lower()
                if any(kw in col_lower for kw in ['intensity', 'absorbance', 'absorption', 'y', 'signal']):
                    default_y.append(col)

            # If no keywords match, select first available column
            if not default_y and available_y_cols:
                default_y = [available_y_cols[0]]

            st.session_state['y_column_selections'][file_name] = default_y

        selected_y_cols = st.multiselect(
            f"📄 {shorten_path(file_name, 40)}",
            available_y_cols,
            default=st.session_state['y_column_selections'][file_name],
            key=f"y_cols_{file_name}",
            help=f"Select one or more Y columns from {file_name}"
        )

        st.session_state['y_column_selections'][file_name] = selected_y_cols
        file_y_columns[file_name] = selected_y_cols

    # Check if any Y columns selected
    total_curves = sum(len(cols) for cols in file_y_columns.values())
    if total_curves == 0:
        st.error("No Y columns selected. Please select at least one Y column from any file.")
        st.stop()

    st.success(f"✅ Total curves to plot: {total_curves}")

    # ---------------------------------------------------------------------------
    # Global Plot Controls
    # ---------------------------------------------------------------------------

    st.header("⚙️ Global Controls")

    # Plot mode
    plot_mode = st.radio(
        "Plot mode",
        ["Interactive (Plotly)", "Static (Matplotlib)"],
        horizontal=True,
        help="Plotly shows values on hover! Matplotlib is static but publication-ready."
    )
    use_plotly = plot_mode.startswith("Interactive")

    # Scale
    col1, col2 = st.columns(2)
    with col1:
        x_scale = st.radio("X Scale", ["linear", "log"], horizontal=True)
    with col2:
        y_scale = st.radio("Y Scale", ["linear", "log"], horizontal=True)

    # Axis limits
    with st.expander("📏 Axis Limits", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**X-axis limits:**")
            use_xlim = st.checkbox("Set X limits", value=False)
            if use_xlim:
                xlim_min = st.number_input("X min", value=0.0, format="%.4f")
                xlim_max = st.number_input("X max", value=100.0, format="%.4f")
            else:
                xlim_min, xlim_max = None, None

        with col2:
            st.markdown("**Y-axis limits:**")
            use_ylim = st.checkbox("Set Y limits", value=False)
            if use_ylim:
                ylim_min = st.number_input("Y min", value=0.0, format="%.4f")
                ylim_max = st.number_input("Y max", value=100.0, format="%.4f")
            else:
                ylim_min, ylim_max = None, None

    # Global style
    with st.expander("🎨 Global Style", expanded=False):
        show_grid = st.checkbox("Show grid", value=True)
        show_legend = st.checkbox("Show legend", value=True)

    # Labels
    with st.expander("📝 Labels", expanded=False):
        plot_title = st.text_input("Plot title", value="Data Comparison")
        x_label = st.text_input("X-axis label", value=x_col)
        y_label = st.text_input("Y-axis label", value="Intensity")

# ---------------------------------------------------------------------------
# Main Area: Per-Curve Styling
# ---------------------------------------------------------------------------

st.header("🎨 Per-Curve Styling")

# Create expanders for each curve (file_name, y_col combination)
curve_settings = {}
curve_idx = 0

for file_name, y_cols in file_y_columns.items():
    for y_col in y_cols:
        curve_key = f"{file_name}::{y_col}"  # Unique key for each curve
        curve_label = f"{shorten_path(file_name, 30)} : {y_col}"

        with st.expander(f"🔧 {curve_label}", expanded=False):
            # Initialize defaults if not in session state
            if curve_key not in st.session_state['curve_styles']:
                st.session_state['curve_styles'][curve_key] = {
                    'color': list(COLORS_NAMED.keys())[curve_idx % len(COLORS_NAMED)],
                    'marker': list(MARKERS_DICT.keys())[curve_idx % len(MARKERS_DICT)],
                    'linestyle': 'Solid',
                    'linewidth': 2.0,
                    'alpha': 0.8,
                    'enabled': True
                }

            # Initialize curve_settings entry
            if curve_key not in curve_settings:
                curve_settings[curve_key] = {}

            # Enable/Disable checkbox
            enabled = st.checkbox(
                f"✅ Show this curve",
                value=st.session_state['curve_styles'][curve_key].get('enabled', True),
                key=f"enabled_{curve_key}",
                help="Toggle to show/hide this curve in the plot"
            )
            st.session_state['curve_styles'][curve_key]['enabled'] = enabled
            curve_settings[curve_key]['enabled'] = enabled

            if not enabled:
                st.info("⚠️ This curve is hidden. Enable to show in plot.")
                curve_idx += 1
                continue

            st.divider()
            col1, col2, col3, col4, col5 = st.columns(5)

            with col1:
                color_name = st.selectbox(
                    "Color",
                    list(COLORS_NAMED.keys()),
                    index=list(COLORS_NAMED.keys()).index(
                        st.session_state['curve_styles'][curve_key]['color']
                    ),
                    key=f"color_{curve_key}"
                )
                curve_settings[curve_key]['color'] = COLORS_NAMED[color_name]

            with col2:
                marker_name = st.selectbox(
                    "Marker",
                    list(MARKERS_DICT.keys()),
                    index=list(MARKERS_DICT.keys()).index(
                        st.session_state['curve_styles'][curve_key]['marker']
                    ),
                    key=f"marker_{curve_key}"
                )
                curve_settings[curve_key]['marker'] = MARKERS_DICT[marker_name]

            with col3:
                linestyle_name = st.selectbox(
                    "Line Style",
                    list(LINESTYLES_DICT.keys()),
                    index=list(LINESTYLES_DICT.keys()).index(
                        st.session_state['curve_styles'][curve_key]['linestyle']
                    ),
                    key=f"linestyle_{curve_key}"
                )
                curve_settings[curve_key]['linestyle'] = LINESTYLES_DICT[linestyle_name]

            with col4:
                linewidth = st.slider(
                    "Line Width",
                    0.5, 5.0,
                    st.session_state['curve_styles'][curve_key]['linewidth'],
                    0.5,
                    key=f"linewidth_{curve_key}"
                )
                curve_settings[curve_key]['linewidth'] = linewidth

            with col5:
                alpha = st.slider(
                    "Opacity",
                    0.1, 1.0,
                    st.session_state['curve_styles'][curve_key]['alpha'],
                    0.1,
                    key=f"alpha_{curve_key}"
                )
                curve_settings[curve_key]['alpha'] = alpha

            # Update session state
            st.session_state['curve_styles'][curve_key].update({
                'color': color_name,
                'marker': marker_name,
                'linestyle': linestyle_name,
                'linewidth': linewidth,
                'alpha': alpha
            })

        curve_idx += 1

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

st.divider()
st.header(f"📈 Plot: {y_col} vs {x_col}")

if use_plotly:
    # -------------------------------------------------------------------------
    # Plotly Interactive Plot (with hover!)
    # -------------------------------------------------------------------------
    fig = go.Figure()

    plotted_count = 0
    for file_name, y_cols in file_y_columns.items():
        df = dataframes[file_name]

        for y_col in y_cols:
            curve_key = f"{file_name}::{y_col}"

            # Check if enabled
            if not curve_settings.get(curve_key, {}).get('enabled', True):
                continue

            # Check if columns exist
            if x_col not in df.columns or y_col not in df.columns:
                st.warning(f"⚠️ {file_name}, {y_col}: missing columns")
                continue

            # Get data
            x_data = df[x_col].values
            y_data = df[y_col].values

            # Remove NaN
            mask = ~(np.isnan(x_data) | np.isnan(y_data))
            x_data = x_data[mask]
            y_data = y_data[mask]

            if len(x_data) == 0:
                st.warning(f"⚠️ {file_name}, {y_col}: no valid data")
                continue

            # Get styling
            style = curve_settings.get(curve_key, {})

        # Map matplotlib markers to plotly symbols
        marker_map = {
            'o': 'circle', 's': 'square', '^': 'triangle-up', 'v': 'triangle-down',
            'D': 'diamond', 'p': 'pentagon', '*': 'star', 'h': 'hexagon',
            '+': 'cross', 'x': 'x', '.': 'circle', 'None': None
        }

        # Map matplotlib linestyles to plotly dash
        linestyle_map = {
            '-': 'solid', '--': 'dash', '-.': 'dashdot', ':': 'dot', 'None': None
        }

        marker_style = marker_map.get(style.get('marker', 'o'), 'circle')
        line_dash = linestyle_map.get(style.get('linestyle', '-'), 'solid')

        # Determine mode
        if marker_style and line_dash:
            mode = 'lines+markers'
        elif marker_style:
            mode = 'markers'
        elif line_dash:
            mode = 'lines'
        else:
            mode = 'lines'

        # Add trace
        trace_name = f"{shorten_path(file_name, 20)}: {y_col}"
        fig.add_trace(go.Scatter(
            x=x_data,
            y=y_data,
            mode=mode,
            name=trace_name,
            line=dict(
                color=style.get('color', '#1f77b4'),
                width=style.get('linewidth', 2.0),
                dash=line_dash if line_dash else 'solid'
            ),
            marker=dict(
                symbol=marker_style if marker_style else 'circle',
                size=8,
                color=style.get('color', '#1f77b4')
            ),
            opacity=style.get('alpha', 0.8),
            hovertemplate=f'<b>{x_col}</b>: %{{x:.4f}}<br><b>{y_col}</b>: %{{y:.4f}}<extra></extra>'
        ))

        plotted_count += 1

    if plotted_count == 0:
        st.error("No curves enabled. Enable curves in Per-Curve Styling section.")
        st.stop()

    # Apply settings
    fig.update_xaxes(
        title=x_label,
        type='log' if x_scale == 'log' else 'linear',
        range=[np.log10(xlim_min) if x_scale == 'log' and use_xlim and xlim_min > 0 else xlim_min,
               np.log10(xlim_max) if x_scale == 'log' and use_xlim else xlim_max] if use_xlim else None,
        showgrid=show_grid,
        gridcolor='lightgray',
        gridwidth=0.5
    )

    fig.update_yaxes(
        title=y_label,
        type='log' if y_scale == 'log' else 'linear',
        range=[np.log10(ylim_min) if y_scale == 'log' and use_ylim and ylim_min > 0 else ylim_min,
               np.log10(ylim_max) if y_scale == 'log' and use_ylim else ylim_max] if use_ylim else None,
        showgrid=show_grid,
        gridcolor='lightgray',
        gridwidth=0.5
    )

    fig.update_layout(
        title=plot_title,
        height=600,
        hovermode='closest',
        showlegend=show_legend,
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02)
    )

    # Show plot
    st.plotly_chart(fig, use_container_width=True)
    st.success(f"✅ {plotted_count} curve(s) plotted. **Hover over curves to see (x,y) values!**")

else:
    # -------------------------------------------------------------------------
    # Matplotlib Static Plot
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 7))

    plotted_count = 0
    for file_name, y_cols in file_y_columns.items():
        df = dataframes[file_name]

        for y_col in y_cols:
            curve_key = f"{file_name}::{y_col}"

            # Check if enabled
            if not curve_settings.get(curve_key, {}).get('enabled', True):
                continue

            # Check if columns exist
            if x_col not in df.columns or y_col not in df.columns:
                st.warning(f"⚠️ {file_name}, {y_col}: missing columns")
                continue

            # Get data
            x_data = df[x_col].values
            y_data = df[y_col].values

            # Remove NaN
            mask = ~(np.isnan(x_data) | np.isnan(y_data))
            x_data = x_data[mask]
            y_data = y_data[mask]

            if len(x_data) == 0:
                st.warning(f"⚠️ {file_name}, {y_col}: no valid data")
                continue

            # Get styling
            style = curve_settings.get(curve_key, {})

            # Plot
            marker = style.get('marker', 'None')
            marker = None if marker == 'None' else marker

            linestyle = style.get('linestyle', '-')
            linestyle = '' if linestyle == 'None' else linestyle

            trace_label = f"{shorten_path(file_name, 20)}: {y_col}"

            ax.plot(
                x_data, y_data,
                color=style.get('color', '#1f77b4'),
                marker=marker,
                linestyle=linestyle,
                linewidth=style.get('linewidth', 2.0),
                alpha=style.get('alpha', 0.8),
                label=trace_label,
                markersize=6,
                markevery=max(1, len(x_data)//20) if marker else None
            )

            plotted_count += 1

    if plotted_count == 0:
        st.error("No curves enabled. Enable curves in Per-Curve Styling section.")
        st.stop()

    # Apply settings
    ax.set_xscale(x_scale)
    ax.set_yscale(y_scale)
    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel(y_label, fontsize=12)
    ax.set_title(plot_title, fontsize=14, fontweight='bold')

    # Set axis limits
    if use_xlim:
        ax.set_xlim(xlim_min, xlim_max)
    if use_ylim:
        ax.set_ylim(ylim_min, ylim_max)

    if show_grid:
        ax.grid(True, alpha=0.3, linestyle='--')

    if show_legend and len(dataframes) > 1:
        ax.legend(loc='best', framealpha=0.9, fontsize=9)

    # Show plot
    st.pyplot(fig)
    st.info(f"✅ {plotted_count} curve(s) plotted. Switch to 'Interactive (Plotly)' mode to see hover values!")

# Export
st.divider()

if use_plotly:
    # Plotly export
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        html_buffer = io.StringIO()
        fig.write_html(html_buffer)
        html_bytes = html_buffer.getvalue().encode()
        st.download_button(
            label="💾 Download HTML",
            data=html_bytes,
            file_name=f"plot_{x_col}_vs_{y_col}.html",
            mime="text/html",
            help="Interactive plot - preserves hover functionality!"
        )

    with col2:
        try:
            img_bytes = fig.to_image(format="png", width=1200, height=800)
            st.download_button(
                label="💾 Download PNG",
                data=img_bytes,
                file_name=f"plot_{x_col}_vs_{y_col}.png",
                mime="image/png"
            )
        except:
            st.info("Install kaleido for PNG export")

    with col3:
        try:
            img_bytes = fig.to_image(format="svg")
            st.download_button(
                label="💾 Download SVG",
                data=img_bytes,
                file_name=f"plot_{x_col}_vs_{y_col}.svg",
                mime="image/svg+xml"
            )
        except:
            st.info("Install kaleido for SVG export")

    with col4:
        st.metric("Curves", plotted_count)

else:
    # Matplotlib export
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
