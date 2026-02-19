#!/usr/bin/env python3
"""
2D Image Viewer - Dedicated tool for viewing 2D images and stacks.

Features:
- Load image stacks (NPY, PNG, TIF, etc.)
- Browse through frames
- Interactive (Plotly) and Static (Matplotlib) modes
- Log scale display
- Colormap selection
- Intensity adjustment
- Side-by-side comparison
- Export: PNG, SVG, interactive HTML
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402

import streamlit as st  # noqa: E402
import numpy as np  # noqa: E402
from pathlib import Path  # noqa: E402
import io  # noqa: E402
import sys  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.folder_browser import folder_browser  # noqa: E402
from components.floating_button import floating_sidebar_toggle  # noqa: E402
from components.security import (  # noqa: E402
    initialize_security_context,
    require_authentication,
)

# User-mode restriction (set by nanoorganizer_user)
initialize_security_context()
require_authentication()
_user_mode = st.session_state.get("user_mode", False)
_start_dir = st.session_state.get("user_start_dir", None)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLORMAPS = ['viridis', 'plasma', 'inferno', 'magma', 'cividis',
             'turbo', 'jet', 'hot', 'cool', 'gray', 'bone', 'seismic',
             'RdYlBu', 'RdBu', 'coolwarm']

# Matplotlib colormap -> Plotly colorscale name mapping
_PLOTLY_CMAP = {
    'viridis': 'Viridis', 'plasma': 'Plasma', 'inferno': 'Inferno',
    'magma': 'Magma', 'cividis': 'Cividis', 'turbo': 'Turbo',
    'jet': 'Jet', 'hot': 'Hot', 'cool': 'ice', 'gray': 'Greys',
    'bone': 'Greys', 'seismic': 'RdBu', 'RdYlBu': 'RdYlBu',
    'RdBu': 'RdBu', 'coolwarm': 'RdBu',
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def load_image(file_path):
    """Load image from various formats."""
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
            st.error(f"Unsupported format: {suffix}")
            return None
    except Exception as e:
        st.error(f"Error loading {path.name}: {e}")
        return None


def _save_fig_to_bytes(fig, format='png', dpi=300):
    """Save matplotlib figure to bytes buffer."""
    buf = io.BytesIO()
    fig.savefig(buf, format=format, dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    return buf


def prepare_display_data(img, use_log):
    """Apply log10 transform if requested. Returns (display_data, label_suffix)."""
    if not use_log:
        return img.astype(np.float64), ""
    # log10 with floor for zero/negative values
    floor_val = np.min(img[img > 0]) if np.any(img > 0) else 1e-10
    clipped = np.clip(img.astype(np.float64), floor_val, None)
    return np.log10(clipped), " (log₁₀)"


def calc_intensity_range(img, auto_contrast, vmin_pct, vmax_pct):
    """Calculate vmin/vmax from percentiles."""
    if auto_contrast:
        return np.nanpercentile(img, [1, 99])
    return np.nanpercentile(img, vmin_pct), np.nanpercentile(img, vmax_pct)


def get_frame(img, frame_idx=None):
    """Extract single frame from stack or return 2D image as-is."""
    if img.ndim == 3:
        return img[frame_idx if frame_idx is not None else 0]
    return img


def make_plotly_heatmap(display_data, original_data, title, cmap, vmin, vmax,
                        use_log, equal_aspect=True):
    """Create a Plotly heatmap figure with hover showing original intensity."""
    colorscale = _PLOTLY_CMAP.get(cmap, 'Viridis')
    colorbar_title = "log₁₀(I)" if use_log else "Intensity"

    # For Heatmap, customdata must be 3D (M x N x K) — access via %{customdata[0]}
    custom_3d = original_data[:, :, np.newaxis]

    hover_parts = ['x: %{x}', 'y: %{y}']
    if use_log:
        hover_parts.append('Intensity: %{customdata[0]:.4g}')
        hover_parts.append('log₁₀(I): %{z:.3f}')
    else:
        hover_parts.append('Intensity: %{customdata[0]:.4g}')
    hover = '<br>'.join(hover_parts) + '<extra></extra>'

    fig = go.Figure(go.Heatmap(
        z=display_data,
        zmin=vmin,
        zmax=vmax,
        colorscale=colorscale,
        colorbar=dict(title=colorbar_title),
        customdata=custom_3d,
        hovertemplate=hover,
    ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=700,
        hovermode='closest',
    )

    # y-axis: row 0 at top (like imshow origin='upper')
    fig.update_yaxes(autorange='reversed')

    if equal_aspect:
        fig.update_yaxes(scaleanchor='x', scaleratio=1)

    return fig


def make_plotly_grid(image_list, name_list, cmap, use_log, auto_contrast,
                     vmin_pct, vmax_pct, n_cols):
    """Create Plotly subplots grid of heatmaps."""
    n = len(image_list)
    n_rows = (n + n_cols - 1) // n_cols
    colorscale = _PLOTLY_CMAP.get(cmap, 'Viridis')

    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        subplot_titles=name_list,
        horizontal_spacing=0.05,
        vertical_spacing=0.08,
    )

    for idx, (img, name) in enumerate(zip(image_list, name_list)):
        row = idx // n_cols + 1
        col = idx % n_cols + 1

        display_data, _ = prepare_display_data(img, use_log)
        vmin, vmax = calc_intensity_range(display_data, auto_contrast, vmin_pct, vmax_pct)

        # customdata must be 3D for Heatmap
        custom_3d = img.astype(np.float64)[:, :, np.newaxis]

        fig.add_trace(
            go.Heatmap(
                z=display_data,
                zmin=vmin, zmax=vmax,
                colorscale=colorscale,
                customdata=custom_3d,
                hovertemplate=(
                    f'<b>{name}</b><br>'
                    'x: %{x}  y: %{y}<br>'
                    'Intensity: %{customdata[0]:.4g}<extra></extra>'
                ),
                showscale=(idx == 0),
            ),
            row=row, col=col,
        )

        # y-axis reversed for image convention
        fig.update_yaxes(autorange='reversed', row=row, col=col)
        fig.update_yaxes(scaleanchor=f'x{idx+1 if idx > 0 else ""}',
                         scaleratio=1, row=row, col=col)

    fig.update_layout(
        height=max(400, 350 * n_rows),
        hovermode='closest',
    )

    return fig


def export_section_plotly(fig, file_stem):
    """Render Plotly export buttons."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        html_buffer = io.StringIO()
        fig.write_html(html_buffer)
        html_bytes = html_buffer.getvalue().encode()
        st.download_button(
            label="💾 HTML (interactive)",
            data=html_bytes,
            file_name=f"{file_stem}.html",
            mime="text/html",
            help="Interactive plot — zoom, pan, hover preserved!"
        )

    with col2:
        try:
            img_bytes = fig.to_image(format="png", width=1200, height=900)
            st.download_button(
                label="💾 PNG",
                data=img_bytes,
                file_name=f"{file_stem}.png",
                mime="image/png"
            )
        except Exception:
            st.info("Install kaleido for PNG export")

    with col3:
        try:
            img_bytes = fig.to_image(format="svg")
            st.download_button(
                label="💾 SVG",
                data=img_bytes,
                file_name=f"{file_stem}.svg",
                mime="image/svg+xml"
            )
        except Exception:
            st.info("Install kaleido for SVG export")

    with col4:
        st.metric("Mode", "Interactive")


