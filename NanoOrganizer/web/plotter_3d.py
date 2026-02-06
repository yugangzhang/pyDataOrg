#!/usr/bin/env python3
"""
3D Plotter - Visualize XYZ data with color as 4th dimension.

Launch with:
    streamlit run NanoOrganizer/web/plotter_3d.py

Use cases:
- Time-series heatmaps viewed as 3D surface (wavelength, time, absorbance + color)
- Spatial data (X, Y, Z + value as color)
- Any 3D volumetric or gridded data
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d import Axes3D  # noqa: E402, F401

import streamlit as st  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pathlib import Path  # noqa: E402
import io  # noqa: E402

# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------
COLORMAPS = ['viridis', 'plasma', 'inferno', 'magma', 'cividis',
             'turbo', 'jet', 'hot', 'cool', 'RdYlBu', 'seismic']

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _save_fig_to_bytes(fig, format='png', dpi=300):
    """Save matplotlib figure to bytes buffer for download."""
    buf = io.BytesIO()
    fig.savefig(buf, format=format, dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    return buf


def load_csv_file(file_path):
    """Load CSV file, try to auto-detect delimiter."""
    try:
        df = pd.read_csv(file_path, sep=',')
        if len(df.columns) == 1:
            df = pd.read_csv(file_path, sep='\t')
        if len(df.columns) == 1:
            df = pd.read_csv(file_path, sep=r'\s+')
        return df
    except Exception as e:
        st.error(f"Error loading {file_path}: {e}")
        return None


def create_meshgrid_from_data(x, y, z):
    """Create meshgrid from scattered or gridded data."""
    # Check if data is already gridded
    unique_x = np.unique(x)
    unique_y = np.unique(y)

    if len(unique_x) * len(unique_y) == len(z):
        # Data is gridded
        X, Y = np.meshgrid(unique_x, unique_y)
        Z = z.reshape(len(unique_y), len(unique_x))
    else:
        # Data is scattered - interpolate to grid
        from scipy.interpolate import griddata
        X, Y = np.meshgrid(
            np.linspace(x.min(), x.max(), 100),
            np.linspace(y.min(), y.max(), 100)
        )
        Z = griddata((x, y), z, (X, Y), method='cubic')

    return X, Y, Z


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="3D Plotter", layout="wide")
st.title("📊 3D Data Plotter")
st.markdown("Visualize XYZ data with color as 4th dimension")

# ---------------------------------------------------------------------------
# Sidebar: Data Input
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 Data Input")

    data_source = st.radio(
        "Data source",
        ["Upload CSV", "Browse server", "Generate synthetic"],
        help="Choose how to load 3D data"
    )

    df = None

    if data_source == "Upload CSV":
        uploaded_file = st.file_uploader(
            "Upload CSV file",
            type=['csv', 'txt', 'dat'],
            help="CSV with columns: X, Y, Z, [Value]"
        )

        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            st.success(f"✅ Loaded {len(df)} rows")

    elif data_source == "Browse server":
        server_dir = st.text_input("Server directory", value=str(Path.cwd()))
        csv_pattern = st.text_input("File pattern", value="*.csv")

        if st.button("🔍 Search"):
            files = list(Path(server_dir).rglob(csv_pattern))
            st.session_state['found_3d_files'] = [str(f) for f in sorted(files)]

        if 'found_3d_files' in st.session_state:
            selected_file = st.selectbox("Select file", st.session_state['found_3d_files'])
            if selected_file:
                df = load_csv_file(selected_file)
                if df is not None:
                    st.success(f"✅ Loaded {len(df)} rows")

    else:  # Generate synthetic
        st.subheader("Synthetic Data Parameters")

        func_type = st.selectbox(
            "Function",
            ["Gaussian", "Ripple", "Saddle", "Volcano"],
            help="Type of 3D surface to generate"
        )

        grid_size = st.slider("Grid size", 20, 200, 50, 10)

        if st.button("🎲 Generate"):
            x = np.linspace(-5, 5, grid_size)
            y = np.linspace(-5, 5, grid_size)
            X, Y = np.meshgrid(x, y)

            if func_type == "Gaussian":
                Z = np.exp(-(X**2 + Y**2) / 10)
            elif func_type == "Ripple":
                Z = np.sin(np.sqrt(X**2 + Y**2))
            elif func_type == "Saddle":
                Z = X**2 - Y**2
            else:  # Volcano
                Z = -np.exp(-(X**2 + Y**2) / 10) + 0.1 * (X**2 + Y**2)

            # Flatten to dataframe
            df = pd.DataFrame({
                'X': X.flatten(),
                'Y': Y.flatten(),
                'Z': Z.flatten()
            })
            st.session_state['synth_df'] = df
            st.success(f"✅ Generated {len(df)} points")

        if 'synth_df' in st.session_state:
            df = st.session_state['synth_df']

    if df is None:
        st.info("👆 Load or generate data to continue")
        st.stop()

    # Column selection
    st.header("📐 Column Selection")

    columns = list(df.columns)

    x_col = st.selectbox("X-axis column", columns, index=0)
    y_col = st.selectbox("Y-axis column", columns, index=min(1, len(columns)-1))
    z_col = st.selectbox("Z-axis column", columns, index=min(2, len(columns)-1))

    # Optional: 4th dimension for color
    use_color_col = st.checkbox("Use 4th dimension for color", value=False)
    if use_color_col and len(columns) > 3:
        color_col = st.selectbox("Color column", columns, index=min(3, len(columns)-1))
    else:
        color_col = None

    # Plot Controls
    st.header("⚙️ Plot Controls")

    plot_type = st.radio(
        "Plot type",
        ["Surface", "Wireframe", "Scatter", "Contour (2D)", "Surface + Contour"],
        help="Type of 3D visualization"
    )

    cmap = st.selectbox("Colormap", COLORMAPS, index=0)

    # View angle
    with st.expander("📐 View Angle", expanded=False):
        elev = st.slider("Elevation", -90, 90, 30, 5)
        azim = st.slider("Azimuth", -180, 180, -60, 5)

    # Style options
    with st.expander("🎨 Style Options", expanded=False):
        alpha = st.slider("Opacity", 0.1, 1.0, 0.8, 0.1)
        if plot_type in ["Wireframe", "Surface + Contour"]:
            line_width = st.slider("Line width", 0.1, 3.0, 0.5, 0.1)
        else:
            line_width = 0.5

        if plot_type == "Scatter":
            marker_size = st.slider("Marker size", 1, 100, 20, 5)
        else:
            marker_size = 20

    # Labels
    with st.expander("📝 Labels", expanded=False):
        plot_title = st.text_input("Title", value="3D Visualization")
        x_label = st.text_input("X-axis label", value=x_col)
        y_label = st.text_input("Y-axis label", value=y_col)
        z_label = st.text_input("Z-axis label", value=z_col)

# ---------------------------------------------------------------------------
# Main Area: 3D Plot
# ---------------------------------------------------------------------------

st.header(f"📈 {plot_type} Plot")

# Extract data
x = df[x_col].values
y = df[y_col].values
z = df[z_col].values

if color_col:
    c = df[color_col].values
else:
    c = z  # Use Z values for color

# Create figure
if plot_type == "Contour (2D)":
    fig, ax = plt.subplots(figsize=(12, 10))
else:
    fig = plt.figure(figsize=(14, 10))
    ax = fig.add_subplot(111, projection='3d')

# Plot based on type
if plot_type == "Surface" or plot_type == "Surface + Contour":
    X, Y, Z = create_meshgrid_from_data(x, y, z)
    surf = ax.plot_surface(X, Y, Z, cmap=cmap, alpha=alpha,
                           linewidth=line_width, antialiased=True)
    fig.colorbar(surf, ax=ax, shrink=0.5, aspect=5)

    if plot_type == "Surface + Contour":
        # Add contour lines on the surface
        ax.contour(X, Y, Z, levels=10, cmap=cmap, linewidths=line_width,
                   offset=Z.min())

elif plot_type == "Wireframe":
    X, Y, Z = create_meshgrid_from_data(x, y, z)
    ax.plot_wireframe(X, Y, Z, color='black', linewidth=line_width, alpha=alpha)

elif plot_type == "Scatter":
    scatter = ax.scatter(x, y, z, c=c, cmap=cmap, s=marker_size, alpha=alpha)
    fig.colorbar(scatter, ax=ax, shrink=0.5, aspect=5)

elif plot_type == "Contour (2D)":
    X, Y, Z = create_meshgrid_from_data(x, y, z)
    contour = ax.contourf(X, Y, Z, levels=20, cmap=cmap, alpha=alpha)
    fig.colorbar(contour, ax=ax)
    ax.contour(X, Y, Z, levels=20, colors='black', linewidths=0.5, alpha=0.3)

# Set labels and title
if plot_type != "Contour (2D)":
    ax.set_xlabel(x_label, fontsize=12, labelpad=10)
    ax.set_ylabel(y_label, fontsize=12, labelpad=10)
    ax.set_zlabel(z_label, fontsize=12, labelpad=10)
    ax.view_init(elev=elev, azim=azim)
else:
    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel(y_label, fontsize=12)

ax.set_title(plot_title, fontsize=14, fontweight='bold', pad=20)

# Show plot
st.pyplot(fig)

# Export options
st.divider()
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    buf = _save_fig_to_bytes(fig, dpi=300)
    st.download_button(
        label="💾 Download Plot (PNG, 300 DPI)",
        data=buf,
        file_name=f"3d_plot_{plot_type.lower().replace(' ', '_')}.png",
        mime="image/png"
    )

with col2:
    buf_svg = _save_fig_to_bytes(fig, format='svg')
    st.download_button(
        label="💾 Download (SVG)",
        data=buf_svg,
        file_name=f"3d_plot_{plot_type.lower().replace(' ', '_')}.svg",
        mime="image/svg+xml"
    )

with col3:
    st.metric("Data Points", len(df))

plt.close(fig)

# ---------------------------------------------------------------------------
# Data Preview & Statistics
# ---------------------------------------------------------------------------

col1, col2 = st.columns(2)

with col1:
    with st.expander("📄 Data Preview"):
        st.dataframe(df.head(20))
        st.text(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")

with col2:
    with st.expander("📊 Statistics"):
        for col in [x_col, y_col, z_col]:
            st.markdown(f"**{col}**")
            st.text(f"Min:  {df[col].min():.4f}")
            st.text(f"Max:  {df[col].max():.4f}")
            st.text(f"Mean: {df[col].mean():.4f}")
            st.text(f"Std:  {df[col].std():.4f}")
            st.divider()

# ---------------------------------------------------------------------------
# Usage Guide
# ---------------------------------------------------------------------------

with st.expander("💡 Usage Guide"):
    st.markdown("""
    ### Data Format
    - **CSV format**: Columns for X, Y, Z, and optionally a 4th column for color values
    - **Gridded data**: Regular grid in X-Y with Z values
    - **Scattered data**: Irregular points will be interpolated to a grid

    ### Plot Types
    - **Surface**: Smooth 3D surface with color mapping
    - **Wireframe**: 3D mesh structure
    - **Scatter**: Individual 3D points
    - **Contour (2D)**: Top-down view with contour lines
    - **Surface + Contour**: Surface with projected contour lines

    ### Tips
    - Adjust view angle (elevation & azimuth) for best perspective
    - Use different colormaps to highlight features
    - Export as SVG for publication-quality vector graphics
    """)
