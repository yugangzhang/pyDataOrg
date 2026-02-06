#!/usr/bin/env python3
"""
Universal Plotter - Integrated plotting for 1D, 2D, and 3D data.

Features:
- Create custom grid layouts
- Mix 1D, 2D, and 3D plots in one figure
- Interactive hover to show values (x,y) for 1D, (x,y,z) for 2D/3D
- Plotly-based for full interactivity
- Export as interactive HTML or static PNG/SVG
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from pathlib import Path
import io

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def load_data_file(file_path):
    """Load CSV, TXT, DAT, or NPZ file."""
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
            else:
                return None
        else:
            # CSV/TXT with different delimiters
            df = pd.read_csv(file_path, sep=',')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep='\t')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep=r'\s+')
            return df
    except Exception as e:
        st.error(f"Error loading {path.name}: {e}")
        return None


def browse_directory(base_dir, pattern="*.*"):
    """Browse directory and find files matching pattern."""
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    files = list(base_path.rglob(pattern))
    return [str(f) for f in sorted(files)]


def generate_synthetic_data(func_type, points=100):
    """Generate synthetic data for testing."""
    if func_type == "1D - Sine wave":
        x = np.linspace(0, 4*np.pi, points)
        y = np.sin(x) + 0.1 * np.random.randn(points)
        df = pd.DataFrame({'x': x, 'y': y})
        return df, '1D'

    elif func_type == "1D - Gaussian":
        x = np.linspace(-5, 5, points)
        y = np.exp(-x**2) + 0.05 * np.random.randn(points)
        df = pd.DataFrame({'x': x, 'y': y})
        return df, '1D'

    elif func_type == "2D - Heatmap":
        n = int(np.sqrt(points))
        x = np.linspace(-3, 3, n)
        y = np.linspace(-3, 3, n)
        X, Y = np.meshgrid(x, y)
        Z = np.exp(-(X**2 + Y**2))
        df = pd.DataFrame({
            'x': X.flatten(),
            'y': Y.flatten(),
            'z': Z.flatten()
        })
        return df, '2D'

    elif func_type == "3D - Surface":
        n = int(np.sqrt(points))
        x = np.linspace(-5, 5, n)
        y = np.linspace(-5, 5, n)
        X, Y = np.meshgrid(x, y)
        Z = np.sin(np.sqrt(X**2 + Y**2))
        df = pd.DataFrame({
            'x': X.flatten(),
            'y': Y.flatten(),
            'z': Z.flatten()
        })
        return df, '3D'

    return None, None


def create_1d_plot(df, x_col, y_col, title="", showlegend=True):
    """Create 1D line plot with hover values."""
    trace = go.Scatter(
        x=df[x_col],
        y=df[y_col],
        mode='lines+markers',
        name=title,
        hovertemplate=f'<b>{x_col}</b>: %{{x:.4f}}<br><b>{y_col}</b>: %{{y:.4f}}<extra></extra>',
        marker=dict(size=4),
        line=dict(width=2)
    )
    return trace


def create_2d_plot(df, x_col, y_col, z_col, title=""):
    """Create 2D heatmap with hover values."""
    # Pivot data if needed
    try:
        pivot_df = df.pivot_table(values=z_col, index=y_col, columns=x_col, aggfunc='mean')
        trace = go.Heatmap(
            z=pivot_df.values,
            x=pivot_df.columns,
            y=pivot_df.index,
            colorscale='Viridis',
            hovertemplate=f'<b>{x_col}</b>: %{{x:.4f}}<br><b>{y_col}</b>: %{{y:.4f}}<br><b>{z_col}</b>: %{{z:.4f}}<extra></extra>',
            name=title
        )
    except:
        # If pivot fails, try direct heatmap
        x_unique = sorted(df[x_col].unique())
        y_unique = sorted(df[y_col].unique())
        Z = np.zeros((len(y_unique), len(x_unique)))

        for i, y_val in enumerate(y_unique):
            for j, x_val in enumerate(x_unique):
                mask = (df[x_col] == x_val) & (df[y_col] == y_val)
                if mask.any():
                    Z[i, j] = df.loc[mask, z_col].iloc[0]

        trace = go.Heatmap(
            z=Z,
            x=x_unique,
            y=y_unique,
            colorscale='Viridis',
            hovertemplate=f'<b>{x_col}</b>: %{{x:.4f}}<br><b>{y_col}</b>: %{{y:.4f}}<br><b>{z_col}</b>: %{{z:.4f}}<extra></extra>',
            name=title
        )

    return trace


def create_3d_plot(df, x_col, y_col, z_col, title=""):
    """Create 3D surface plot with hover values."""
    # Reshape data for surface plot
    try:
        pivot_df = df.pivot_table(values=z_col, index=y_col, columns=x_col, aggfunc='mean')
        X, Y = np.meshgrid(pivot_df.columns, pivot_df.index)
        Z = pivot_df.values
    except:
        # Fallback: create grid
        x_unique = sorted(df[x_col].unique())
        y_unique = sorted(df[y_col].unique())
        X, Y = np.meshgrid(x_unique, y_unique)
        Z = np.zeros_like(X)

        for i, y_val in enumerate(y_unique):
            for j, x_val in enumerate(x_unique):
                mask = (df[x_col] == x_val) & (df[y_col] == y_val)
                if mask.any():
                    Z[i, j] = df.loc[mask, z_col].iloc[0]

    trace = go.Surface(
        x=X,
        y=Y,
        z=Z,
        colorscale='Viridis',
        hovertemplate=f'<b>{x_col}</b>: %{{x:.4f}}<br><b>{y_col}</b>: %{{y:.4f}}<br><b>{z_col}</b>: %{{z:.4f}}<extra></extra>',
        name=title
    )

    return trace


# ---------------------------------------------------------------------------
# Initialize session state
# ---------------------------------------------------------------------------

if 'subplot_configs' not in st.session_state:
    st.session_state['subplot_configs'] = {}

if 'loaded_data' not in st.session_state:
    st.session_state['loaded_data'] = {}

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.title("🎯 Universal Plotter")
st.markdown("**Create integrated figures with 1D, 2D, and 3D plots - All interactive with hover values!**")

# ---------------------------------------------------------------------------
# Sidebar: Layout & Data Loading
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📐 Layout Configuration")

    # Grid layout
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
            "1×1 (Single)": (1, 1),
            "1×2 (Horizontal)": (1, 2),
            "2×1 (Vertical)": (2, 1),
            "2×2 (Grid)": (2, 2),
            "1×3": (1, 3),
            "3×1": (3, 1),
            "2×3": (2, 3)
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
        default_dir = str(Path.cwd())
        server_dir = st.text_input("Server directory", value=default_dir)
        pattern = st.text_input("File pattern", value="*.csv")

        if st.button("🔍 Search"):
            found_files = browse_directory(server_dir, pattern)
            st.session_state['found_files'] = found_files

        if 'found_files' in st.session_state and st.session_state['found_files']:
            selected_files = st.multiselect(
                "Select files",
                st.session_state['found_files']
            )

            for file_path in selected_files:
                df = load_data_file(file_path)
                if df is not None:
                    file_name = Path(file_path).name
                    st.session_state['loaded_data'][file_name] = df

    else:  # Generate synthetic
        st.markdown("**Quick test data:**")
        if st.button("🎲 Generate 1D Sine"):
            df, dtype = generate_synthetic_data("1D - Sine wave")
            st.session_state['loaded_data']['Sine Wave'] = df
        if st.button("🎲 Generate 1D Gaussian"):
            df, dtype = generate_synthetic_data("1D - Gaussian")
            st.session_state['loaded_data']['Gaussian'] = df
        if st.button("🎲 Generate 2D Heatmap"):
            df, dtype = generate_synthetic_data("2D - Heatmap")
            st.session_state['loaded_data']['2D Heatmap'] = df
        if st.button("🎲 Generate 3D Surface"):
            df, dtype = generate_synthetic_data("3D - Surface")
            st.session_state['loaded_data']['3D Surface'] = df

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

st.header(f"⚙️ Configure {n_rows}×{n_cols} Layout ({total_subplots} subplot{'s' if total_subplots > 1 else ''})")

# Create tabs for each subplot
subplot_tabs = st.tabs([f"Subplot {i+1}" for i in range(total_subplots)])

subplot_configs = []

for subplot_idx, tab in enumerate(subplot_tabs):
    with tab:
        st.subheader(f"Subplot {subplot_idx + 1}")

        col1, col2 = st.columns([1, 1])

        with col1:
            # Data selection
            data_name = st.selectbox(
                "Data source",
                list(st.session_state['loaded_data'].keys()),
                key=f"data_{subplot_idx}"
            )

            df = st.session_state['loaded_data'][data_name]
            columns = list(df.columns)

            # Plot type
            plot_type = st.selectbox(
                "Plot type",
                ["1D Line", "2D Heatmap", "3D Surface"],
                key=f"plot_type_{subplot_idx}",
                help="1D: line plot, 2D: heatmap, 3D: surface plot"
            )

        with col2:
            # Column selection based on plot type
            if plot_type == "1D Line":
                x_col = st.selectbox("X column", columns, key=f"x_{subplot_idx}")
                y_col = st.selectbox(
                    "Y column",
                    [c for c in columns if c != x_col],
                    key=f"y_{subplot_idx}"
                )
                z_col = None

            elif plot_type == "2D Heatmap":
                x_col = st.selectbox("X column", columns, key=f"x_{subplot_idx}")
                y_col = st.selectbox(
                    "Y column",
                    [c for c in columns if c != x_col],
                    key=f"y_{subplot_idx}"
                )
                z_col = st.selectbox(
                    "Z/Color column",
                    [c for c in columns if c not in [x_col, y_col]],
                    key=f"z_{subplot_idx}"
                )

            else:  # 3D Surface
                x_col = st.selectbox("X column", columns, key=f"x_{subplot_idx}")
                y_col = st.selectbox(
                    "Y column",
                    [c for c in columns if c != x_col],
                    key=f"y_{subplot_idx}"
                )
                z_col = st.selectbox(
                    "Z column",
                    [c for c in columns if c not in [x_col, y_col]],
                    key=f"z_{subplot_idx}"
                )

        # Title
        subplot_title = st.text_input(
            "Subplot title",
            value=f"{data_name}",
            key=f"title_{subplot_idx}"
        )

        # Store configuration
        subplot_configs.append({
            'data_name': data_name,
            'df': df,
            'plot_type': plot_type,
            'x_col': x_col,
            'y_col': y_col,
            'z_col': z_col,
            'title': subplot_title
        })

# ---------------------------------------------------------------------------
# Generate Figure
# ---------------------------------------------------------------------------

st.divider()
st.header("📊 Generated Figure")

if st.button("🎨 Generate Plot", type="primary"):
    # Determine subplot types for layout
    specs = []
    for row in range(n_rows):
        row_specs = []
        for col in range(n_cols):
            idx = row * n_cols + col
            if idx < len(subplot_configs):
                if subplot_configs[idx]['plot_type'] == "3D Surface":
                    row_specs.append({"type": "surface"})
                else:
                    row_specs.append({"type": "xy"})
            else:
                row_specs.append({"type": "xy"})
        specs.append(row_specs)

    # Create subplots
    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        specs=specs,
        subplot_titles=[config['title'] for config in subplot_configs]
    )

    # Add traces
    for idx, config in enumerate(subplot_configs):
        row = idx // n_cols + 1
        col = idx % n_cols + 1

        if config['plot_type'] == "1D Line":
            trace = create_1d_plot(
                config['df'],
                config['x_col'],
                config['y_col'],
                config['title']
            )
            fig.add_trace(trace, row=row, col=col)

            # Update axes
            fig.update_xaxes(title_text=config['x_col'], row=row, col=col)
            fig.update_yaxes(title_text=config['y_col'], row=row, col=col)

        elif config['plot_type'] == "2D Heatmap":
            trace = create_2d_plot(
                config['df'],
                config['x_col'],
                config['y_col'],
                config['z_col'],
                config['title']
            )
            fig.add_trace(trace, row=row, col=col)

            # Update axes
            fig.update_xaxes(title_text=config['x_col'], row=row, col=col)
            fig.update_yaxes(title_text=config['y_col'], row=row, col=col)

        elif config['plot_type'] == "3D Surface":
            trace = create_3d_plot(
                config['df'],
                config['x_col'],
                config['y_col'],
                config['z_col'],
                config['title']
            )
            fig.add_trace(trace, row=row, col=col)

            # Update 3D scene
            scene_name = 'scene' if idx == 0 else f'scene{idx+1}'
            fig.update_scenes(
                {
                    'xaxis_title': config['x_col'],
                    'yaxis_title': config['y_col'],
                    'zaxis_title': config['z_col']
                },
                row=row,
                col=col
            )

    # Update layout
    fig.update_layout(
        height=400 * n_rows,
        showlegend=False,
        title_text="Universal Plotter - Interactive Figure",
        hovermode='closest'
    )

    # Display
    st.plotly_chart(fig, use_container_width=True)

    # Store in session state for export
    st.session_state['generated_fig'] = fig

    st.success("✅ Figure generated! **Hover over any plot to see values (x,y) or (x,y,z)**")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

if 'generated_fig' in st.session_state:
    st.divider()
    st.header("💾 Export")

    col1, col2, col3 = st.columns(3)

    with col1:
        # HTML export
        html_buffer = io.StringIO()
        st.session_state['generated_fig'].write_html(html_buffer)
        html_bytes = html_buffer.getvalue().encode()

        st.download_button(
            label="📥 Download Interactive HTML",
            data=html_bytes,
            file_name="universal_plot.html",
            mime="text/html",
            help="Fully interactive plot - can rotate, zoom, hover"
        )

    with col2:
        # PNG export
        try:
            img_bytes = st.session_state['generated_fig'].to_image(format="png", width=1200, height=800)
            st.download_button(
                label="📥 Download PNG",
                data=img_bytes,
                file_name="universal_plot.png",
                mime="image/png",
                help="High-resolution static image"
            )
        except:
            st.warning("Install kaleido for PNG export: `pip install kaleido`")

    with col3:
        # SVG export
        try:
            img_bytes = st.session_state['generated_fig'].to_image(format="svg")
            st.download_button(
                label="📥 Download SVG",
                data=img_bytes,
                file_name="universal_plot.svg",
                mime="image/svg+xml",
                help="Vector graphics for publications"
            )
        except:
            st.warning("Install kaleido for SVG export: `pip install kaleido`")

# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------

with st.expander("ℹ️ How to Use"):
    st.markdown("""
    ### Universal Plotter Guide

    **1. Load Data (Sidebar)**
    - Upload files, browse server, or generate synthetic data
    - Supports CSV, TXT, NPZ, NPY formats

    **2. Choose Layout**
    - Select grid arrangement (1×1, 2×2, etc.)
    - Configure each subplot independently

    **3. Configure Each Subplot**
    - Select data source
    - Choose plot type (1D, 2D, or 3D)
    - Select columns for X, Y, Z axes
    - Add custom title

    **4. Generate Plot**
    - Click "Generate Plot" button
    - **Hover over any plot to see values!**
    - 1D plots show (x, y)
    - 2D/3D plots show (x, y, z)

    **5. Export**
    - **HTML**: Fully interactive (recommended for sharing!)
    - **PNG**: High-resolution static image
    - **SVG**: Vector graphics for publications

    ### Features
    - ✅ **Interactive hover** - See exact values anywhere
    - ✅ **Mix plot types** - Combine 1D, 2D, 3D in one figure
    - ✅ **Flexible layouts** - From single plot to complex grids
    - ✅ **Full control** - Independent configuration per subplot
    - ✅ **Export options** - Interactive HTML or static images
    """)
