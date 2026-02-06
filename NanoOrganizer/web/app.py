#!/usr/bin/env python3
"""
NanoOrganizer – interactive data-browser (Streamlit).

Run via the console script::

    nanoorganizer-viz

or directly::

    streamlit run NanoOrganizer/web/app.py
"""

# ---------------------------------------------------------------------------
# Agg backend MUST be set before any other matplotlib import
# ---------------------------------------------------------------------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import streamlit as st            # noqa: E402
import numpy as np                # noqa: E402
from pathlib import Path          # noqa: E402
import io                          # noqa: E402

from NanoOrganizer import DataOrganizer                       # noqa: E402
from NanoOrganizer.viz import PLOTTER_REGISTRY                # noqa: E402
from NanoOrganizer.core.run import DEFAULT_LOADERS            # noqa: E402

# ---------------------------------------------------------------------------
# SELECTORS – single source of truth for dynamic parameter controls.
#
# Each row: (data_type, plot_type) → (kwarg_name, label, data_key)
#   kwarg_name  – keyword passed to plotter.plot()
#   label       – text shown in the Streamlit selectbox
#   data_key    – key in the loaded data dict whose values populate the box
#                 Use None for image types; handled separately.
# ---------------------------------------------------------------------------
SELECTORS = {
    ("uvvis",  "spectrum"):   ("time_point",      "Time (s)",        "times"),
    ("uvvis",  "kinetics"):   ("wavelength",      "Wavelength (nm)", "wavelengths"),
    ("saxs",   "profile"):    ("time_point",      "Time (s)",        "times"),
    ("saxs",   "kinetics"):   ("q_value",         "q (1/Å)",         "q"),
    ("waxs",   "pattern"):    ("time_point",      "Time (s)",        "times"),
    ("waxs",   "kinetics"):   ("two_theta_value", "2θ (°)",          "two_theta"),
    ("dls",    "size_dist"):  ("time_point",      "Time (s)",        "times"),
    ("xas",    "xanes"):      ("time_point",      "Time (s)",        "times"),
    ("xas",    "kinetics"):   ("energy",          "Energy (eV)",     "energy"),
    ("saxs2d", "detector"):   ("time_point",      "Time (s)",        "times"),
    ("saxs2d", "azimuthal"):  ("time_point",      "Time (s)",        "times"),
    ("waxs2d", "detector"):   ("time_point",      "Time (s)",        "times"),
    ("waxs2d", "azimuthal"):  ("time_point",      "Time (s)",        "times"),
}

# Color palette for multi-dataset overlay
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
MARKERS = ['o', 's', '^', 'v', 'D', 'p', '*', 'h', '<', '>']
LINESTYLES = ['-', '--', '-.', ':']

# Colormaps for heatmaps and images
COLORMAPS = ['viridis', 'plasma', 'inferno', 'magma', 'cividis',
             'turbo', 'jet', 'hot', 'cool', 'gray', 'bone']

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _auto_detect_demo() -> str:
    """Return the path to the bundled Demo/ directory, or './Demo' as fallback."""
    # When installed as a package the repo root is two levels up from this file
    candidate = Path(__file__).resolve().parent.parent.parent / "Demo"
    if candidate.is_dir():
        return str(candidate)
    return "./Demo"


def _loader_for(run, data_type: str):
    """Return the loader attribute on *run* that matches *data_type*."""
    for attr, key, _ in DEFAULT_LOADERS:
        if key == data_type or attr == data_type:
            return getattr(run, attr, None)
    return None


def _available_data_types(run) -> list:
    """Return loader attribute names that have at least one linked file."""
    available = []
    for attr, _key, _ in DEFAULT_LOADERS:
        loader = getattr(run, attr, None)
        if loader and loader.link.file_paths:
            available.append(attr)
    return available


def _is_image_type(data_type: str) -> bool:
    return data_type in ("sem", "tem")


def _is_heatmap_plot(plot_type: str) -> bool:
    """Check if plot type generates a heatmap/2D image."""
    return plot_type in ("heatmap", "detector")


