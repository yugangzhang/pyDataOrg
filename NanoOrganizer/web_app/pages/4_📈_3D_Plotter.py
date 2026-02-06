#!/usr/bin/env python3
"""
3D Plotter - Interactive 3D visualization with Plotly.

Much better than matplotlib - fully interactive, rotatable, zoomable!
"""

import streamlit as st
import numpy as np
import pandas as pd
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from scipy.interpolate import griddata

st.set_page_config(page_title="3D Plotter", page_icon="📈", layout="wide")

st.title("📈 Interactive 3D Plotter (Plotly)")
st.markdown("XYZ + Color dimension - Fully interactive and rotatable!")

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def load_data_file(file_path):
    """Load CSV or NPZ file."""
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
        st.error(f"Error loading {path.name}: {e}")
        return None


def browse_directory(base_dir, pattern="*.csv"):
    """Browse directory and find files."""
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    files = list(base_path.rglob(pattern))
    return [str(f) for f in sorted(files)]


def create_meshgrid_from_data(x, y, z, grid_size=100):
    """Create meshgrid from scattered or gridded data."""
    unique_x = np.unique(x)
    unique_y = np.unique(y)

    if len(unique_x) * len(unique_y) == len(z):
        # Data is already gridded
        X, Y = np.meshgrid(unique_x, unique_y)
        Z = z.reshape(len(unique_y), len(unique_x))
    else:
        # Data is scattered - interpolate to grid
        X, Y = np.meshgrid(
            np.linspace(x.min(), x.max(), grid_size),
            np.linspace(y.min(), y.max(), grid_size)
        )
        Z = griddata((x, y), z, (X, Y), method='cubic')

    return X, Y, Z


# ---------------------------------------------------------------------------
# Sidebar: Data Loading
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 Data Input")

    data_source = st.radio(
        "Data source",
        ["Upload CSV", "Browse server", "Generate synthetic"]
    )

    df = None

    if data_source == "Upload CSV":
        uploaded_file = st.file_uploader(
            "Upload CSV file",
            type=['csv', 'txt', 'dat', 'npz']
        )

        if uploaded_file:
            temp_path = Path(f"/tmp/{uploaded_file.name}")
            with open(temp_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())
            df = load_data_file(str(temp_path))

    elif data_source == "Browse server":
        server_dir = st.text_input("Server directory", value=str(Path.cwd()))
        pattern = st.text_input("File pattern", value="*.csv")

        if st.button("🔍 Search"):
            found_files = browse_directory(server_dir, pattern)
            st.session_state['found_3d_files'] = found_files

        if 'found_3d_files' in st.session_state and st.session_state['found_3d_files']:
            found_files = st.session_state['found_3d_files']
            if found_files:
                st.success(f"Found {len(found_files)} files")
                selected_file = st.selectbox("Select file", found_files)
                if selected_file:
                    df = load_data_file(selected_file)

    else:  # Generate synthetic
        st.subheader("Synthetic Data")

        func_type = st.selectbox(
            "Function",
            ["Gaussian", "Ripple", "Saddle", "Volcano", "Waves", "Mexican Hat"]
        )

        grid_size = st.slider("Grid size", 20, 200, 50, 10)

        if st.button("🎲 Generate"):
            x = np.linspace(-5, 5, grid_size)
            y = np.linspace(-5, 5, grid_size)
            X, Y = np.meshgrid(x, y)

            if func_type == "Gaussian":
                Z = np.exp(-(X**2 + Y**2) / 10)
                H = Z * (X**2 + Y**2)  # Color based on position * height
            elif func_type == "Ripple":
                Z = np.sin(np.sqrt(X**2 + Y**2))
                H = np.cos(np.sqrt(X**2 + Y**2))
            elif func_type == "Saddle":
                Z = X**2 - Y**2
                H = np.abs(X) + np.abs(Y)
            elif func_type == "Volcano":
                Z = -np.exp(-(X**2 + Y**2) / 10) + 0.1 * (X**2 + Y**2)
                H = X**2 + Y**2
            elif func_type == "Waves":
                Z = np.sin(X) * np.cos(Y)
                H = np.cos(X) * np.sin(Y)
            else:  # Mexican Hat
                r = np.sqrt(X**2 + Y**2)
                Z = (1 - r**2) * np.exp(-r**2 / 2)
                H = r

            df = pd.DataFrame({
                'X': X.flatten(),
                'Y': Y.flatten(),
                'Z': Z.flatten(),
                'H': H.flatten()
            })
            st.session_state['synth_df_3d'] = df
            st.success(f"Generated {len(df)} points")

        if 'synth_df_3d' in st.session_state:
            df = st.session_state['synth_df_3d']

    if df is None:
        st.info("👆 Load or generate data")
        st.stop()

    # Column selection
    st.header("📐 Column Selection")

    columns = list(df.columns)

    x_col = st.selectbox("X-axis", columns, index=0)
    y_col = st.selectbox("Y-axis", columns, index=min(1, len(columns)-1))
    z_col = st.selectbox("Z-axis", columns, index=min(2, len(columns)-1))

    use_color = st.checkbox("Use 4th dimension for color", value=len(columns) > 3)
    if use_color and len(columns) > 3:
        color_col = st.selectbox("Color column", columns, index=min(3, len(columns)-1))
    else:
        color_col = None

    # Plot type
    st.header("📊 Plot Type")

    plot_type = st.radio(
        "Type",
        ["Surface", "Scatter 3D", "Contour 3D", "Wireframe", "Mesh"],
        help="All plots are fully interactive!"
    )

    # Colorscale
    st.header("🎨 Style")

    colorscales = ['Viridis', 'Plasma', 'Inferno', 'Magma', 'Cividis',
                  'Turbo', 'Rainbow', 'Jet', 'Hot', 'Cool',
                  'Portland', 'Electric', 'Picnic', 'RdBu', 'Earth']

    colorscale = st.selectbox("Colorscale", colorscales, index=0)

    # Opacity
    opacity = st.slider("Opacity", 0.1, 1.0, 0.9, 0.1)