def export_section_matplotlib(mpl_fig, file_stem):
    """Render Matplotlib export buttons."""
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        buf = _save_fig_to_bytes(mpl_fig, dpi=300)
        st.download_button(
            label="💾 PNG (300 DPI)",
            data=buf,
            file_name=f"{file_stem}.png",
            mime="image/png"
        )

    with col2:
        buf_svg = _save_fig_to_bytes(mpl_fig, format='svg')
        st.download_button(
            label="💾 SVG",
            data=buf_svg,
            file_name=f"{file_stem}.svg",
            mime="image/svg+xml"
        )

    with col3:
        st.metric("Mode", "Static")


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.title("🖼️ 2D Image Viewer")
st.markdown("Dedicated viewer for 2D images, detector data, and image stacks")

# Floating sidebar toggle button (bottom-left)
floating_sidebar_toggle()

# Session state for persistent data
if 'images_viewer' not in st.session_state:
    st.session_state['images_viewer'] = {}
if 'image_paths_viewer' not in st.session_state:
    st.session_state['image_paths_viewer'] = {}

# ---------------------------------------------------------------------------
# Sidebar: Load Images
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 Load Images")

    data_source = st.radio(
        "Data source",
        ["Upload files", "Browse server"],
        help="Upload images or browse server filesystem"
    )

    if data_source == "Upload files":
        uploaded_files = st.file_uploader(
            "Upload image files",
            type=['npy', 'npz', 'png', 'jpg', 'jpeg', 'tif', 'tiff'],
            accept_multiple_files=True,
            help="Upload NPY, NPZ, PNG, TIFF, or JPG files"
        )

        if uploaded_files:
            for uploaded_file in uploaded_files:
                try:
                    temp_path = Path(f"/tmp/{uploaded_file.name}")
                    with open(temp_path, 'wb') as f:
                        f.write(uploaded_file.getbuffer())

                    img = load_image(str(temp_path))
                    if img is not None:
                        st.session_state['images_viewer'][uploaded_file.name] = img
                        st.session_state['image_paths_viewer'][uploaded_file.name] = uploaded_file.name
                except Exception as e:
                    st.error(f"Error: {e}")

    else:  # Browse server
        st.markdown("**🗂️ Interactive Folder Browser**")
        st.markdown("Click folders to navigate, select files with checkboxes:")

        # File pattern selector
        st.markdown("**📋 File Type Filter:**")
        pattern = st.selectbox(
            "Extension pattern",
            ["*.*", "*.npy", "*.npz", "*.png", "*.tif", "*.tiff", "*.jpg"],
            help="Filter files by extension",
            label_visibility="collapsed"
        )

        st.info("💡 Tip: Use '🔍 Advanced Filters' below for name-based filtering")

        # Use folder browser component
        selected_files = folder_browser(
            key="image_viewer_browser",
            show_files=True,
            file_pattern=pattern,
            multi_select=True,
            initial_path=_start_dir if _user_mode else None,
            restrict_to_start_dir=_user_mode,
        )

        # Load button
        if selected_files and st.button("📥 Load Selected Files", key="img_load_btn"):
            for full_path in selected_files:
                img = load_image(full_path)
                if img is not None:
                    file_name = Path(full_path).name
                    st.session_state['images_viewer'][file_name] = img
                    st.session_state['image_paths_viewer'][file_name] = full_path
                    st.success(f"✅ Loaded {file_name}")

    # Get images from session state
    images = st.session_state['images_viewer']
    file_paths = st.session_state['image_paths_viewer']

    # Clear button
    if images:
        if st.button("🗑️ Clear All Images", key="clear_img_data"):
            st.session_state['images_viewer'] = {}
            st.session_state['image_paths_viewer'] = {}
            st.rerun()

    if not images:
        st.info("👆 Upload or select images to get started")
        st.stop()

    st.success(f"✅ Loaded {len(images)} image(s)")

    # -----------------------------------------------------------------------
    # Display Controls
    # -----------------------------------------------------------------------

    st.header("🎨 Display Controls")

    # Plot mode
    plot_mode = st.radio(
        "Plot mode",
        ["Interactive (Plotly)", "Static (Matplotlib)"],
        horizontal=True,
        help="Plotly: hover values, zoom, pan. Matplotlib: publication-ready static."
    )
    use_plotly = plot_mode.startswith("Interactive")

    # View mode
    view_mode = st.radio(
        "View mode",
        ["Single image", "Side-by-side comparison", "Grid view"],
        help="How to display images"
    )

    # Colormap
    cmap = st.selectbox("Colormap", COLORMAPS, index=0)

    # Log scale
    use_log_scale = st.checkbox(
        "Log scale",
        value=False,
        help="Display log₁₀(intensity). Useful for data with large dynamic range (e.g. diffraction)."
    )

    # Intensity controls
    with st.expander("🔆 Intensity", expanded=True):
        auto_contrast = st.checkbox("Auto contrast", value=True,
                                    help="Automatically adjust intensity range")

        if not auto_contrast:
            vmin_pct = st.slider("Min percentile", 0.0, 50.0, 0.0, 0.5,
                                help="Lower intensity cutoff (percentile)")
            vmax_pct = st.slider("Max percentile", 50.0, 100.0, 100.0, 0.5,
                                help="Upper intensity cutoff (percentile)")
        else:
            vmin_pct = 0.0
            vmax_pct = 100.0

    # Matplotlib-only controls
    if not use_plotly:
        aspect = st.radio("Aspect ratio", ["equal", "auto"], horizontal=True)
        interpolation = st.selectbox(
            "Interpolation",
            ["nearest", "bilinear", "bicubic", "gaussian"],
            index=0,
            help="Image interpolation method"
        )

