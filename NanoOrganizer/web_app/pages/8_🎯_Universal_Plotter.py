#!/usr/bin/env python3
"""
Universal Plotter - Integrated plotting for 1D, 2D, and 3D data.

Features:
- Create custom grid layouts with mixed plot types
- 1D: Line, Scatter, Line+Markers with multi-column Y selection
- 2D: Heatmap with optional log scale
- 3D: Surface, Scatter 3D
- Interactive hover, zoom, pan (Plotly)
- Export: interactive HTML, PNG, SVG
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from pathlib import Path
import io
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.folder_browser import folder_browser
from components.floating_button import floating_sidebar_toggle

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLOT_TYPES_1D = ["1D Line", "1D Scatter", "1D Line+Markers"]
PLOT_TYPES_2D = ["2D Heatmap", "2D Heatmap (log)"]
PLOT_TYPES_3D = ["3D Surface", "3D Scatter"]
ALL_PLOT_TYPES = PLOT_TYPES_1D + PLOT_TYPES_2D + PLOT_TYPES_3D

# Colors for multi-trace 1D plots
TRACE_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#000080', '#FF00FF', '#FFD700', '#008080', '#00FF00',
]

COLORSCALES = ['Viridis', 'Plasma', 'Inferno', 'Magma', 'Cividis',
               'Turbo', 'Jet', 'Hot', 'Greys', 'RdBu']

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def load_data_file(file_path):
    """Load CSV, TXT, DAT, NPZ, or NPY file."""
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


def generate_synthetic_data(func_type, points=100):
    """Generate synthetic data for testing."""
    if func_type == "1D - Sine wave":
        x = np.linspace(0, 4 * np.pi, points)
        y = np.sin(x) + 0.1 * np.random.randn(points)
        return pd.DataFrame({'x': x, 'y': y})
    elif func_type == "1D - Gaussian":
        x = np.linspace(-5, 5, points)
        y = np.exp(-x**2) + 0.05 * np.random.randn(points)
        return pd.DataFrame({'x': x, 'y': y})
    elif func_type == "2D - Heatmap":
        n = int(np.sqrt(points))
        x = np.linspace(-3, 3, n)
        y = np.linspace(-3, 3, n)
        X, Y = np.meshgrid(x, y)
        Z = np.exp(-(X**2 + Y**2))
        return pd.DataFrame({'x': X.flatten(), 'y': Y.flatten(), 'z': Z.flatten()})
    elif func_type == "3D - Surface":
        n = int(np.sqrt(points))
        x = np.linspace(-5, 5, n)
        y = np.linspace(-5, 5, n)
        X, Y = np.meshgrid(x, y)
        Z = np.sin(np.sqrt(X**2 + Y**2))
        return pd.DataFrame({'x': X.flatten(), 'y': Y.flatten(), 'z': Z.flatten()})
    return None


def is_3d_type(plot_type):
    return plot_type in PLOT_TYPES_3D


# ---------------------------------------------------------------------------
# Initialize session state
# ---------------------------------------------------------------------------

if 'loaded_data' not in st.session_state:
    st.session_state['loaded_data'] = {}

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
        help="Choose subplot grid arrangement"
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
        help="Load data from file or generate test data"
    )

    if data_source == "Upload files":
        uploaded_files = st.file_uploader(
            "Upload data files",
            type=['csv', 'txt', 'dat', 'npz', 'npy'],
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
                        st.session_state['loaded_data'][uploaded_file.name] = df
                except Exception as e:
                    st.error(f"Error loading {uploaded_file.name}: {e}")

    elif data_source == "Browse server":
        st.markdown("**🗂️ Interactive Folder Browser**")

        pattern = st.selectbox(
            "File type",
            ["*.*", "*.csv", "*.npz", "*.npy", "*.txt", "*.dat"],
            index=0,
            help="Filter files by pattern"
        )

        selected_files = folder_browser(
            key="universal_plotter_browser",
            show_files=True,
            file_pattern=pattern,
            multi_select=True
        )

        if selected_files and st.button("📥 Load Selected Files"):
            for file_path in selected_files:
                df = load_data_file(file_path)
                if df is not None:
                    file_name = Path(file_path).name
                    st.session_state['loaded_data'][file_name] = df
                    st.success(f"✅ Loaded {file_name}")

    else:  # Generate synthetic
        st.markdown("**Quick test data:**")
        if st.button("🎲 Generate 1D Sine"):
            st.session_state['loaded_data']['Sine Wave'] = generate_synthetic_data("1D - Sine wave")
        if st.button("🎲 Generate 1D Gaussian"):
            st.session_state['loaded_data']['Gaussian'] = generate_synthetic_data("1D - Gaussian")
        if st.button("🎲 Generate 2D Heatmap"):
            st.session_state['loaded_data']['2D Heatmap'] = generate_synthetic_data("2D - Heatmap")
        if st.button("🎲 Generate 3D Surface"):
            st.session_state['loaded_data']['3D Surface'] = generate_synthetic_data("3D - Surface")

    if st.session_state['loaded_data']:
        st.success(f"✅ {len(st.session_state['loaded_data'])} dataset(s) loaded")
        if st.button("🗑️ Clear all data"):
            st.session_state['loaded_data'] = {}
            st.rerun()

# ---------------------------------------------------------------------------
# Main Area: Subplot Configuration
# ---------------------------------------------------------------------------

if not st.session_state['loaded_data']:
    st.info("👆 Load or generate data first using the sidebar")
    st.stop()

data_names = list(st.session_state['loaded_data'].keys())

st.header(f"⚙️ Configure {n_rows}×{n_cols} Layout ({total_subplots} subplot{'s' if total_subplots > 1 else ''})")

subplot_tabs = st.tabs([f"Subplot {i+1}" for i in range(total_subplots)])

subplot_configs = []

for subplot_idx, tab in enumerate(subplot_tabs):
    with tab:
        # Enable toggle — only first subplot enabled by default
        enabled = st.checkbox(
            "Enable this subplot",
            value=(subplot_idx == 0),
            key=f"enable_{subplot_idx}"
        )

        if not enabled:
            st.info("This subplot is empty. Enable it to configure.")
            subplot_configs.append({'enabled': False})
            continue

        col_left, col_right = st.columns([1, 1])

        with col_left:
            data_name = st.selectbox(
                "Dataset",
                data_names,
                key=f"data_{subplot_idx}"
            )

            df = st.session_state['loaded_data'][data_name]
            columns = list(df.columns)

            plot_type = st.selectbox(
                "Plot type",
                ALL_PLOT_TYPES,
                key=f"plot_type_{subplot_idx}",
                help="1D: line/scatter plots | 2D: heatmap | 3D: surface/scatter"
            )

            # Colorscale for 2D/3D
            if plot_type not in PLOT_TYPES_1D:
                colorscale = st.selectbox(
                    "Colorscale",
                    COLORSCALES,
                    key=f"cscale_{subplot_idx}"
                )
            else:
                colorscale = 'Viridis'

        with col_right:
            if plot_type in PLOT_TYPES_1D:
                # --- 1D: X column + multi-Y columns ---
                x_col = st.selectbox("X column", columns, key=f"x_{subplot_idx}")
                available_y = [c for c in columns if c != x_col]
                y_cols = st.multiselect(
                    "Y column(s)",
                    available_y,
                    default=[available_y[0]] if available_y else [],
                    key=f"y_multi_{subplot_idx}",
                    help="Select one or more Y columns — each creates a separate curve"
                )
                z_col = None

                # X/Y scale
                c1, c2 = st.columns(2)
                with c1:
                    x_scale = st.radio("X scale", ["linear", "log"],
                                       horizontal=True, key=f"xscale_{subplot_idx}")
                with c2:
                    y_scale = st.radio("Y scale", ["linear", "log"],
                                       horizontal=True, key=f"yscale_{subplot_idx}")

            elif plot_type in PLOT_TYPES_2D:
                # --- 2D: X, Y, Z columns ---
                x_col = st.selectbox("X column", columns, key=f"x_{subplot_idx}")
                y_cols_2d = [c for c in columns if c != x_col]
                y_col_single = st.selectbox("Y column", y_cols_2d, key=f"y_{subplot_idx}")
                z_candidates = [c for c in columns if c not in [x_col, y_col_single]]
                z_col = st.selectbox("Z / Intensity column", z_candidates, key=f"z_{subplot_idx}")
                y_cols = [y_col_single]
                x_scale, y_scale = "linear", "linear"

            else:
                # --- 3D: X, Y, Z columns ---
                x_col = st.selectbox("X column", columns, key=f"x_{subplot_idx}")
                y_cols_3d = [c for c in columns if c != x_col]
                y_col_single = st.selectbox("Y column", y_cols_3d, key=f"y_{subplot_idx}")
                z_candidates = [c for c in columns if c not in [x_col, y_col_single]]
                z_col = st.selectbox("Z column", z_candidates, key=f"z_{subplot_idx}")
                y_cols = [y_col_single]
                x_scale, y_scale = "linear", "linear"

        subplot_title = st.text_input(
            "Subplot title",
            value=f"Subplot {subplot_idx + 1}",
            key=f"title_{subplot_idx}"
        )

        subplot_configs.append({
            'enabled': True,
            'data_name': data_name,
            'df': df,
            'plot_type': plot_type,
            'x_col': x_col,
            'y_cols': y_cols,
            'z_col': z_col,
            'title': subplot_title,
            'colorscale': colorscale,
            'x_scale': x_scale,
            'y_scale': y_scale,
        })

# ---------------------------------------------------------------------------
# Generate Figure
# ---------------------------------------------------------------------------

st.divider()
st.header("📊 Generated Figure")

if st.button("🎨 Generate Plot", type="primary"):

    # Build subplot specs
    specs = []
    titles = []
    for row in range(n_rows):
        row_specs = []
        for col_i in range(n_cols):
            idx = row * n_cols + col_i
            if idx < len(subplot_configs) and subplot_configs[idx].get('enabled'):
                cfg = subplot_configs[idx]
                if is_3d_type(cfg['plot_type']):
                    row_specs.append({"type": "scene"})
                else:
                    row_specs.append({"type": "xy"})
                titles.append(cfg['title'])
            else:
                row_specs.append({"type": "xy"})
                titles.append("")
        specs.append(row_specs)

    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        specs=specs,
        subplot_titles=titles
    )

    trace_count = 0

    for idx, config in enumerate(subplot_configs):
        row = idx // n_cols + 1
        col_i = idx % n_cols + 1

        if not config.get('enabled'):
            continue

        df = config['df']
        pt = config['plot_type']
        x_col = config['x_col']
        y_cols = config['y_cols']
        z_col = config.get('z_col')
        cscale = config.get('colorscale', 'Viridis')

        # ---- 1D plot types ----
        if pt in PLOT_TYPES_1D:
            if pt == "1D Line":
                mode = 'lines'
            elif pt == "1D Scatter":
                mode = 'markers'
            else:
                mode = 'lines+markers'

            for y_idx, y_col in enumerate(y_cols):
                if x_col not in df.columns or y_col not in df.columns:
                    continue

                x_data = df[x_col].values
                y_data = df[y_col].values
                mask = ~(np.isnan(x_data.astype(float)) | np.isnan(y_data.astype(float)))
                x_data = x_data[mask]
                y_data = y_data[mask]

                if len(x_data) == 0:
                    continue

                color = TRACE_COLORS[(trace_count + y_idx) % len(TRACE_COLORS)]
                trace_name = y_col if len(y_cols) > 1 else config['title']

                fig.add_trace(
                    go.Scatter(
                        x=x_data, y=y_data,
                        mode=mode,
                        name=trace_name,
                        line=dict(color=color, width=2),
                        marker=dict(color=color, size=5),
                        hovertemplate=(
                            f'<b>{x_col}</b>: %{{x:.4g}}<br>'
                            f'<b>{y_col}</b>: %{{y:.4g}}<extra>{trace_name}</extra>'
                        ),
                    ),
                    row=row, col=col_i,
                )

            # Axis labels and scale
            fig.update_xaxes(title_text=x_col, row=row, col=col_i,
                             type='log' if config.get('x_scale') == 'log' else 'linear')
            fig.update_yaxes(
                title_text=y_cols[0] if len(y_cols) == 1 else "Value",
                row=row, col=col_i,
                type='log' if config.get('y_scale') == 'log' else 'linear',
            )

        # ---- 2D Heatmap ----
        elif pt in PLOT_TYPES_2D:
            y_col = y_cols[0]
            use_log = pt.endswith("(log)")

            if x_col not in df.columns or y_col not in df.columns or z_col not in df.columns:
                continue

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

            # 3D customdata for Heatmap hover
            custom_3d = original_z[:, :, np.newaxis]

            hover_parts = [f'<b>{x_col}</b>: %{{x:.4g}}',
                           f'<b>{y_col}</b>: %{{y:.4g}}',
                           f'<b>{z_col}</b>: %{{customdata[0]:.4g}}']
            if use_log:
                hover_parts.append('log₁₀: %{z:.3f}')
            hover = '<br>'.join(hover_parts) + '<extra></extra>'

            fig.add_trace(
                go.Heatmap(
                    z=z_data, x=x_vals, y=y_vals,
                    colorscale=cscale,
                    customdata=custom_3d,
                    hovertemplate=hover,
                    colorbar=dict(title="log₁₀(I)" if use_log else z_col),
                ),
                row=row, col=col_i,
            )
            fig.update_xaxes(title_text=x_col, row=row, col=col_i)
            fig.update_yaxes(title_text=y_col, autorange='reversed', row=row, col=col_i)

        # ---- 3D Surface ----
        elif pt == "3D Surface":
            y_col = y_cols[0]
            if x_col not in df.columns or y_col not in df.columns or z_col not in df.columns:
                continue

            try:
                pivot_df = df.pivot_table(values=z_col, index=y_col,
                                          columns=x_col, aggfunc='mean')
                X, Y = np.meshgrid(pivot_df.columns, pivot_df.index)
                Z = pivot_df.values
            except Exception:
                x_u = sorted(df[x_col].unique())
                y_u = sorted(df[y_col].unique())
                X, Y = np.meshgrid(x_u, y_u)
                Z = np.zeros_like(X, dtype=float)
                for i, yv in enumerate(y_u):
                    for j, xv in enumerate(x_u):
                        mask = (df[x_col] == xv) & (df[y_col] == yv)
                        if mask.any():
                            Z[i, j] = df.loc[mask, z_col].iloc[0]

            fig.add_trace(
                go.Surface(
                    x=X, y=Y, z=Z,
                    colorscale=cscale,
                    hovertemplate=(
                        f'<b>{x_col}</b>: %{{x:.4g}}<br>'
                        f'<b>{y_col}</b>: %{{y:.4g}}<br>'
                        f'<b>{z_col}</b>: %{{z:.4g}}<extra></extra>'
                    ),
                ),
                row=row, col=col_i,
            )
            fig.update_scenes(
                dict(xaxis_title=x_col, yaxis_title=y_col, zaxis_title=z_col),
                row=row, col=col_i,
            )

        # ---- 3D Scatter ----
        elif pt == "3D Scatter":
            y_col = y_cols[0]
            if x_col not in df.columns or y_col not in df.columns or z_col not in df.columns:
                continue

            fig.add_trace(
                go.Scatter3d(
                    x=df[x_col], y=df[y_col], z=df[z_col],
                    mode='markers',
                    marker=dict(size=3, color=df[z_col], colorscale=cscale,
                                colorbar=dict(title=z_col)),
                    hovertemplate=(
                        f'<b>{x_col}</b>: %{{x:.4g}}<br>'
                        f'<b>{y_col}</b>: %{{y:.4g}}<br>'
                        f'<b>{z_col}</b>: %{{z:.4g}}<extra></extra>'
                    ),
                ),
                row=row, col=col_i,
            )
            fig.update_scenes(
                dict(xaxis_title=x_col, yaxis_title=y_col, zaxis_title=z_col),
                row=row, col=col_i,
            )

        trace_count += len(y_cols)

    # Layout
    any_1d = any(c.get('enabled') and c.get('plot_type') in PLOT_TYPES_1D
                 and len(c.get('y_cols', [])) > 1 for c in subplot_configs)

    fig.update_layout(
        height=max(400, 400 * n_rows),
        showlegend=any_1d,
        title_text="Universal Plotter",
        hovermode='closest',
    )

    st.plotly_chart(fig, use_container_width=True)
    st.session_state['generated_fig'] = fig
    st.success("✅ **Hover** for values, **scroll** to zoom, **drag** to pan.")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

if 'generated_fig' in st.session_state:
    st.divider()
    st.header("💾 Export")

    col1, col2, col3 = st.columns(3)

    with col1:
        html_buffer = io.StringIO()
        st.session_state['generated_fig'].write_html(html_buffer)
        st.download_button(
            label="📥 Interactive HTML",
            data=html_buffer.getvalue().encode(),
            file_name="universal_plot.html",
            mime="text/html",
            help="Fully interactive — zoom, hover, rotate preserved"
        )

    with col2:
        try:
            img_bytes = st.session_state['generated_fig'].to_image(
                format="png", width=1200, height=800)
            st.download_button(
                label="📥 PNG",
                data=img_bytes,
                file_name="universal_plot.png",
                mime="image/png"
            )
        except Exception:
            st.warning("Install kaleido for PNG export")

    with col3:
        try:
            img_bytes = st.session_state['generated_fig'].to_image(format="svg")
            st.download_button(
                label="📥 SVG",
                data=img_bytes,
                file_name="universal_plot.svg",
                mime="image/svg+xml"
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
    - Supports CSV, TXT, NPZ, NPY

    **2. Choose Layout**
    - Select grid arrangement (1×1, 2×2, etc.)
    - Each subplot is configured independently

    **3. Configure Each Subplot**
    - **Enable** the subplot (only Subplot 1 is on by default)
    - Select dataset and plot type
    - **1D plots**: select multiple Y columns — each becomes a separate curve
    - **2D Heatmap**: select X, Y, Z columns; optional log scale
    - **3D Surface/Scatter**: select X, Y, Z columns

    **4. Generate & Interact**
    - Click **"Generate Plot"**
    - **Hover** for exact values
    - **Scroll** to zoom, **drag** to pan
    - **Rotate** 3D plots by click-drag

    **5. Export**
    - **HTML**: Fully interactive (recommended!)
    - **PNG / SVG**: Static images for publications
    """)
