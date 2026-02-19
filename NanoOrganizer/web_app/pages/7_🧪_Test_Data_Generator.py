#!/usr/bin/env python3
"""
Test Data Generator - Create comprehensive simulated data for testing.
"""

import streamlit as st
import numpy as np
import pandas as pd
from pathlib import Path
import json
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.floating_button import floating_sidebar_toggle
from components.security import (
    assert_path_allowed,
    initialize_security_context,
    is_path_allowed,
    require_authentication,
)

initialize_security_context()
require_authentication()

st.title("🧪 Test Data Generator")
st.markdown("Create comprehensive simulated data for testing all tools")

# Floating sidebar toggle button (bottom-left)
floating_sidebar_toggle()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Generation Settings")

    output_dir = st.text_input(
        "Output directory",
        value=str(Path.cwd() / "TestData"),
        help="Where to save generated data"
    )
    if output_dir and not is_path_allowed(output_dir, allow_nonexistent=True):
        st.error("Output directory is outside your allowed folders.")

    st.subheader("Data Types")
    generate_csv = st.checkbox("CSV time-series", value=True)
    generate_npz = st.checkbox("NPZ arrays", value=True)
    generate_images = st.checkbox("2D images", value=True)
    generate_stacks = st.checkbox("Image stacks", value=True)
    generate_3d = st.checkbox("3D data", value=True)

    st.subheader("Quantity")
    n_csv_files = st.slider("CSV files", 3, 20, 10)
    n_time_points = st.slider("Time points", 5, 50, 15)
    n_data_points = st.slider("Data points per file", 50, 1000, 200)

# ---------------------------------------------------------------------------
# Generation Functions
# ---------------------------------------------------------------------------

def generate_csv_timeseries(output_dir, n_files, n_points, n_times):
    """Generate CSV time-series data (UV-Vis like)."""
    output_path = Path(output_dir) / "csv_data"
    output_path.mkdir(parents=True, exist_ok=True)

    files_created = []

    for i in range(n_files):
        # Create wavelength array
        wavelength = np.linspace(300, 800, n_points)

        # Create time-dependent spectra with different characteristics
        time_points = np.linspace(0, 300, n_times)

        for t_idx, t in enumerate(time_points):
            # Peak that grows and shifts
            peak_pos = 520 + i * 5 + t * 0.1
            peak_width = 50 + i * 2
            peak_height = 0.5 + i * 0.1 + t * 0.002

            absorbance = peak_height * np.exp(-((wavelength - peak_pos) / peak_width) ** 2)

            # Add noise
            absorbance += np.random.normal(0, 0.02, n_points)

            # Add baseline
            absorbance += 0.1 + wavelength * 0.0001

            # Save
            df = pd.DataFrame({
                'wavelength': wavelength,
                'absorbance': absorbance
            })

            filename = output_path / f"sample_{i+1:02d}_t{t:06.1f}s.csv"
            df.to_csv(filename, index=False)
            files_created.append(str(filename))

    return files_created


def generate_npz_arrays(output_dir, n_files):
    """Generate NPZ files with multiple arrays."""
    output_path = Path(output_dir) / "npz_data"
    output_path.mkdir(parents=True, exist_ok=True)

    files_created = []

    for i in range(n_files):
        # Create correlated X, Y, Z data
        n_points = 200
        x = np.linspace(0, 10, n_points)
        y = np.sin(x + i * 0.5) + np.random.normal(0, 0.1, n_points)
        z = np.cos(x * 2 + i * 0.3) + np.random.normal(0, 0.1, n_points)

        # Save as NPZ
        filename = output_path / f"data_{i+1:02d}.npz"
        np.savez(filename, x=x, y=y, z=z, time=x*30)
        files_created.append(str(filename))

    return files_created