# ---------------------------------------------------------------------------
# Main Area: Display Images
# ---------------------------------------------------------------------------

st.header("📊 Image Display")

if view_mode == "Single image":
    # ----- Single image view -----
    selected_file = st.selectbox("Select image", list(images.keys()))
    img_raw = images[selected_file]

    # Handle stacks
    if img_raw.ndim == 3:
        st.info(f"Image stack: {img_raw.shape[0]} frames, "
                f"{img_raw.shape[1]}×{img_raw.shape[2]} pixels")
        frame_idx = st.slider("Frame", 0, img_raw.shape[0] - 1, 0)
        img_frame = img_raw[frame_idx]
    else:
        img_frame = img_raw

    # Prepare display data
    display_data, label_suffix = prepare_display_data(img_frame, use_log_scale)
    vmin, vmax = calc_intensity_range(display_data, auto_contrast, vmin_pct, vmax_pct)
    file_stem = Path(selected_file).stem

    if use_plotly:
        fig = make_plotly_heatmap(
            display_data, img_frame.astype(np.float64),
            title=selected_file,
            cmap=cmap, vmin=vmin, vmax=vmax,
            use_log=use_log_scale,
            equal_aspect=True,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.success("**Hover** to see intensity values. **Scroll** to zoom. **Drag** to pan.")

        # Export
        st.divider()
        export_section_plotly(fig, f"{file_stem}_display")

    else:
        mpl_fig, ax = plt.subplots(figsize=(12, 10))
        if use_log_scale:
            im = ax.imshow(img_frame.astype(np.float64), cmap=cmap,
                           norm=mcolors.LogNorm(vmin=max(vmin, 1e-10), vmax=vmax),
                           aspect=aspect, interpolation=interpolation)
        else:
            im = ax.imshow(display_data, cmap=cmap, vmin=vmin, vmax=vmax,
                           aspect=aspect, interpolation=interpolation)
        ax.set_title(selected_file, fontsize=14, fontweight='bold')
        plt.colorbar(im, ax=ax, label=f"Intensity{label_suffix}")

        st.pyplot(mpl_fig)

        # Export
        st.divider()
        export_section_matplotlib(mpl_fig, f"{file_stem}_display")
        plt.close(mpl_fig)

    # Statistics
    with st.expander("📊 Statistics"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Shape", f"{img_frame.shape[0]}×{img_frame.shape[1]}")
        with col2:
            st.metric("Min", f"{img_frame.min():.2f}")
        with col3:
            st.metric("Max", f"{img_frame.max():.2f}")
        with col4:
            st.metric("Mean", f"{img_frame.mean():.2f}")

elif view_mode == "Side-by-side comparison":
    # ----- Side-by-side comparison -----
    if len(images) < 2:
        st.warning("Need at least 2 images for comparison")
        st.stop()

    selected_files = st.multiselect(
        "Select images to compare",
        list(images.keys()),
        default=list(images.keys())[:min(4, len(images))],
        help="Select 2-4 images"
    )

    if len(selected_files) < 2:
        st.info("Select at least 2 images")
        st.stop()

    if len(selected_files) > 4:
        st.warning("Maximum 4 images for side-by-side. Showing first 4.")
        selected_files = selected_files[:4]

    n_images = len(selected_files)

    # Collect frames (with optional per-image frame slider)
    frames = []
    names = []
    frame_cols = st.columns(n_images)
    for idx, file_name in enumerate(selected_files):
        img_raw = images[file_name]
        with frame_cols[idx]:
            if img_raw.ndim == 3:
                fi = st.slider(f"Frame: {Path(file_name).stem}",
                               0, img_raw.shape[0] - 1, 0,
                               key=f"sbs_frame_{idx}")
                frames.append(img_raw[fi])
            else:
                frames.append(img_raw)
        names.append(Path(file_name).stem)

    if use_plotly:
        fig = make_plotly_grid(frames, names, cmap, use_log_scale,
                               auto_contrast, vmin_pct, vmax_pct, n_cols=n_images)
        st.plotly_chart(fig, use_container_width=True)
        st.success("**Hover** for intensity. **Scroll** to zoom. **Drag** to pan.")

        st.divider()
        export_section_plotly(fig, "comparison")

    else:
        cols = st.columns(n_images)
        for idx, (col, img_frame, name) in enumerate(zip(cols, frames, names)):
            with col:
                display_data, _ = prepare_display_data(img_frame, use_log_scale)
                vmin, vmax = calc_intensity_range(display_data, auto_contrast,
                                                  vmin_pct, vmax_pct)
                mpl_fig, ax = plt.subplots(figsize=(6, 6))
                if use_log_scale:
                    im = ax.imshow(img_frame.astype(np.float64), cmap=cmap,
                                   norm=mcolors.LogNorm(vmin=max(vmin, 1e-10), vmax=vmax),
                                   aspect=aspect, interpolation=interpolation)
                else:
                    im = ax.imshow(display_data, cmap=cmap, vmin=vmin, vmax=vmax,
                                   aspect=aspect, interpolation=interpolation)
                ax.set_title(name, fontsize=10)
                plt.colorbar(im, ax=ax)
                st.pyplot(mpl_fig)
                plt.close(mpl_fig)

else:  # Grid view
    # ----- Grid view of all images -----
    n_images = len(images)
    n_cols_grid = st.slider("Columns", 1, 4, min(3, n_images))

    # Collect frames (middle frame for stacks)
    grid_frames = []
    grid_names = []
    for file_name, img_raw in images.items():
        if img_raw.ndim == 3:
            grid_frames.append(img_raw[img_raw.shape[0] // 2])
        else:
            grid_frames.append(img_raw)
        grid_names.append(Path(file_name).stem)

    if use_plotly:
        fig = make_plotly_grid(grid_frames, grid_names, cmap, use_log_scale,
                               auto_contrast, vmin_pct, vmax_pct, n_cols=n_cols_grid)
        st.plotly_chart(fig, use_container_width=True)
        st.success("**Hover** for intensity. **Scroll** to zoom. **Drag** to pan.")

        st.divider()
        export_section_plotly(fig, "image_grid")

    else:
        n_rows = (n_images + n_cols_grid - 1) // n_cols_grid
        mpl_fig, axes = plt.subplots(n_rows, n_cols_grid,
                                     figsize=(4 * n_cols_grid, 4 * n_rows))
        if n_images == 1:
            axes = np.array([axes])
        axes = np.array(axes).flatten()

        for idx, (img_frame, name) in enumerate(zip(grid_frames, grid_names)):
            ax = axes[idx]
            display_data, _ = prepare_display_data(img_frame, use_log_scale)
            vmin, vmax = calc_intensity_range(display_data, auto_contrast,
                                              vmin_pct, vmax_pct)
            if use_log_scale:
                im = ax.imshow(img_frame.astype(np.float64), cmap=cmap,
                               norm=mcolors.LogNorm(vmin=max(vmin, 1e-10), vmax=vmax),
                               aspect=aspect, interpolation=interpolation)
            else:
                im = ax.imshow(display_data, cmap=cmap, vmin=vmin, vmax=vmax,
                               aspect=aspect, interpolation=interpolation)
            ax.set_title(name, fontsize=9)
            ax.axis('off')

        for idx in range(n_images, len(axes)):
            axes[idx].axis('off')

        plt.tight_layout()
        st.pyplot(mpl_fig)

        st.divider()
        export_section_matplotlib(mpl_fig, "image_grid")
        plt.close(mpl_fig)

# ---------------------------------------------------------------------------
# Image Info
# ---------------------------------------------------------------------------

with st.expander("📄 Image Information"):
    for file_name, img_raw in images.items():
        st.subheader(file_name)
        col1, col2, col3 = st.columns(3)

        with col1:
            st.text(f"Shape: {img_raw.shape}")
            st.text(f"Dimensions: {img_raw.ndim}D")

        with col2:
            st.text(f"Data type: {img_raw.dtype}")
            st.text(f"Size: {img_raw.size} pixels")

        with col3:
            st.text(f"Min: {img_raw.min():.4f}")
            st.text(f"Max: {img_raw.max():.4f}")
            st.text(f"Mean: {img_raw.mean():.4f}")

        st.divider()