# ---------------------------------------------------------------------------
# Main Area: 3D Plot
# ---------------------------------------------------------------------------

st.header(f"📊 Interactive 3D Plot: {plot_type}")

# Get data
x = df[x_col].values
y = df[y_col].values
z = df[z_col].values
c = df[color_col].values if color_col else z

# Create figure
fig = go.Figure()

if plot_type == "Surface":
    # Create mesh grid
    X, Y, Z = create_meshgrid_from_data(x, y, z, grid_size=100)

    if color_col:
        C, _, _ = create_meshgrid_from_data(x, y, c, grid_size=100)
    else:
        C = Z

    fig.add_trace(go.Surface(
        x=X, y=Y, z=Z,
        surfacecolor=C,
        colorscale=colorscale,
        opacity=opacity,
        colorbar=dict(title=color_col if color_col else z_col)
    ))

elif plot_type == "Scatter 3D":
    fig.add_trace(go.Scatter3d(
        x=x, y=y, z=z,
        mode='markers',
        marker=dict(
            size=3,
            color=c,
            colorscale=colorscale,
            opacity=opacity,
            colorbar=dict(title=color_col if color_col else z_col)
        )
    ))

elif plot_type == "Contour 3D":
    fig.add_trace(go.Isosurface(
        x=x, y=y, z=z,
        value=c,
        colorscale=colorscale,
        opacity=opacity,
        caps=dict(x_show=False, y_show=False),
        colorbar=dict(title=color_col if color_col else z_col)
    ))

elif plot_type == "Wireframe":
    X, Y, Z = create_meshgrid_from_data(x, y, z, grid_size=50)

    # Create wireframe by adding lines
    for i in range(0, X.shape[0], 2):
        fig.add_trace(go.Scatter3d(
            x=X[i, :], y=Y[i, :], z=Z[i, :],
            mode='lines',
            line=dict(color='blue', width=1),
            showlegend=False
        ))

    for j in range(0, X.shape[1], 2):
        fig.add_trace(go.Scatter3d(
            x=X[:, j], y=Y[:, j], z=Z[:, j],
            mode='lines',
            line=dict(color='blue', width=1),
            showlegend=False
        ))

else:  # Mesh
    X, Y, Z = create_meshgrid_from_data(x, y, z, grid_size=100)

    fig.add_trace(go.Mesh3d(
        x=X.flatten(), y=Y.flatten(), z=Z.flatten(),
        intensity=c,
        colorscale=colorscale,
        opacity=opacity,
        colorbar=dict(title=color_col if color_col else z_col)
    ))

# Update layout
fig.update_layout(
    title=f"{plot_type} Plot: {z_col}",
    scene=dict(
        xaxis_title=x_col,
        yaxis_title=y_col,
        zaxis_title=z_col,
        camera=dict(
            eye=dict(x=1.5, y=1.5, z=1.5)
        )
    ),
    width=1000,
    height=700,
    font=dict(size=12)
)

# Show plot (fully interactive!)
st.plotly_chart(fig, use_container_width=True)

st.info("""
🖱️ **Interactive Controls:**
- **Rotate**: Click and drag
- **Zoom**: Scroll wheel
- **Pan**: Right-click and drag
- **Reset**: Double-click
- **Export**: Click camera icon in toolbar (PNG, SVG, HTML)
""")

# Download options
st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    # Save as HTML (interactive!)
    html_str = fig.to_html(include_plotlyjs='cdn')
    st.download_button(
        label="💾 Download Interactive HTML",
        data=html_str,
        file_name="3d_plot_interactive.html",
        mime="text/html"
    )

with col2:
    # Save as PNG
    try:
        img_bytes = fig.to_image(format="png", width=1200, height=900)
        st.download_button(
            label="💾 Download PNG",
            data=img_bytes,
            file_name="3d_plot.png",
            mime="image/png"
        )
    except:
        st.info("Install kaleido for PNG export: `pip install kaleido`")

with col3:
    st.metric("Data Points", len(df))

# Statistics
with st.expander("📊 Data Statistics"):
    col1, col2, col3 = st.columns(3)

    for col, col_name in zip([col1, col2, col3], [x_col, y_col, z_col]):
        with col:
            st.markdown(f"**{col_name}**")
            vals = df[col_name].values
            st.text(f"Min:  {vals.min():.4f}")
            st.text(f"Max:  {vals.max():.4f}")
            st.text(f"Mean: {vals.mean():.4f}")
            st.text(f"Std:  {vals.std():.4f}")
