#!/usr/bin/env python3
"""
Universal Plotter - Integrated plotting for 1D, 2D, and 3D data.

Features:
- Create custom grid layouts with mixed plot types
- 1D: Full per-curve styling (color, marker, line style, width, opacity)
- 2D: Heatmap with colormap, log scale, contrast/percentile controls
- 3D: Surface, Scatter 3D, Contour 3D, Wireframe, Mesh with full options
- Interactive hover, zoom, pan (Plotly)
- Export: interactive HTML, PNG, SVG
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.interpolate import griddata
import io
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.folder_browser import folder_browser
from components.floating_button import floating_sidebar_toggle

# User-mode restriction (set by nanoorganizer_user)
_user_mode = st.session_state.get("user_mode", False)
_start_dir = st.session_state.get("user_start_dir", None)

# ---------------------------------------------------------------------------
# Constants (matching individual pages)
# ---------------------------------------------------------------------------

# 1D styling: colors (from CSV Plotter)
COLORS_NAMED = {
    'Blue': '#1f77b4', 'Orange': '#ff7f0e', 'Green': '#2ca02c',
    'Red': '#d62728', 'Purple': '#9467bd', 'Brown': '#8c564b',
    'Pink': '#e377c2', 'Gray': '#7f7f7f', 'Olive': '#bcbd22',
    'Cyan': '#17becf', 'Navy': '#000080', 'Magenta': '#FF00FF',
    'Yellow': '#FFD700', 'Teal': '#008080', 'Lime': '#00FF00',
}
COLOR_NAMES = list(COLORS_NAMED.keys())

# 1D styling: markers (matplotlib name -> Plotly symbol)
MARKERS_DICT = {
    'Circle': 'o', 'Square': 's', 'Triangle Up': '^', 'Triangle Down': 'v',
    'Diamond': 'D', 'Pentagon': 'p', 'Star': '*', 'Hexagon': 'h',
    'Plus': '+', 'X': 'x', 'Point': '.', 'None': 'None',
}
MARKER_NAMES = list(MARKERS_DICT.keys())

MPL_TO_PLOTLY_MARKER = {
    'o': 'circle', 's': 'square', '^': 'triangle-up', 'v': 'triangle-down',
    'D': 'diamond', 'p': 'pentagon', '*': 'star', 'h': 'hexagon',
    '+': 'cross', 'x': 'x', '.': 'circle', 'None': None,
}

# 1D styling: line styles (matplotlib name -> Plotly dash)
LINESTYLES_DICT = {
    'Solid': '-', 'Dashed': '--', 'Dash-dot': '-.', 'Dotted': ':',
    'None': 'None',
}
LINESTYLE_NAMES = list(LINESTYLES_DICT.keys())

MPL_TO_PLOTLY_DASH = {
    '-': 'solid', '--': 'dash', '-.': 'dashdot', ':': 'dot', 'None': None,
}

# 2D colormaps (from Image Viewer)
COLORMAPS_2D = [
    'viridis', 'plasma', 'inferno', 'magma', 'cividis',
    'turbo', 'jet', 'hot', 'cool', 'gray', 'bone', 'seismic',
    'RdYlBu', 'RdBu', 'coolwarm',
]

# Matplotlib colormap -> Plotly colorscale name
_PLOTLY_CMAP = {
    'viridis': 'Viridis', 'plasma': 'Plasma', 'inferno': 'Inferno',
    'magma': 'Magma', 'cividis': 'Cividis', 'turbo': 'Turbo',
    'jet': 'Jet', 'hot': 'Hot', 'cool': 'ice', 'gray': 'Greys',
    'bone': 'Greys', 'seismic': 'RdBu', 'RdYlBu': 'RdYlBu',
    'RdBu': 'RdBu', 'coolwarm': 'RdBu',
}

# 3D colorscales (from 3D Plotter)
COLORSCALES_3D = [
    'Viridis', 'Plasma', 'Inferno', 'Magma', 'Cividis',
    'Turbo', 'Rainbow', 'Jet', 'Hot', 'Cool',
    'Portland', 'Electric', 'Picnic', 'RdBu', 'Earth',
]

# 3D plot types (from 3D Plotter)
PLOT_TYPES_3D = ['Surface', 'Scatter 3D', 'Contour 3D', 'Wireframe', 'Mesh']

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def make_subplot_colorbar(fig, row, col_i, n_rows, n_cols, title):
    """Build a colorbar dict positioned next to a specific XY subplot."""
    try:
        ref = fig.get_subplot(row, col_i)
        if ref is None:
            return dict(title=title)
        xaxis_obj = ref.xaxis
        yaxis_obj = ref.yaxis
        xaxis_key = xaxis_obj.plotly_name
        yaxis_key = yaxis_obj.plotly_name
        x_domain = list(getattr(fig.layout, xaxis_key).domain)
        y_domain = list(getattr(fig.layout, yaxis_key).domain)
        return dict(
            title=title,
            x=x_domain[1] + 0.01,
            xanchor='left',
            y=(y_domain[0] + y_domain[1]) / 2,
            yanchor='middle',
            len=max(0.15, y_domain[1] - y_domain[0]),
            thickness=15,
        )
    except Exception:
        return dict(title=title)


def fix_3d_colorbar(fig, title):
    """Update the last added 3D trace's colorbar to sit next to its scene.

    Must be called right after fig.add_trace() for a 3D trace.
    Reads the scene ref from fig.data[-1], gets the scene domain,
    and patches the colorbar position.
    """
    try:
        last = fig.data[-1]
        scene_ref = getattr(last, 'scene', None) or 'scene'
        scene_obj = getattr(fig.layout, scene_ref)
        x_domain = list(scene_obj.domain.x)
        y_domain = list(scene_obj.domain.y)
        cbar = dict(
            title=title,
            x=x_domain[1] + 0.01,
            xanchor='left',
            y=(y_domain[0] + y_domain[1]) / 2,
            yanchor='middle',
            len=max(0.15, y_domain[1] - y_domain[0]),
            thickness=15,
        )
        # Patch colorbar onto the trace (or its marker)
        if hasattr(last, 'colorbar'):
            last.colorbar = cbar
        elif hasattr(last, 'marker') and last.marker is not None:
            last.marker.colorbar = cbar
    except Exception:
        pass


def load_data_file(file_path):
    """Load CSV, TXT, DAT, NPZ, or NPY file as DataFrame."""
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
        elif suffix == '.npy':
            arr = np.load(file_path)
            if arr.ndim == 1:
                return pd.DataFrame({'data': arr})
            elif arr.ndim == 2:
                return pd.DataFrame(arr)
            return None
        else:
            df = pd.read_csv(file_path, sep=',')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep='\t')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep=r'\s+')
            return df
    except Exception as e:
        st.error(f"Error loading {path.name}: {e}")
        return None


def load_image(file_path):
    """Load 2D image array from NPY/NPZ/PNG/TIF."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    try:
        if suffix == '.npy':
            return np.load(file_path)
        elif suffix == '.npz':
            data = np.load(file_path)
            return data[data.files[0]]
        elif suffix in ['.png', '.jpg', '.jpeg', '.tif', '.tiff']:
            from PIL import Image
            img = Image.open(file_path)
            return np.array(img, dtype=np.float64)
        else:
            return None
    except Exception as e:
        st.error(f"Error loading image {path.name}: {e}")
        return None