def generate_2d_images(output_dir, n_images):
    """Generate 2D detector images (NPY format)."""
    output_path = Path(output_dir) / "images_2d"
    output_path.mkdir(parents=True, exist_ok=True)

    files_created = []

    for i in range(n_images):
        # Create 2D detector pattern
        size = 512
        x = np.linspace(-5, 5, size)
        y = np.linspace(-5, 5, size)
        X, Y = np.meshgrid(x, y)

        # Radial pattern (SAXS-like)
        R = np.sqrt(X**2 + Y**2)
        pattern = np.exp(-((R - 2 - i*0.2) / 0.5) ** 2) * (1 + 0.3 * np.random.random((size, size)))

        # Add central beam stop
        pattern[R < 0.5] = 0

        # Save
        filename = output_path / f"detector_{i+1:02d}.npy"
        np.save(filename, pattern)
        files_created.append(str(filename))

    return files_created


def generate_image_stacks(output_dir, n_stacks, n_frames=20):
    """Generate 3D image stacks (time-series of 2D images)."""
    output_path = Path(output_dir) / "image_stacks"
    output_path.mkdir(parents=True, exist_ok=True)

    files_created = []

    for i in range(n_stacks):
        size = 256
        stack = np.zeros((n_frames, size, size))

        for frame in range(n_frames):
            # Moving Gaussian peak
            x = np.linspace(-5, 5, size)
            y = np.linspace(-5, 5, size)
            X, Y = np.meshgrid(x, y)

            # Peak moves across frame
            cx = -3 + frame * 0.3
            cy = -2 + frame * 0.2 + i * 0.5
            stack[frame] = np.exp(-((X - cx)**2 + (Y - cy)**2) / 2)

            # Add noise
            stack[frame] += np.random.normal(0, 0.05, (size, size))

        # Save
        filename = output_path / f"stack_{i+1:02d}.npy"
        np.save(filename, stack)
        files_created.append(str(filename))

    return files_created


def generate_3d_data(output_dir, n_files):
    """Generate 3D data for volume/surface plots."""
    output_path = Path(output_dir) / "data_3d"
    output_path.mkdir(parents=True, exist_ok=True)

    files_created = []

    functions = [
        ("gaussian", lambda X, Y: np.exp(-(X**2 + Y**2) / 10)),
        ("ripple", lambda X, Y: np.sin(np.sqrt(X**2 + Y**2))),
        ("saddle", lambda X, Y: X**2 - Y**2),
        ("volcano", lambda X, Y: -np.exp(-(X**2 + Y**2) / 10) + 0.1 * (X**2 + Y**2)),
        ("waves", lambda X, Y: np.sin(X) * np.cos(Y)),
    ]

    for i, (name, func) in enumerate(functions):
        if i >= n_files:
            break

        # Create grid
        grid_size = 100
        x = np.linspace(-5, 5, grid_size)
        y = np.linspace(-5, 5, grid_size)
        X, Y = np.meshgrid(x, y)

        # Generate Z and H (4th dimension for color)
        Z = func(X, Y)
        H = np.gradient(Z)[0]  # Use gradient as color dimension

        # Save as CSV (flattened)
        df = pd.DataFrame({
            'X': X.flatten(),
            'Y': Y.flatten(),
            'Z': Z.flatten(),
            'H': H.flatten()
        })

        filename = output_path / f"{name}_3d.csv"
        df.to_csv(filename, index=False)
        files_created.append(str(filename))

    return files_created


# ---------------------------------------------------------------------------
# Generate Button
# ---------------------------------------------------------------------------

st.divider()

