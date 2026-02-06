#!/usr/bin/env python3
"""
2D Image Viewer - Dedicated tool for viewing 2D images and stacks.

Features:
- Load image stacks (NPY, PNG, TIF, etc.)
- Browse through frames
- Colormap selection
- Intensity adjustment
- Side-by-side comparison
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import streamlit as st  # noqa: E402
import numpy as np  # noqa: E402
from pathlib import Path  # noqa: E402
import io  # noqa: E402

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

COLORMAPS = ['viridis', 'plasma', 'inferno', 'magma', 'cividis',
             'turbo', 'jet', 'hot', 'cool', 'gray', 'bone', 'seismic',
             'RdYlBu', 'RdBu', 'coolwarm']


def load_image(file_path):
    """Load image from various formats."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    try:
        if suffix == '.npy':
            return np.load(file_path)
        elif suffix == '.npz':
            data = np.load(file_path)
            # Return first array
            return data[data.files[0]]
        elif suffix in ['.png', '.jpg', '.jpeg', '.tif', '.tiff']:
            from PIL import Image
            img = Image.open(file_path)
            return np.array(img)
        else:
            st.error(f"Unsupported format: {suffix}")
            return None
    except Exception as e:
        st.error(f"Error loading {path.name}: {e}")
        return None


def browse_directory(base_dir, pattern="*.npy"):
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
# Main App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="2D Image Viewer", layout="wide")
st.title("🖼️ 2D Image Viewer")
st.markdown("Dedicated viewer for 2D images, detector data, and image stacks")

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

    images = {}  # {filename: image_array}
    file_paths = {}

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
                        images[uploaded_file.name] = img
                        file_paths[uploaded_file.name] = uploaded_file.name
                except Exception as e:
                    st.error(f"Error: {e}")

    else:  # Browse server
        server_dir = st.text_input("Server directory", value=str(Path.cwd()))
        pattern = st.text_input("File pattern", value="*.npy",
                               help="e.g., *.npy, *.png, *.tif")

        if st.button("🔍 Search"):
            found_files = browse_directory(server_dir, pattern)
            st.session_state['found_images'] = found_files

        if 'found_images' in st.session_state and st.session_state['found_images']:
            found_files = st.session_state['found_images']
            if found_files:
                st.success(f"Found {len(found_files)} files")

                selected_files = st.multiselect(
                    "Select files",
                    found_files,
                    default=found_files[:min(5, len(found_files))],
                    help="Select image files to load"
                )

                for file_path in selected_files:
                    img = load_image(file_path)
                    if img is not None:
                        file_name = Path(file_path).name
                        images[file_name] = img
                        file_paths[file_name] = file_path

    if not images:
        st.info("👆 Upload or select images to get started")
        st.stop()

    st.success(f"✅ Loaded {len(images)} image(s)")

    # ---------------------------------------------------------------------------
    # Display Controls
    # ---------------------------------------------------------------------------

    st.header("🎨 Display Controls")

    # View mode
    view_mode = st.radio(
        "View mode",
        ["Single image", "Side-by-side comparison", "Grid view"],
        help="How to display images"
    )

    # Colormap
    cmap = st.selectbox("Colormap", COLORMAPS, index=0)

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

    # Aspect ratio
    aspect = st.radio("Aspect ratio", ["equal", "auto"], horizontal=True)

    # Interpolation
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
    # Single image view with frame slider for stacks
    selected_file = st.selectbox("Select image", list(images.keys()))
    img = images[selected_file]

    # Check if it's a stack (3D array)
    if img.ndim == 3:
        st.info(f"Image stack: {img.shape[0]} frames, {img.shape[1]}×{img.shape[2]} pixels")
        frame_idx = st.slider("Frame", 0, img.shape[0]-1, 0)
        img_to_show = img[frame_idx]
    else:
        img_to_show = img

    # Calculate intensity range
    if auto_contrast:
        vmin, vmax = np.percentile(img_to_show, [1, 99])
    else:
        vmin = np.percentile(img_to_show, vmin_pct)
        vmax = np.percentile(img_to_show, vmax_pct)

    # Plot
    fig, ax = plt.subplots(figsize=(12, 10))
    im = ax.imshow(img_to_show, cmap=cmap, vmin=vmin, vmax=vmax,
                   aspect=aspect, interpolation=interpolation)
    ax.set_title(f"{selected_file}", fontsize=14, fontweight='bold')
    plt.colorbar(im, ax=ax, label="Intensity")

    st.pyplot(fig)

    # Export
    buf = _save_fig_to_bytes(fig, dpi=300)
    st.download_button(
        label="💾 Download Image",
        data=buf,
        file_name=f"{Path(selected_file).stem}_display.png",
        mime="image/png"
    )
    plt.close(fig)

    # Statistics
    with st.expander("📊 Statistics"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Shape", f"{img_to_show.shape[0]}×{img_to_show.shape[1]}")
        with col2:
            st.metric("Min", f"{img_to_show.min():.2f}")
        with col3:
            st.metric("Max", f"{img_to_show.max():.2f}")
        with col4:
            st.metric("Mean", f"{img_to_show.mean():.2f}")

elif view_mode == "Side-by-side comparison":
    # Side-by-side comparison
    if len(images) < 2:
        st.warning("Need at least 2 images for comparison")
        st.stop()

    # Select images to compare
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

    # Create figure with subplots
    n_images = len(selected_files)
    cols = st.columns(n_images)

    for idx, (col, file_name) in enumerate(zip(cols, selected_files)):
        with col:
            img = images[file_name]

            # Handle stacks
            if img.ndim == 3:
                frame_idx = st.slider(f"Frame {idx+1}", 0, img.shape[0]-1, 0,
                                     key=f"frame_{idx}")
                img_to_show = img[frame_idx]
            else:
                img_to_show = img

            # Calculate intensity
            if auto_contrast:
                vmin, vmax = np.percentile(img_to_show, [1, 99])
            else:
                vmin = np.percentile(img_to_show, vmin_pct)
                vmax = np.percentile(img_to_show, vmax_pct)

            # Plot
            fig, ax = plt.subplots(figsize=(6, 6))
            im = ax.imshow(img_to_show, cmap=cmap, vmin=vmin, vmax=vmax,
                          aspect=aspect, interpolation=interpolation)
            ax.set_title(Path(file_name).stem, fontsize=10)
            plt.colorbar(im, ax=ax)

            st.pyplot(fig)
            plt.close(fig)

else:  # Grid view
    # Grid view of all images
    n_images = len(images)
    n_cols = st.slider("Columns", 1, 4, min(3, n_images))
    n_rows = (n_images + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4*n_cols, 4*n_rows))
    if n_images == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for idx, (file_name, img) in enumerate(images.items()):
        ax = axes[idx]

        # Handle stacks (take middle frame)
        if img.ndim == 3:
            img_to_show = img[img.shape[0]//2]
        else:
            img_to_show = img

        # Calculate intensity
        if auto_contrast:
            vmin, vmax = np.percentile(img_to_show, [1, 99])
        else:
            vmin = np.percentile(img_to_show, vmin_pct)
            vmax = np.percentile(img_to_show, vmax_pct)

        im = ax.imshow(img_to_show, cmap=cmap, vmin=vmin, vmax=vmax,
                      aspect=aspect, interpolation=interpolation)
        ax.set_title(Path(file_name).stem, fontsize=9)
        ax.axis('off')

    # Hide unused axes
    for idx in range(n_images, len(axes)):
        axes[idx].axis('off')

    plt.tight_layout()
    st.pyplot(fig)

    # Export
    buf = _save_fig_to_bytes(fig, dpi=300)
    st.download_button(
        label="💾 Download Grid",
        data=buf,
        file_name="image_grid.png",
        mime="image/png"
    )
    plt.close(fig)

# ---------------------------------------------------------------------------
# Image Info
# ---------------------------------------------------------------------------

with st.expander("📄 Image Information"):
    for file_name, img in images.items():
        st.subheader(file_name)
        col1, col2, col3 = st.columns(3)

        with col1:
            st.text(f"Shape: {img.shape}")
            st.text(f"Dimensions: {img.ndim}D")

        with col2:
            st.text(f"Data type: {img.dtype}")
            st.text(f"Size: {img.size} pixels")

        with col3:
            st.text(f"Min: {img.min():.4f}")
            st.text(f"Max: {img.max():.4f}")
            st.text(f"Mean: {img.mean():.4f}")

        st.divider()