def prepare_display_data(img, use_log):
    """Apply log10 transform if requested."""
    if not use_log:
        return img.astype(np.float64), ""
    floor_val = np.min(img[img > 0]) if np.any(img > 0) else 1e-10
    clipped = np.clip(img.astype(np.float64), floor_val, None)
    return np.log10(clipped), " (log10)"


def calc_intensity_range(img, auto_contrast, vmin_pct, vmax_pct):
    """Calculate vmin/vmax from percentiles."""
    if auto_contrast:
        return np.nanpercentile(img, [1, 99])
    return np.nanpercentile(img, vmin_pct), np.nanpercentile(img, vmax_pct)


def create_meshgrid_from_data(x, y, z, grid_size=100):
    """Create meshgrid from scattered or gridded data."""
    unique_x = np.unique(x)
    unique_y = np.unique(y)

    if len(unique_x) * len(unique_y) == len(z):
        X, Y = np.meshgrid(unique_x, unique_y)
        Z = z.reshape(len(unique_y), len(unique_x))
    else:
        X, Y = np.meshgrid(
            np.linspace(x.min(), x.max(), grid_size),
            np.linspace(y.min(), y.max(), grid_size),
        )
        Z = griddata((x, y), z, (X, Y), method='cubic')

    return X, Y, Z


def generate_synthetic_data(func_type, points=100):
    """Generate synthetic data for testing."""
    if func_type == "1D - Sine wave":
        x = np.linspace(0, 4 * np.pi, points)
        y = np.sin(x) + 0.1 * np.random.randn(points)
        return pd.DataFrame({'x': x, 'y': y})
    elif func_type == "1D - Gaussian":
        x = np.linspace(-5, 5, points)
        y = np.exp(-x ** 2) + 0.05 * np.random.randn(points)
        return pd.DataFrame({'x': x, 'y': y})
    elif func_type == "2D - Heatmap":
        n = int(np.sqrt(points))
        x = np.linspace(-3, 3, n)
        y = np.linspace(-3, 3, n)
        X, Y = np.meshgrid(x, y)
        Z = np.exp(-(X ** 2 + Y ** 2))
        return pd.DataFrame({'x': X.flatten(), 'y': Y.flatten(), 'z': Z.flatten()})
    elif func_type == "3D - Surface":
        n = int(np.sqrt(points))
        x = np.linspace(-5, 5, n)
        y = np.linspace(-5, 5, n)
        X, Y = np.meshgrid(x, y)
        Z = np.sin(np.sqrt(X ** 2 + Y ** 2))
        H = np.cos(np.sqrt(X ** 2 + Y ** 2))
        return pd.DataFrame({
            'x': X.flatten(), 'y': Y.flatten(),
            'z': Z.flatten(), 'color': H.flatten(),
        })
    return None


def shorten_path(path_str, max_length=40):
    """Shorten long file paths for display."""
    if len(path_str) <= max_length:
        return path_str
    path = Path(path_str)
    filename = path.name
    if len(filename) > max_length - 3:
        return "..." + filename[-(max_length - 3):]
    return ".../" + filename


# ---------------------------------------------------------------------------
# Initialize session state
# ---------------------------------------------------------------------------

if 'univ_loaded_data' not in st.session_state:
    st.session_state['univ_loaded_data'] = {}

if 'univ_loaded_images' not in st.session_state:
    st.session_state['univ_loaded_images'] = {}

if 'univ_curve_styles' not in st.session_state:
    st.session_state['univ_curve_styles'] = {}

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.title("🎯 Universal Plotter")
st.markdown("**Create integrated figures with 1D, 2D, and 3D plots — all interactive with hover values!**")

floating_sidebar_toggle()