if st.button("🚀 Generate All Test Data", type="primary"):
    try:
        output_path = assert_path_allowed(
            output_dir,
            allow_nonexistent=True,
            path_label="Output directory",
        )
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    with st.spinner("Generating test data..."):
        summary = {}

        # CSV time-series
        if generate_csv:
            with st.status("Generating CSV time-series...", expanded=True) as status:
                files = generate_csv_timeseries(output_path, n_csv_files, n_data_points, n_time_points)
                summary['csv'] = files
                status.update(label=f"✅ Generated {len(files)} CSV files", state="complete")

        # NPZ arrays
        if generate_npz:
            with st.status("Generating NPZ arrays...", expanded=True) as status:
                files = generate_npz_arrays(output_path, n_csv_files)
                summary['npz'] = files
                status.update(label=f"✅ Generated {len(files)} NPZ files", state="complete")

        # 2D images
        if generate_images:
            with st.status("Generating 2D images...", expanded=True) as status:
                files = generate_2d_images(output_path, 10)
                summary['images'] = files
                status.update(label=f"✅ Generated {len(files)} 2D images", state="complete")

        # Image stacks
        if generate_stacks:
            with st.status("Generating image stacks...", expanded=True) as status:
                files = generate_image_stacks(output_path, 5, 20)
                summary['stacks'] = files
                status.update(label=f"✅ Generated {len(files)} image stacks", state="complete")

        # 3D data
        if generate_3d:
            with st.status("Generating 3D data...", expanded=True) as status:
                files = generate_3d_data(output_path, 5)
                summary['3d'] = files
                status.update(label=f"✅ Generated {len(files)} 3D datasets", state="complete")

        # Save summary
        summary_file = output_path / "summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

    st.success(f"✅ All test data generated in: {output_path}")

    # Show summary
    st.divider()
    st.header("📊 Generation Summary")

    total_files = sum(len(files) for files in summary.values())
    st.metric("Total Files", total_files)

    for data_type, files in summary.items():
        with st.expander(f"{data_type.upper()} - {len(files)} files"):
            for file in files[:10]:  # Show first 10
                st.code(file, language=None)
            if len(files) > 10:
                st.text(f"... and {len(files) - 10} more files")

    # Quick test instructions
    st.divider()
    st.info(f"""
    **Next Steps:**

    1. **Test CSV Plotter:**
       - Go to "CSV Plotter" page
       - Browse to: `{output_path}/csv_data`
       - Load some CSV files

    2. **Test Image Viewer:**
       - Go to "Image Viewer" page
       - Browse to: `{output_path}/image_stacks`
       - Load a stack and browse frames

    3. **Test 3D Plotter:**
       - Go to "3D Plotter" page
       - Browse to: `{output_path}/data_3d`
       - Load a 3D dataset

    4. **Test Multi-Axes:**
       - Go to "Multi-Axes" page
       - Load multiple CSV files
       - Create multi-panel figure
    """)

# ---------------------------------------------------------------------------
# Info Section
# ---------------------------------------------------------------------------

st.divider()

with st.expander("📖 About Test Data"):
    st.markdown("""
    ### Generated Data Types

    **1. CSV Time-Series**
    - UV-Vis-like spectral data
    - Multiple samples with different peak positions
    - Time evolution (growth, shifts)
    - Realistic noise

    **2. NPZ Arrays**
    - Multiple correlated arrays (X, Y, Z)
    - Sinusoidal patterns
    - Good for testing multi-column plotting

    **3. 2D Detector Images**
    - SAXS-like radial patterns
    - 512×512 pixels
    - Central beam stop
    - Different ring positions

    **4. Image Stacks**
    - 3D arrays (time × height × width)
    - Moving Gaussian peaks
    - Good for testing frame browsing
    - 256×256 pixels per frame

    **5. 3D Data**
    - X, Y, Z, H (4D) datasets
    - Various mathematical surfaces
    - Gaussian, ripple, saddle, volcano, waves
    - Good for testing 3D plotters

    ### File Structure

    ```
    TestData/
    ├── csv_data/          # Time-series CSVs
    ├── npz_data/          # NPZ arrays
    ├── images_2d/         # 2D detector images
    ├── image_stacks/      # 3D stacks
    ├── data_3d/           # 3D surface data
    └── summary.json       # Generation log
    ```

    ### Use Cases

    - **CSV Plotter**: Use csv_data/ or npz_data/
    - **Image Viewer**: Use images_2d/ or image_stacks/
    - **3D Plotter**: Use data_3d/
    - **Multi-Axes**: Use csv_data/ (multiple files)
    - **Data Viewer**: Create NanoOrganizer project first
    """)