def _save_fig_to_bytes(fig, format='png', dpi=300):
    """Save matplotlib figure to bytes buffer for download."""
    buf = io.BytesIO()
    fig.savefig(buf, format=format, dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# main app
# ---------------------------------------------------------------------------

st.set_page_config(page_title="NanoOrganizer Viz", layout="wide")
st.title("NanoOrganizer — Data Browser")

# ---- sidebar: data directory & load ----------------------------------------
with st.sidebar:
    st.header("📁 Data Source")
    default_path = _auto_detect_demo()
    data_dir = st.text_input("Data directory", value=default_path)

    if "org" not in st.session_state or st.button("🔄 Load/Reload"):
        try:
            st.session_state["org"] = DataOrganizer.load(data_dir)
            st.session_state.pop("_prev_dir", None)
            st.success("✅ Data loaded!")
        except Exception as exc:
            st.error(f"Failed to load: {exc}")
            st.stop()

    org: DataOrganizer = st.session_state.get("org")
    if org is None:
        st.info("Click **🔄 Load/Reload** to open a data directory.")
        st.stop()

    # ---- run selector (MULTI-SELECT) ----------------------------------------
    st.header("🔬 Run Selection")
    run_keys = org.list_runs()
    if not run_keys:
        st.warning("No runs found in the selected directory.")
        st.stop()

    # Multi-select for comparing multiple runs
    selected_keys = st.multiselect(
        "Select Run(s)",
        run_keys,
        default=[run_keys[0]] if run_keys else [],
        help="Select multiple runs to overlay/compare"
    )

    if not selected_keys:
        st.warning("Please select at least one run.")
        st.stop()

    # Get all selected runs
    selected_runs = [(key, org.get_run(key)) for key in selected_keys]

    # ---- show info for first selected run ----------------------------------
    first_run = selected_runs[0][1]
    meta = first_run.metadata

    with st.expander("📋 First Run Info", expanded=False):
        st.markdown(
            f"- **Project:** {meta.project}\n"
            f"- **Experiment:** {meta.experiment}\n"
            f"- **Run ID:** {meta.run_id}\n"
            f"- **Sample ID:** {meta.sample_id}\n"
            f"- **Temperature:** {meta.reaction_temperature}\n"
            f"- **Chemicals:** "
            + (", ".join(c.name for c in meta.reaction.chemicals)
               if meta.reaction else "—") + "\n"
            f"- **Tags:** {meta.tags}\n"
            f"- **Notes:** {meta.notes}"
        )

    # ---- data-type selector (must be same for all runs) --------------------
    st.header("📊 Data Type & Plot")
    available = _available_data_types(first_run)
    if not available:
        st.warning("No linked data in this run.")
        st.stop()

    selected_dtype = st.selectbox("Data type", available)

    # ---- plot-type selector -------------------------------------------------
    plotter_cls = PLOTTER_REGISTRY.get(selected_dtype)
    if plotter_cls is None:
        st.error(f"No plotter registered for '{selected_dtype}'.")
        st.stop()

    plotter = plotter_cls()
    plot_types = plotter.available_plot_types
    selected_plot_type = st.selectbox("Plot type", plot_types)

    # ---- Plot Controls ------------------------------------------------------
    st.header("⚙️ Plot Controls")

    # Scale controls for non-image plots
    if not _is_image_type(selected_dtype):
        col1, col2 = st.columns(2)
        with col1:
            x_scale = st.radio("X Scale", ["linear", "log"], horizontal=True)
        with col2:
            y_scale = st.radio("Y Scale", ["linear", "log"], horizontal=True)

    # Colormap for heatmaps/2D plots
    if _is_heatmap_plot(selected_plot_type) or _is_image_type(selected_dtype):
        cmap = st.selectbox("Colormap", COLORMAPS, index=0)
    else:
        cmap = None

    # Line style controls for overlay plots (when multiple runs selected)
    if len(selected_keys) > 1 and not _is_image_type(selected_dtype):
        with st.expander("🎨 Line Styles", expanded=False):
            show_markers = st.checkbox("Show markers", value=False)
            line_alpha = st.slider("Line opacity", 0.1, 1.0, 0.8, 0.1)
    else:
        show_markers = False
        line_alpha = 1.0

# ---------------------------------------------------------------------------
# main area
# ---------------------------------------------------------------------------

st.header(f"📈 Visualization: {selected_dtype.upper()} - {selected_plot_type}")

if _is_image_type(selected_dtype):
    # ----- IMAGE BRANCH --------------------------------------------------------
    # For images, show side-by-side comparison if multiple runs selected

    loaders = [getattr(run, selected_dtype) for _, run in selected_runs]

    # Get image indices
    n_files = len(loaders[0].link.file_paths)
    image_idx = st.sidebar.selectbox("Image #", list(range(n_files)))

    # Side-by-side comparison
    if len(selected_keys) > 1:
        st.subheader(f"Side-by-Side Comparison (Image #{image_idx})")
        cols = st.columns(len(selected_keys))

        for idx, (col, (run_key, run)) in enumerate(zip(cols, selected_runs)):
            with col:
                st.markdown(f"**{run_key.split('/')[-1]}**")
                loader = getattr(run, selected_dtype)
                fig, ax = plt.subplots(figsize=(6, 6))
                loader.plot(index=image_idx, ax=ax)
                if cmap:
                    # Re-apply colormap if image was loaded
                    for im in ax.get_images():
                        im.set_cmap(cmap)
                st.pyplot(fig)
                plt.close(fig)
    else:
        # Single image view
        loader = loaders[0]
        fig, ax = plt.subplots(figsize=(10, 10))
        loader.plot(index=image_idx, ax=ax)
        if cmap:
            for im in ax.get_images():
                im.set_cmap(cmap)
        st.pyplot(fig)

        # Export button
        buf = _save_fig_to_bytes(fig)
        st.download_button(
            label="💾 Download Image",
            data=buf,
            file_name=f"{selected_keys[0].replace('/', '_')}_{selected_dtype}_{image_idx}.png",
            mime="image/png"
        )
        plt.close(fig)

    with st.expander("📄 Raw Data"):
        st.info(f"{n_files} image file(s) linked in first run.")
        for fp in loaders[0].link.file_paths[:5]:  # Show first 5
            st.code(fp, language=None)
        if n_files > 5:
            st.text(f"... and {n_files - 5} more files")

else:
    # ----- TIME-SERIES / 2-D DETECTOR BRANCH ------------------------------------

    # Load data from all selected runs
    run_data_pairs = []
    for run_key, run in selected_runs:
        loader = getattr(run, selected_dtype)
        try:
            data = loader.load()
            run_data_pairs.append((run_key, data))
        except Exception as e:
            st.warning(f"Could not load data for {run_key}: {e}")

    if not run_data_pairs:
        st.error("No data could be loaded from selected runs.")
        st.stop()

    # Dynamic selector control (use first dataset's values)
    kwargs = {}
    selector_key = (selected_dtype, selected_plot_type)
    if selector_key in SELECTORS:
        kwarg_name, label, data_key = SELECTORS[selector_key]
        first_data = run_data_pairs[0][1]
        values = first_data[data_key]
        values_list = [round(float(v), 4) for v in values]
        chosen = st.sidebar.selectbox(label, values_list)
        kwargs[kwarg_name] = chosen

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 7))

    # OVERLAY MODE: Plot all datasets on same axes
    if len(run_data_pairs) > 1 and selected_plot_type not in ["heatmap", "detector", "azimuthal"]:
        # Overlay multiple datasets with different colors
        st.info(f"📊 Overlaying {len(run_data_pairs)} datasets")

        for idx, (run_key, data) in enumerate(run_data_pairs):
            color = COLORS[idx % len(COLORS)]
            marker = MARKERS[idx % len(MARKERS)] if show_markers else None
            linestyle = LINESTYLES[idx % len(LINESTYLES)]

            # Create a copy of kwargs and add styling
            plot_kwargs = kwargs.copy()
            plot_kwargs['color'] = color
            plot_kwargs['alpha'] = line_alpha
            plot_kwargs['linewidth'] = 2
            if marker:
                plot_kwargs['marker'] = marker
                plot_kwargs['markersize'] = 6
                plot_kwargs['markevery'] = max(1, len(data.get('times', [])) // 20)
            plot_kwargs['linestyle'] = linestyle
            plot_kwargs['label'] = run_key.split('/')[-1]  # Use run_id as label

            # Plot this dataset
            plotter.plot(data, plot_type=selected_plot_type, ax=ax, **plot_kwargs)

        # Add legend for overlay
        ax.legend(loc='best', framealpha=0.9, fontsize=9)

    else:
        # Single dataset or heatmap-type plot
        first_data = run_data_pairs[0][1]

        # Add colormap for heatmaps
        if cmap and _is_heatmap_plot(selected_plot_type):
            kwargs['cmap'] = cmap

        plotter.plot(first_data, plot_type=selected_plot_type, ax=ax, **kwargs)

        # Apply colormap to existing images if needed
        if cmap and _is_heatmap_plot(selected_plot_type):
            for im in ax.get_images():
                im.set_cmap(cmap)

    # Apply scale settings
    if not _is_image_type(selected_dtype):
        ax.set_xscale(x_scale)
        ax.set_yscale(y_scale)

    # Show plot
    st.pyplot(fig)

    # Export button
    export_filename = f"{selected_keys[0].replace('/', '_')}_{selected_dtype}_{selected_plot_type}.png"
    if len(selected_keys) > 1:
        export_filename = f"overlay_{len(selected_keys)}runs_{selected_dtype}_{selected_plot_type}.png"

    buf = _save_fig_to_bytes(fig, dpi=300)
    st.download_button(
        label="💾 Download Plot (PNG, 300 DPI)",
        data=buf,
        file_name=export_filename,
        mime="image/png"
    )

    plt.close(fig)

    # ----- Raw Data expander ---------------------------------------------------
    with st.expander("📄 Raw Data (First Run)"):
        first_data = run_data_pairs[0][1]
        if "images" in first_data:
            # 2-D detector data
            st.info(
                f"Image stack: {first_data['images'].shape[0]} frames, "
                f"shape {first_data['images'].shape[1]}×{first_data['images'].shape[2]} pixels"
            )
        else:
            # 1-D time-series – find the 2-D array and its axes
            for key, val in first_data.items():
                if isinstance(val, np.ndarray) and val.ndim == 2:
                    import pandas as pd
                    # Show first 10 rows
                    df = pd.DataFrame(val)
                    st.dataframe(df.head(10))
                    st.text(f"Shape: {val.shape}")
                    break

# ----- Full Metadata expander (always visible) --------------------------------
with st.expander("📋 Full Metadata (First Run)"):
    st.json(first_run.to_dict())

# ----- Footer with stats -------------------------------------------------------
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Runs", len(run_keys))
with col2:
    st.metric("Selected Runs", len(selected_keys))
with col3:
    st.metric("Data Types Available", len(available))