# ---------------------------------------------------------------------------
# Sidebar: Layout & Data Loading
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📐 Layout Configuration")

    layout_type = st.selectbox(
        "Figure layout",
        ["1×1 (Single)", "1×2 (Horizontal)", "2×1 (Vertical)",
         "2×2 (Grid)", "1×3", "3×1", "2×3", "Custom"],
        help="Choose subplot grid arrangement",
    )

    if layout_type == "Custom":
        n_rows = st.number_input("Rows", min_value=1, max_value=5, value=2)
        n_cols = st.number_input("Columns", min_value=1, max_value=5, value=2)
    else:
        layout_map = {
            "1×1 (Single)": (1, 1), "1×2 (Horizontal)": (1, 2),
            "2×1 (Vertical)": (2, 1), "2×2 (Grid)": (2, 2),
            "1×3": (1, 3), "3×1": (3, 1), "2×3": (2, 3),
        }
        n_rows, n_cols = layout_map[layout_type]

    total_subplots = n_rows * n_cols

    st.divider()
    st.header("📁 Data Loading")

    data_source = st.radio(
        "Data source",
        ["Upload files", "Browse server", "Generate synthetic"],
        help="Load data from file or generate test data",
    )

    if data_source == "Upload files":
        uploaded_files = st.file_uploader(
            "Upload data files",
            type=['csv', 'txt', 'dat', 'npz', 'npy', 'png', 'tif', 'tiff', 'jpg'],
            accept_multiple_files=True,
        )
        if uploaded_files:
            for uploaded_file in uploaded_files:
                try:
                    temp_path = Path(f"/tmp/{uploaded_file.name}")
                    with open(temp_path, 'wb') as f:
                        f.write(uploaded_file.getbuffer())

                    suffix = temp_path.suffix.lower()
                    if suffix in ['.png', '.tif', '.tiff', '.jpg', '.jpeg']:
                        img = load_image(str(temp_path))
                        if img is not None:
                            st.session_state['univ_loaded_images'][uploaded_file.name] = img
                    elif suffix == '.npy':
                        arr = np.load(str(temp_path))
                        if arr.ndim == 2:
                            st.session_state['univ_loaded_images'][uploaded_file.name] = arr
                        else:
                            df = load_data_file(str(temp_path))
                            if df is not None:
                                st.session_state['univ_loaded_data'][uploaded_file.name] = df
                    else:
                        df = load_data_file(str(temp_path))
                        if df is not None:
                            st.session_state['univ_loaded_data'][uploaded_file.name] = df
                except Exception as e:
                    st.error(f"Error loading {uploaded_file.name}: {e}")

    elif data_source == "Browse server":
        st.markdown("**🗂️ Interactive Folder Browser**")

        pattern = st.selectbox(
            "File type",
            ["*.*", "*.csv", "*.npz", "*.npy", "*.txt", "*.dat",
             "*.png", "*.tif", "*.tiff", "*.jpg"],
            index=0,
        )

        selected_files = folder_browser(
            key="universal_plotter_browser",
            show_files=True,
            file_pattern=pattern,
            multi_select=True,
            initial_path=_start_dir if _user_mode else None,
            restrict_to_start_dir=_user_mode,
        )

        if selected_files and st.button("📥 Load Selected Files"):
            for file_path in selected_files:
                suffix = Path(file_path).suffix.lower()
                file_name = Path(file_path).name

                if suffix in ['.png', '.tif', '.tiff', '.jpg', '.jpeg']:
                    img = load_image(file_path)
                    if img is not None:
                        st.session_state['univ_loaded_images'][file_name] = img
                        st.success(f"✅ Loaded image {file_name}")
                elif suffix == '.npy':
                    arr = np.load(file_path)
                    if arr.ndim == 2:
                        st.session_state['univ_loaded_images'][file_name] = arr
                        st.success(f"✅ Loaded image {file_name}")
                    else:
                        df = load_data_file(file_path)
                        if df is not None:
                            st.session_state['univ_loaded_data'][file_name] = df
                            st.success(f"✅ Loaded {file_name}")
                else:
                    df = load_data_file(file_path)
                    if df is not None:
                        st.session_state['univ_loaded_data'][file_name] = df
                        st.success(f"✅ Loaded {file_name}")

    else:  # Generate synthetic
        st.markdown("**Quick test data:**")
        if st.button("🎲 Generate 1D Sine"):
            st.session_state['univ_loaded_data']['Sine Wave'] = generate_synthetic_data("1D - Sine wave")
        if st.button("🎲 Generate 1D Gaussian"):
            st.session_state['univ_loaded_data']['Gaussian'] = generate_synthetic_data("1D - Gaussian")
        if st.button("🎲 Generate 2D Heatmap"):
            st.session_state['univ_loaded_data']['2D Heatmap'] = generate_synthetic_data("2D - Heatmap")
        if st.button("🎲 Generate 3D Surface"):
            st.session_state['univ_loaded_data']['3D Surface'] = generate_synthetic_data("3D - Surface")

    # Quick-load TestData button (always visible)
    st.divider()
    _test_data_dir = None
    for _candidate in [
        Path(__file__).resolve().parent.parent.parent.parent / "TestData",
        Path.cwd() / "TestData",
    ]:
        if _candidate.is_dir():
            _test_data_dir = _candidate
            break

    if _test_data_dir is not None:
        if st.button("🧪 Load Test Data", help=f"One-click load from {_test_data_dir}"):
            _loaded_count = 0
            # 1D CSV files (3 spectra from different samples)
            for _csv_name in [
                "sample_01_t0000.0s.csv",
                "sample_02_t0000.0s.csv",
                "sample_03_t0000.0s.csv",
            ]:
                _csv_path = _test_data_dir / "csv_data" / _csv_name
                if _csv_path.exists():
                    _df = load_data_file(str(_csv_path))
                    if _df is not None:
                        st.session_state['univ_loaded_data'][_csv_name] = _df
                        _loaded_count += 1

            # 1D multi-column file
            _oned_path = _test_data_dir / "OneD" / "Oned_4cols.txt"
            if _oned_path.exists():
                _df = load_data_file(str(_oned_path))
                if _df is not None:
                    st.session_state['univ_loaded_data']['Oned_4cols.txt'] = _df
                    _loaded_count += 1

            # 2D detector image
            _img_path = _test_data_dir / "images_2d" / "detector_01.npy"
            if _img_path.exists():
                _arr = np.load(str(_img_path))
                if _arr.ndim == 2:
                    st.session_state['univ_loaded_images']['detector_01.npy'] = _arr
                    _loaded_count += 1

            # 3D surface CSV
            _3d_path = _test_data_dir / "data_3d" / "gaussian_3d.csv"
            if _3d_path.exists():
                _df = load_data_file(str(_3d_path))
                if _df is not None:
                    st.session_state['univ_loaded_data']['gaussian_3d.csv'] = _df
                    _loaded_count += 1

            st.success(f"✅ Loaded {_loaded_count} test datasets")
            st.rerun()

    has_data = bool(st.session_state['univ_loaded_data']) or bool(st.session_state['univ_loaded_images'])
    if has_data:
        n_tab = len(st.session_state['univ_loaded_data'])
        n_img = len(st.session_state['univ_loaded_images'])
        parts = []
        if n_tab:
            parts.append(f"{n_tab} tabular")
        if n_img:
            parts.append(f"{n_img} image")
        st.success(f"✅ {' + '.join(parts)} dataset(s) loaded")
        if st.button("🗑️ Clear all data"):
            st.session_state['univ_loaded_data'] = {}
            st.session_state['univ_loaded_images'] = {}
            st.session_state['univ_curve_styles'] = {}
            st.rerun()

# ---------------------------------------------------------------------------
# Main Area: Subplot Configuration
# ---------------------------------------------------------------------------

has_data = bool(st.session_state['univ_loaded_data']) or bool(st.session_state['univ_loaded_images'])
if not has_data:
    st.info("👆 Load or generate data first using the sidebar")
    st.stop()

data_names = list(st.session_state['univ_loaded_data'].keys())
image_names = list(st.session_state['univ_loaded_images'].keys())

st.header(f"⚙️ Configure {n_rows}×{n_cols} Layout ({total_subplots} subplot{'s' if total_subplots > 1 else ''})")

subplot_tabs = st.tabs([f"Subplot {i + 1}" for i in range(total_subplots)])

subplot_configs = []

for subplot_idx, tab in enumerate(subplot_tabs):
    with tab:
        enabled = st.checkbox(
            "Enable this subplot",
            value=(subplot_idx == 0),
            key=f"univ_enable_{subplot_idx}",
        )

        if not enabled:
            st.info("This subplot is empty. Enable it to configure.")
            subplot_configs.append({'enabled': False})
            continue

        # Plot category selection
        plot_category = st.radio(
            "Plot category",
            ["1D Plot", "2D Image/Heatmap", "3D Plot"],
            horizontal=True,
            key=f"univ_cat_{subplot_idx}",
        )

        config = {'enabled': True, 'category': plot_category}

        # =================================================================
        # 1D PLOT CONFIGURATION (from CSV Plotter) — multi-dataset layers
        # =================================================================
        if plot_category == "1D Plot":
            if not data_names:
                st.warning("No tabular data loaded. Load CSV/NPZ/TXT files first.")
                subplot_configs.append({'enabled': False})
                continue

            # --- Layer count via Add/Remove buttons ---
            layer_count_key = f"univ_nlayers_{subplot_idx}"
            if layer_count_key not in st.session_state:
                st.session_state[layer_count_key] = 1
            n_layers = st.session_state[layer_count_key]

            btn_c1, btn_c2, btn_c3 = st.columns([3, 1, 1])
            with btn_c1:
                st.markdown(f"**Datasets: {n_layers}** — overlay multiple files")
            with btn_c2:
                if st.button("➕ Add", key=f"univ_addlayer_{subplot_idx}"):
                    st.session_state[layer_count_key] = min(n_layers + 1, 10)
                    st.rerun()
            with btn_c3:
                if n_layers > 1 and st.button("➖ Remove", key=f"univ_rmlayer_{subplot_idx}"):
                    st.session_state[layer_count_key] = n_layers - 1
                    st.rerun()

            layers = []
            global_curve_idx = 0

            for layer_idx in range(n_layers):
                # Visual separator between layers
                if layer_idx > 0:
                    st.divider()
                if n_layers > 1:
                    st.markdown(f"**📂 Dataset {layer_idx + 1}**")

                # Default to different datasets for different layers
                default_data_idx = min(layer_idx, len(data_names) - 1)

                data_name = st.selectbox(
                    "File" if n_layers == 1 else f"File (layer {layer_idx + 1})",
                    data_names,
                    index=default_data_idx,
                    key=f"univ_data_1d_{subplot_idx}_L{layer_idx}",
                )
                df = st.session_state['univ_loaded_data'][data_name]
                columns = list(df.columns)

                lc1, lc2 = st.columns(2)
                with lc1:
                    x_col = st.selectbox("X column", columns,
                                         key=f"univ_xcol_{subplot_idx}_L{layer_idx}")
                with lc2:
                    available_y = [c for c in columns if c != x_col]
                    y_cols = st.multiselect(
                        "Y column(s)",
                        available_y,
                        default=[available_y[0]] if available_y else [],
                        key=f"univ_ycols_{subplot_idx}_L{layer_idx}",
                        help="Each Y column creates a separate curve",
                    )

                # Per-curve styling for this layer
                curve_styles = {}
                if y_cols:
                    with st.expander("🎨 Curve Styling", expanded=False):
                        for cidx, yc in enumerate(y_cols):
                            style_key = f"univ_{subplot_idx}::L{layer_idx}::{data_name}::{yc}"
                            color_idx = (global_curve_idx + cidx) % len(COLOR_NAMES)

                            if style_key not in st.session_state['univ_curve_styles']:
                                st.session_state['univ_curve_styles'][style_key] = {
                                    'color': COLOR_NAMES[color_idx],
                                    'marker': 'None',
                                    'linestyle': 'Solid',
                                    'linewidth': 2.0,
                                    'opacity': 0.9,
                                    'enabled': True,
                                }

                            defaults = st.session_state['univ_curve_styles'][style_key]

                            st.markdown(f"**{data_name} → {yc}**")
                            sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)

                            with sc1:
                                s_enabled = st.checkbox("Show", value=defaults['enabled'],
                                                        key=f"univ_en_{style_key}")
                            with sc2:
                                s_color = st.selectbox("Color", COLOR_NAMES,
                                                       index=COLOR_NAMES.index(defaults['color']),
                                                       key=f"univ_col_{style_key}")
                            with sc3:
                                s_marker = st.selectbox("Marker", MARKER_NAMES,
                                                        index=MARKER_NAMES.index(defaults['marker']),
                                                        key=f"univ_mk_{style_key}")
                            with sc4:
                                s_line = st.selectbox("Line", LINESTYLE_NAMES,
                                                      index=LINESTYLE_NAMES.index(defaults['linestyle']),
                                                      key=f"univ_ls_{style_key}")
                            with sc5:
                                s_width = st.slider("Width", 0.5, 5.0, defaults['linewidth'], 0.5,
                                                    key=f"univ_lw_{style_key}")
                            with sc6:
                                s_alpha = st.slider("Opacity", 0.1, 1.0, defaults['opacity'], 0.1,
                                                    key=f"univ_op_{style_key}")

                            st.session_state['univ_curve_styles'][style_key] = {
                                'color': s_color, 'marker': s_marker,
                                'linestyle': s_line, 'linewidth': s_width,
                                'opacity': s_alpha, 'enabled': s_enabled,
                            }

                            curve_styles[yc] = {
                                'enabled': s_enabled,
                                'color': COLORS_NAMED[s_color],
                                'marker_plotly': MPL_TO_PLOTLY_MARKER.get(MARKERS_DICT[s_marker]),
                                'dash': MPL_TO_PLOTLY_DASH.get(LINESTYLES_DICT[s_line]),
                                'linewidth': s_width,
                                'opacity': s_alpha,
                            }

                            if cidx < len(y_cols) - 1:
                                st.divider()

                global_curve_idx += max(len(y_cols), 1)

                layers.append({
                    'data_name': data_name,
                    'df': df,
                    'x_col': x_col,
                    'y_cols': y_cols,
                    'curve_styles': curve_styles,
                })

            # Shared subplot settings (all layers share these)
            col_left, col_right = st.columns(2)
            with col_left:
                c1, c2 = st.columns(2)
                with c1:
                    x_scale = st.radio("X scale", ["linear", "log"],
                                       horizontal=True, key=f"univ_xscale_{subplot_idx}")
                with c2:
                    y_scale = st.radio("Y scale", ["linear", "log"],
                                       horizontal=True, key=f"univ_yscale_{subplot_idx}")
            with col_right:
                show_grid = st.checkbox("Show grid", value=True,
                                        key=f"univ_grid_{subplot_idx}")
                show_legend = st.checkbox("Show legend", value=True,
                                          key=f"univ_legend_{subplot_idx}")

            # Axis limits
            with st.expander("📏 Axis Limits", expanded=False):
                lc1, lc2 = st.columns(2)
                with lc1:
                    use_xlim = st.checkbox("Set X limits", value=False,
                                           key=f"univ_usexlim_{subplot_idx}")
                    if use_xlim:
                        xlim_min = st.number_input("X min", value=0.0, format="%.4f",
                                                   key=f"univ_xmin_{subplot_idx}")
                        xlim_max = st.number_input("X max", value=100.0, format="%.4f",
                                                   key=f"univ_xmax_{subplot_idx}")
                    else:
                        xlim_min, xlim_max = None, None
                with lc2:
                    use_ylim = st.checkbox("Set Y limits", value=False,
                                           key=f"univ_useylim_{subplot_idx}")
                    if use_ylim:
                        ylim_min = st.number_input("Y min", value=0.0, format="%.4f",
                                                   key=f"univ_ymin_{subplot_idx}")
                        ylim_max = st.number_input("Y max", value=100.0, format="%.4f",
                                                   key=f"univ_ymax_{subplot_idx}")
                    else:
                        ylim_min, ylim_max = None, None

            # Labels
            with st.expander("📝 Labels", expanded=False):
                subplot_title = st.text_input("Subplot title",
                                              value=f"Subplot {subplot_idx + 1}",
                                              key=f"univ_title_{subplot_idx}")
                x_label = st.text_input("X-axis label",
                                        value=layers[0]['x_col'] if layers else "",
                                        key=f"univ_xlabel_{subplot_idx}")
                y_label = st.text_input("Y-axis label", value="Value",
                                        key=f"univ_ylabel_{subplot_idx}")

            config.update({
                'layers': layers,
                'x_scale': x_scale,
                'y_scale': y_scale,
                'show_grid': show_grid,
                'show_legend': show_legend,
                'use_xlim': use_xlim,
                'xlim_min': xlim_min,
                'xlim_max': xlim_max,
                'use_ylim': use_ylim,
                'ylim_min': ylim_min,
                'ylim_max': ylim_max,
                'title': subplot_title,
                'x_label': x_label,
                'y_label': y_label,
            })

        # =================================================================
        # 2D IMAGE/HEATMAP CONFIGURATION (from Image Viewer)
        # =================================================================
        elif plot_category == "2D Image/Heatmap":
            # Data source: image array or tabular pivot
            source_type = st.radio(
                "Source type",
                ["Image array (NPY/NPZ/PNG)" if image_names else "(No images loaded)",
                 "Tabular data (CSV pivot)" if data_names else "(No tabular data loaded)"],
                horizontal=True,
                key=f"univ_2dsrc_{subplot_idx}",
            )

            if "Image array" in source_type and image_names:
                img_name = st.selectbox("Image", image_names,
                                        key=f"univ_img_{subplot_idx}")
                img_raw = st.session_state['univ_loaded_images'][img_name]

                # Handle stacks
                if img_raw.ndim == 3:
                    frame_idx = st.slider(
                        f"Frame (0-{img_raw.shape[0] - 1})",
                        0, img_raw.shape[0] - 1, 0,
                        key=f"univ_frame_{subplot_idx}",
                    )
                    img_2d = img_raw[frame_idx]
                else:
                    img_2d = img_raw

                config['source'] = 'image'
                config['img_2d'] = img_2d

            elif "Tabular" in source_type and data_names:
                data_name = st.selectbox("Dataset", data_names,
                                         key=f"univ_data_2d_{subplot_idx}")
                df = st.session_state['univ_loaded_data'][data_name]
                columns = list(df.columns)

                tc1, tc2, tc3 = st.columns(3)
                with tc1:
                    x_col = st.selectbox("X column", columns,
                                         key=f"univ_2dx_{subplot_idx}")
                with tc2:
                    y_opts = [c for c in columns if c != x_col]
                    y_col = st.selectbox("Y column", y_opts,
                                         key=f"univ_2dy_{subplot_idx}")
                with tc3:
                    z_opts = [c for c in columns if c not in [x_col, y_col]]
                    z_col = st.selectbox("Z / Intensity", z_opts,
                                         key=f"univ_2dz_{subplot_idx}")

                config['source'] = 'tabular'
                config['data_name'] = data_name
                config['df'] = df
                config['x_col'] = x_col
                config['y_col'] = y_col
                config['z_col'] = z_col
            else:
                st.warning("No suitable data loaded for this source type.")
                subplot_configs.append({'enabled': False})
                continue

            # Display controls (from Image Viewer)
            dc1, dc2 = st.columns(2)
            with dc1:
                cmap = st.selectbox("Colormap", COLORMAPS_2D,
                                    key=f"univ_cmap_{subplot_idx}")
                use_log = st.checkbox("Log scale", value=False,
                                      key=f"univ_log_{subplot_idx}")
            with dc2:
                aspect_mode = st.radio("Aspect ratio", ["equal", "auto"],
                                       horizontal=True,
                                       key=f"univ_aspect_{subplot_idx}")

            with st.expander("🔆 Intensity / Contrast", expanded=False):
                auto_contrast = st.checkbox("Auto contrast (1st-99th percentile)",
                                            value=True,
                                            key=f"univ_autocon_{subplot_idx}")
                if not auto_contrast:
                    vmin_pct = st.slider("Min percentile", 0.0, 50.0, 0.0, 0.5,
                                         key=f"univ_vminp_{subplot_idx}")
                    vmax_pct = st.slider("Max percentile", 50.0, 100.0, 100.0, 0.5,
                                         key=f"univ_vmaxp_{subplot_idx}")
                else:
                    vmin_pct, vmax_pct = 0.0, 100.0

            subplot_title = st.text_input("Subplot title",
                                          value=f"Subplot {subplot_idx + 1}",
                                          key=f"univ_title_{subplot_idx}")

            config.update({
                'cmap': cmap,
                'use_log': use_log,
                'aspect_mode': aspect_mode,
                'auto_contrast': auto_contrast,
                'vmin_pct': vmin_pct,
                'vmax_pct': vmax_pct,
                'title': subplot_title,
            })

        # =================================================================
        # 3D PLOT CONFIGURATION (from 3D Plotter)
        # =================================================================
        elif plot_category == "3D Plot":
            if not data_names:
                st.warning("No tabular data loaded. Load CSV/NPZ files with X/Y/Z columns.")
                subplot_configs.append({'enabled': False})
                continue

            data_name = st.selectbox("Dataset", data_names,
                                     key=f"univ_data_3d_{subplot_idx}")
            df = st.session_state['univ_loaded_data'][data_name]
            columns = list(df.columns)

            tc1, tc2, tc3 = st.columns(3)
            with tc1:
                x_col = st.selectbox("X column", columns,
                                     key=f"univ_3dx_{subplot_idx}")
            with tc2:
                y_col = st.selectbox("Y column", columns,
                                     index=min(1, len(columns) - 1),
                                     key=f"univ_3dy_{subplot_idx}")
            with tc3:
                z_col = st.selectbox("Z column", columns,
                                     index=min(2, len(columns) - 1),
                                     key=f"univ_3dz_{subplot_idx}")

            # 4th dimension for color
            use_color_dim = st.checkbox("Use 4th dimension for color",
                                        value=(len(columns) > 3),
                                        key=f"univ_use4d_{subplot_idx}")
            if use_color_dim and len(columns) > 3:
                color_col = st.selectbox("Color column", columns,
                                         index=min(3, len(columns) - 1),
                                         key=f"univ_colcol_{subplot_idx}")
            else:
                color_col = None

            # Plot type (all 5 from 3D Plotter)
            plot_type_3d = st.radio(
                "3D plot type",
                PLOT_TYPES_3D,
                horizontal=True,
                key=f"univ_3dtype_{subplot_idx}",
                help="All types are fully interactive!",
            )

            sc1, sc2 = st.columns(2)
            with sc1:
                colorscale_3d = st.selectbox("Colorscale", COLORSCALES_3D,
                                             key=f"univ_3dcscale_{subplot_idx}")
            with sc2:
                opacity_3d = st.slider("Opacity", 0.1, 1.0, 0.9, 0.1,
                                       key=f"univ_3dopacity_{subplot_idx}")

            subplot_title = st.text_input("Subplot title",
                                          value=f"Subplot {subplot_idx + 1}",
                                          key=f"univ_title_{subplot_idx}")

            config.update({
                'data_name': data_name,
                'df': df,
                'x_col': x_col,
                'y_col': y_col,
                'z_col': z_col,
                'color_col': color_col,
                'plot_type_3d': plot_type_3d,
                'colorscale_3d': colorscale_3d,
                'opacity_3d': opacity_3d,
                'title': subplot_title,
            })

        subplot_configs.append(config)

# ---------------------------------------------------------------------------
# Generate Figure (reactive — auto-updates on any widget change)
# ---------------------------------------------------------------------------

st.divider()
st.header("📊 Generated Figure")

# Check if any subplot is enabled with valid data
any_enabled = any(cfg.get('enabled') for cfg in subplot_configs)

if any_enabled:

    # Build subplot specs (3D types need scene, others xy)
    specs = []
    titles = []
    for row in range(n_rows):
        row_specs = []
        for col_i in range(n_cols):
            idx = row * n_cols + col_i
            if idx < len(subplot_configs) and subplot_configs[idx].get('enabled'):
                cfg = subplot_configs[idx]
                if cfg.get('category') == '3D Plot':
                    row_specs.append({"type": "scene"})
                else:
                    row_specs.append({"type": "xy"})
                titles.append(cfg.get('title', ''))
            else:
                row_specs.append({"type": "xy"})
                titles.append("")
        specs.append(row_specs)

    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        specs=specs,
        subplot_titles=titles,
    )

    # Track per-subplot legend assignments (Change 3)
    legend_configs = {}
    legend_counter = 0

    for idx, cfg in enumerate(subplot_configs):
        row = idx // n_cols + 1
        col_i = idx % n_cols + 1

        if not cfg.get('enabled'):
            continue

        cat = cfg.get('category')

        # Assign a unique legend group for 1D subplots
        legend_name = "legend" if legend_counter == 0 else f"legend{legend_counter + 1}"

        # ================================================================
        # 1D PLOT RENDERING (multi-layer)
        # ================================================================
        if cat == '1D Plot':
            layers = cfg.get('layers', [])
            show_legend = cfg.get('show_legend', True)

            for layer in layers:
                df = layer['df']
                x_col = layer['x_col']
                y_cols = layer.get('y_cols', [])
                styles = layer.get('curve_styles', {})
                layer_data_name = layer.get('data_name', '')

                for yc in y_cols:
                    style = styles.get(yc, {})
                    if not style.get('enabled', True):
                        continue

                    if x_col not in df.columns or yc not in df.columns:
                        continue

                    x_data = df[x_col].values.astype(float)
                    y_data = df[yc].values.astype(float)
                    mask = ~(np.isnan(x_data) | np.isnan(y_data))
                    x_data = x_data[mask]
                    y_data = y_data[mask]

                    if len(x_data) == 0:
                        continue

                    color = style.get('color', '#1f77b4')
                    marker_sym = style.get('marker_plotly')
                    dash = style.get('dash')
                    lw = style.get('linewidth', 2.0)
                    alpha = style.get('opacity', 0.9)

                    # Determine mode
                    has_line = dash is not None
                    has_marker = marker_sym is not None
                    if has_line and has_marker:
                        mode = 'lines+markers'
                    elif has_marker:
                        mode = 'markers'
                    else:
                        mode = 'lines'
                        dash = 'solid'

                    # Build trace name: include dataset name if multiple layers
                    if len(layers) > 1:
                        short_name = shorten_path(layer_data_name, 20)
                        trace_name = f"{short_name}: {yc}"
                    else:
                        trace_name = yc

                    fig.add_trace(
                        go.Scatter(
                            x=x_data, y=y_data,
                            mode=mode,
                            name=trace_name,
                            line=dict(color=color, width=lw, dash=dash if dash else 'solid'),
                            marker=dict(symbol=marker_sym if marker_sym else 'circle',
                                        size=7, color=color),
                            opacity=alpha,
                            showlegend=show_legend,
                            legend=legend_name,
                            hovertemplate=(
                                f'<b>{x_col}</b>: %{{x:.4g}}<br>'
                                f'<b>{yc}</b>: %{{y:.4g}}<extra>{trace_name}</extra>'
                            ),
                        ),
                        row=row, col=col_i,
                    )

            # Store legend config — grab axis refs from the last trace added
            if show_legend and len(fig.data) > 0:
                last_trace = fig.data[-1]
                legend_configs[legend_name] = {
                    'xaxis': getattr(last_trace, 'xaxis', 'x') or 'x',
                    'yaxis': getattr(last_trace, 'yaxis', 'y') or 'y',
                }
            legend_counter += 1

            # Axis settings
            x_type = 'log' if cfg.get('x_scale') == 'log' else 'linear'
            y_type = 'log' if cfg.get('y_scale') == 'log' else 'linear'

            x_range = None
            if cfg.get('use_xlim') and cfg.get('xlim_min') is not None:
                if x_type == 'log' and cfg['xlim_min'] > 0:
                    x_range = [np.log10(cfg['xlim_min']), np.log10(cfg['xlim_max'])]
                else:
                    x_range = [cfg['xlim_min'], cfg['xlim_max']]

            y_range = None
            if cfg.get('use_ylim') and cfg.get('ylim_min') is not None:
                if y_type == 'log' and cfg['ylim_min'] > 0:
                    y_range = [np.log10(cfg['ylim_min']), np.log10(cfg['ylim_max'])]
                else:
                    y_range = [cfg['ylim_min'], cfg['ylim_max']]

            fig.update_xaxes(
                title_text=cfg.get('x_label', ''),
                type=x_type,
                range=x_range,
                showgrid=cfg.get('show_grid', True),
                gridcolor='lightgray',
                row=row, col=col_i,
            )
            fig.update_yaxes(
                title_text=cfg.get('y_label', 'Value'),
                type=y_type,
                range=y_range,
                showgrid=cfg.get('show_grid', True),
                gridcolor='lightgray',
                row=row, col=col_i,
            )

        # ================================================================
        # 2D HEATMAP RENDERING
        # ================================================================
        elif cat == '2D Image/Heatmap':
            legend_counter += 1  # keep counter in sync (no legend for 2D)

            cmap = cfg.get('cmap', 'viridis')
            use_log = cfg.get('use_log', False)
            auto_contrast = cfg.get('auto_contrast', True)
            vmin_pct = cfg.get('vmin_pct', 0.0)
            vmax_pct = cfg.get('vmax_pct', 100.0)
            colorscale = _PLOTLY_CMAP.get(cmap, 'Viridis')
            aspect_mode = cfg.get('aspect_mode', 'auto')

            if cfg.get('source') == 'image':
                # Direct 2D array
                img_2d = cfg['img_2d'].astype(np.float64)
                display_data, _ = prepare_display_data(img_2d, use_log)
                vmin, vmax = calc_intensity_range(display_data, auto_contrast,
                                                  vmin_pct, vmax_pct)

                custom_3d = img_2d[:, :, np.newaxis]

                hover_parts = ['x: %{x}', 'y: %{y}']
                if use_log:
                    hover_parts.append('Intensity: %{customdata[0]:.4g}')
                    hover_parts.append('log10: %{z:.3f}')
                else:
                    hover_parts.append('Intensity: %{customdata[0]:.4g}')
                hover = '<br>'.join(hover_parts) + '<extra></extra>'

                _cb_title = "log10(I)" if use_log else "Intensity"
                _cbar = make_subplot_colorbar(fig, row, col_i, n_rows, n_cols, _cb_title)
                fig.add_trace(
                    go.Heatmap(
                        z=display_data,
                        zmin=vmin, zmax=vmax,
                        colorscale=colorscale,
                        customdata=custom_3d,
                        hovertemplate=hover,
                        colorbar=_cbar,
                        showlegend=False,
                    ),
                    row=row, col=col_i,
                )
                fig.update_yaxes(autorange='reversed', row=row, col=col_i)

            else:
                # Tabular pivot
                df = cfg['df']
                x_col = cfg['x_col']
                y_col = cfg['y_col']
                z_col = cfg['z_col']

                try:
                    pivot_df = df.pivot_table(values=z_col, index=y_col,
                                              columns=x_col, aggfunc='mean')
                    z_data = pivot_df.values.astype(float)
                    x_vals = pivot_df.columns.values
                    y_vals = pivot_df.index.values
                except Exception:
                    x_vals = sorted(df[x_col].unique())
                    y_vals = sorted(df[y_col].unique())
                    z_data = np.full((len(y_vals), len(x_vals)), np.nan)
                    for i, yv in enumerate(y_vals):
                        for j, xv in enumerate(x_vals):
                            mask = (df[x_col] == xv) & (df[y_col] == yv)
                            if mask.any():
                                z_data[i, j] = df.loc[mask, z_col].iloc[0]

                original_z = z_data.copy()

                if use_log:
                    floor = np.nanmin(z_data[z_data > 0]) if np.any(z_data > 0) else 1e-10
                    z_data = np.log10(np.clip(z_data, floor, None))

                display_data = z_data
                vmin, vmax = calc_intensity_range(display_data, auto_contrast,
                                                  vmin_pct, vmax_pct)

                custom_3d = original_z[:, :, np.newaxis]

                hover_parts = [
                    f'<b>{x_col}</b>: %{{x:.4g}}',
                    f'<b>{y_col}</b>: %{{y:.4g}}',
                    f'<b>{z_col}</b>: %{{customdata[0]:.4g}}',
                ]
                if use_log:
                    hover_parts.append('log10: %{z:.3f}')
                hover = '<br>'.join(hover_parts) + '<extra></extra>'

                _cb_title = "log10(I)" if use_log else z_col
                _cbar = make_subplot_colorbar(fig, row, col_i, n_rows, n_cols, _cb_title)
                fig.add_trace(
                    go.Heatmap(
                        z=display_data, x=x_vals, y=y_vals,
                        zmin=vmin, zmax=vmax,
                        colorscale=colorscale,
                        customdata=custom_3d,
                        hovertemplate=hover,
                        colorbar=_cbar,
                        showlegend=False,
                    ),
                    row=row, col=col_i,
                )
                fig.update_xaxes(title_text=x_col, row=row, col=col_i)
                fig.update_yaxes(title_text=y_col, autorange='reversed',
                                 row=row, col=col_i)

            # Aspect ratio — read actual xaxis ref from the trace we just added
            if aspect_mode == 'equal':
                last_trace = fig.data[-1]
                xref = getattr(last_trace, 'xaxis', 'x') or 'x'
                # scaleanchor needs the axis name like "x", "x2", etc.
                fig.update_yaxes(scaleanchor=xref, scaleratio=1,
                                 row=row, col=col_i)

        # ================================================================
        # 3D PLOT RENDERING
        # ================================================================
        elif cat == '3D Plot':
            legend_counter += 1  # keep counter in sync (no legend for 3D)

            df = cfg['df']
            x_col = cfg['x_col']
            y_col = cfg['y_col']
            z_col = cfg['z_col']
            color_col = cfg.get('color_col')
            pt3d = cfg.get('plot_type_3d', 'Surface')
            cscale = cfg.get('colorscale_3d', 'Viridis')
            opacity = cfg.get('opacity_3d', 0.9)

            x = df[x_col].values.astype(float)
            y = df[y_col].values.astype(float)
            z = df[z_col].values.astype(float)
            c = df[color_col].values.astype(float) if color_col else z

            _cb_title = color_col if color_col else z_col

            if pt3d == "Surface":
                X, Y, Z = create_meshgrid_from_data(x, y, z)
                if color_col:
                    C, _, _ = create_meshgrid_from_data(x, y, c)
                else:
                    C = Z

                fig.add_trace(
                    go.Surface(
                        x=X, y=Y, z=Z,
                        surfacecolor=C,
                        colorscale=cscale,
                        opacity=opacity,
                        showlegend=False,
                        hovertemplate=(
                            f'<b>{x_col}</b>: %{{x:.4g}}<br>'
                            f'<b>{y_col}</b>: %{{y:.4g}}<br>'
                            f'<b>{z_col}</b>: %{{z:.4g}}<extra></extra>'
                        ),
                    ),
                    row=row, col=col_i,
                )
                fix_3d_colorbar(fig, _cb_title)

            elif pt3d == "Scatter 3D":
                fig.add_trace(
                    go.Scatter3d(
                        x=x, y=y, z=z,
                        mode='markers',
                        marker=dict(
                            size=3, color=c, colorscale=cscale,
                            opacity=opacity,
                        ),
                        showlegend=False,
                        hovertemplate=(
                            f'<b>{x_col}</b>: %{{x:.4g}}<br>'
                            f'<b>{y_col}</b>: %{{y:.4g}}<br>'
                            f'<b>{z_col}</b>: %{{z:.4g}}<extra></extra>'
                        ),
                    ),
                    row=row, col=col_i,
                )
                fix_3d_colorbar(fig, _cb_title)

            elif pt3d == "Contour 3D":
                fig.add_trace(
                    go.Isosurface(
                        x=x, y=y, z=z,
                        value=c,
                        colorscale=cscale,
                        opacity=opacity,
                        caps=dict(x_show=False, y_show=False),
                        showlegend=False,
                    ),
                    row=row, col=col_i,
                )
                fix_3d_colorbar(fig, _cb_title)

            elif pt3d == "Wireframe":
                X, Y, Z = create_meshgrid_from_data(x, y, z, grid_size=50)
                for i in range(0, X.shape[0], 2):
                    fig.add_trace(
                        go.Scatter3d(
                            x=X[i, :], y=Y[i, :], z=Z[i, :],
                            mode='lines',
                            line=dict(color='blue', width=1),
                            showlegend=False,
                        ),
                        row=row, col=col_i,
                    )
                for j in range(0, X.shape[1], 2):
                    fig.add_trace(
                        go.Scatter3d(
                            x=X[:, j], y=Y[:, j], z=Z[:, j],
                            mode='lines',
                            line=dict(color='blue', width=1),
                            showlegend=False,
                        ),
                        row=row, col=col_i,
                    )

            else:  # Mesh
                X, Y, Z = create_meshgrid_from_data(x, y, z)
                fig.add_trace(
                    go.Mesh3d(
                        x=X.flatten(), y=Y.flatten(), z=Z.flatten(),
                        intensity=c if color_col else Z.flatten(),
                        colorscale=cscale,
                        opacity=opacity,
                        showlegend=False,
                    ),
                    row=row, col=col_i,
                )
                fix_3d_colorbar(fig, _cb_title)

            # Scene axis labels
            fig.update_scenes(
                dict(xaxis_title=x_col, yaxis_title=y_col, zaxis_title=z_col),
                row=row, col=col_i,
            )

    # Position per-subplot legends using actual axis domains from figure
    layout_kwargs = {}
    for leg_name, axis_refs in legend_configs.items():
        try:
            # Map trace axis ref (e.g. "x2") to layout key (e.g. "xaxis2")
            xref = axis_refs['xaxis']
            yref = axis_refs['yaxis']
            xaxis_key = 'xaxis' if xref == 'x' else f'xaxis{xref[1:]}'
            yaxis_key = 'yaxis' if yref == 'y' else f'yaxis{yref[1:]}'

            x_domain = list(getattr(fig.layout, xaxis_key).domain)
            y_domain = list(getattr(fig.layout, yaxis_key).domain)

            # Place legend inside subplot, top-right corner
            legend_cfg = dict(
                x=x_domain[1], y=y_domain[1],
                xanchor='right', yanchor='top',
                bgcolor='rgba(255,255,255,0.7)',
                bordercolor='rgba(200,200,200,0.5)',
                borderwidth=1,
                font=dict(size=10),
            )
        except Exception:
            # Fallback: default position
            legend_cfg = dict(
                bgcolor='rgba(255,255,255,0.7)',
                font=dict(size=10),
            )
        layout_kwargs[leg_name] = legend_cfg

    # Global layout
    fig.update_layout(
        height=max(500, 450 * n_rows),
        hovermode='closest',
        title_text="Universal Plotter",
        **layout_kwargs,
    )

    st.plotly_chart(fig, use_container_width=True)
    st.session_state['univ_generated_fig'] = fig
    st.caption("**Hover** for values, **scroll** to zoom, **drag** to pan, **click-drag** to rotate 3D.")

else:
    st.info("Enable at least one subplot above to see the plot.")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

if 'univ_generated_fig' in st.session_state:
    st.divider()
    st.header("💾 Export")

    col1, col2, col3 = st.columns(3)

    with col1:
        html_buffer = io.StringIO()
        st.session_state['univ_generated_fig'].write_html(html_buffer)
        st.download_button(
            label="📥 Interactive HTML",
            data=html_buffer.getvalue().encode(),
            file_name="universal_plot.html",
            mime="text/html",
            help="Fully interactive — zoom, hover, rotate preserved",
        )

    with col2:
        try:
            img_bytes = st.session_state['univ_generated_fig'].to_image(
                format="png", width=1200, height=800)
            st.download_button(
                label="📥 PNG",
                data=img_bytes,
                file_name="universal_plot.png",
                mime="image/png",
            )
        except Exception:
            st.warning("Install kaleido for PNG export")

    with col3:
        try:
            img_bytes = st.session_state['univ_generated_fig'].to_image(format="svg")
            st.download_button(
                label="📥 SVG",
                data=img_bytes,
                file_name="universal_plot.svg",
                mime="image/svg+xml",
            )
        except Exception:
            st.warning("Install kaleido for SVG export")

# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------

with st.expander("ℹ️ How to Use"):
    st.markdown("""
    ### Universal Plotter Guide

    **1. Load Data** (sidebar)
    - Upload files, browse server, or generate synthetic test data
    - **Quick start:** Click **"🧪 Load Test Data"** to load representative samples instantly
    - Supports CSV, TXT, NPZ, NPY for tabular data
    - Supports NPY, NPZ, PNG, TIF for 2D images

    **2. Choose Layout**
    - Select grid arrangement (1x1, 2x2, etc.)
    - Each subplot is configured independently

    **3. Configure Each Subplot**
    - **Enable** the subplot (only Subplot 1 is on by default)
    - Choose category: **1D Plot**, **2D Image/Heatmap**, or **3D Plot**

    **1D Plot options** (same as CSV Plotter):
    - **Multiple datasets per subplot** — overlay curves from different files
    - X column + multiple Y columns per dataset (each = separate curve)
    - Per-curve styling: color (15), marker (12), line style (5), width, opacity
    - X/Y scale (linear/log), axis limits, grid, legend
    - Custom axis labels

    **2D Image/Heatmap options** (same as Image Viewer):
    - Image arrays (NPY/NPZ/PNG) or tabular pivot (CSV with X, Y, Z)
    - 15 colormaps, log scale, auto contrast / percentile sliders
    - Equal or auto aspect ratio

    **3D Plot options** (same as 3D Plotter):
    - X, Y, Z columns + optional 4th dimension for color
    - 5 plot types: Surface, Scatter 3D, Contour 3D, Wireframe, Mesh
    - 15 colorscales, opacity slider

    **4. Live Preview**
    - Plot updates **automatically** when you change any setting — no button needed!
    - **Hover** for exact values
    - **Scroll** to zoom, **drag** to pan
    - **Rotate** 3D plots by click-drag
    - Each subplot has its own **independent legend**

    **5. Export**
    - **HTML**: Fully interactive (recommended!)
    - **PNG / SVG**: Static images for publications
    """)
