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
import sys                         # noqa: E402
import copy                        # noqa: E402
import pprint                      # noqa: E402

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.floating_button import floating_sidebar_toggle  # noqa: E402
from components.security import (  # noqa: E402
    assert_path_allowed,
    initialize_security_context,
    is_path_allowed,
    require_authentication,
)

from NanoOrganizer import DataOrganizer                       # noqa: E402
from NanoOrganizer.viz import PLOTTER_REGISTRY                # noqa: E402
from NanoOrganizer.core.run import DEFAULT_LOADERS            # noqa: E402

initialize_security_context()
require_authentication()

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
SCALE_OPTIONS = ["linear", "log"]

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


def _to_bool(value, default=False):
    """Convert arbitrary values to bool with fallback."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _to_float(value, default, min_value=None, max_value=None):
    """Convert arbitrary values to float with optional clamp."""
    fallback = 0.0 if default is None else default
    try:
        parsed = float(value)
    except Exception:
        try:
            parsed = float(fallback)
        except Exception:
            parsed = 0.0
    if min_value is not None:
        parsed = max(parsed, min_value)
    if max_value is not None:
        parsed = min(parsed, max_value)
    return parsed


def _to_int(value, default, min_value=None, max_value=None):
    """Convert arbitrary values to int with optional clamp."""
    fallback = 0 if default is None else default
    try:
        parsed = int(value)
    except Exception:
        try:
            parsed = int(fallback)
        except Exception:
            parsed = 0
    if min_value is not None:
        parsed = max(parsed, min_value)
    if max_value is not None:
        parsed = min(parsed, max_value)
    return parsed


def _build_data_viewer_plot_spec(data_dir, selected_keys, selected_dtype, selected_plot_type,
                                 x_scale, y_scale, cmap, show_markers, line_alpha,
                                 image_idx, selector_value):
    """Build serializable Data Viewer config from current UI state."""
    return {
        "version": 1,
        "data_dir": str(data_dir),
        "selected_runs": [str(k) for k in selected_keys],
        "data_type": str(selected_dtype),
        "plot_type": str(selected_plot_type),
        "x_scale": str(x_scale),
        "y_scale": str(y_scale),
        "cmap": cmap if cmap in COLORMAPS else None,
        "show_markers": bool(show_markers),
        "line_alpha": float(line_alpha),
        "image_idx": int(image_idx),
        "selector_value": selector_value,
    }


def _generate_data_viewer_editor_python(plot_spec):
    """Generate editable Python code for Data Viewer config."""
    spec_text = pprint.pformat(plot_spec, sort_dicts=False, width=100, compact=False)
    return (
        "# NanoOrganizer Data Viewer editor (experimental)\n"
        "# Edit plot_spec and click 'Run Edited Python'.\n"
        "# The app uses `result` (if defined) otherwise `plot_spec`.\n\n"
        f"plot_spec = {spec_text}\n\n"
        "# Example tweaks:\n"
        "# plot_spec['x_scale'] = 'log'\n"
        "# plot_spec['show_markers'] = True\n\n"
        "result = plot_spec\n"
    )


def _sanitize_data_viewer_plot_spec(candidate, fallback_spec, run_keys,
                                    available_dtypes, plot_types, selector_values):
    """Sanitize edited Data Viewer spec and return (spec, warnings)."""
    warnings = []
    if not isinstance(candidate, dict):
        warnings.append("Edited code did not return a dict; keeping previous settings.")
        return copy.deepcopy(fallback_spec), warnings

    normalized = copy.deepcopy(fallback_spec)
    proposed_data_dir = str(candidate.get("data_dir", normalized["data_dir"]))
    if is_path_allowed(proposed_data_dir, allow_nonexistent=True):
        normalized["data_dir"] = proposed_data_dir
    elif "data_dir" in candidate:
        warnings.append("Ignored data_dir outside allowed folders.")

    selected_runs = candidate.get("selected_runs", normalized.get("selected_runs", []))
    if isinstance(selected_runs, str):
        selected_runs = [selected_runs]
    if not isinstance(selected_runs, (list, tuple, set)):
        selected_runs = []
    run_valid = []
    for run_key in selected_runs:
        run_key = str(run_key)
        if run_key in run_keys and run_key not in run_valid:
            run_valid.append(run_key)
    if not run_valid and run_keys:
        run_valid = [run_keys[0]]
        warnings.append("No valid runs selected in script; defaulted to first run.")
    normalized["selected_runs"] = run_valid

    dtype = candidate.get("data_type", normalized.get("data_type"))
    if dtype in available_dtypes:
        normalized["data_type"] = dtype
    elif "data_type" in candidate:
        warnings.append(f"Ignored unsupported data_type '{dtype}'.")

    plot_type = candidate.get("plot_type", normalized.get("plot_type"))
    if plot_type in plot_types:
        normalized["plot_type"] = plot_type
    elif "plot_type" in candidate:
        warnings.append(f"Ignored unsupported plot_type '{plot_type}'.")

    x_scale = candidate.get("x_scale", normalized.get("x_scale", SCALE_OPTIONS[0]))
    y_scale = candidate.get("y_scale", normalized.get("y_scale", SCALE_OPTIONS[0]))
    normalized["x_scale"] = x_scale if x_scale in SCALE_OPTIONS else SCALE_OPTIONS[0]
    normalized["y_scale"] = y_scale if y_scale in SCALE_OPTIONS else SCALE_OPTIONS[0]

    cmap = candidate.get("cmap", normalized.get("cmap"))
    normalized["cmap"] = cmap if cmap in COLORMAPS else None

    normalized["show_markers"] = _to_bool(candidate.get("show_markers", normalized.get("show_markers", False)), False)
    normalized["line_alpha"] = _to_float(candidate.get("line_alpha", normalized.get("line_alpha", 0.8)), 0.8, 0.1, 1.0)
    normalized["image_idx"] = _to_int(candidate.get("image_idx", normalized.get("image_idx", 0)), 0, 0, 10**6)

    selector_value = candidate.get("selector_value", normalized.get("selector_value"))
    if selector_values:
        if selector_value in selector_values:
            normalized["selector_value"] = selector_value
        else:
            normalized["selector_value"] = selector_values[0]
            if "selector_value" in candidate:
                warnings.append("selector_value was not in allowed values; defaulted to first option.")
    else:
        normalized["selector_value"] = selector_value

    return normalized, warnings


def _apply_data_viewer_plot_spec_to_state(plot_spec):
    """Apply sanitized Data Viewer config to session state."""
    proposed_data_dir = str(plot_spec.get("data_dir", st.session_state.get("dv_data_dir", "")))
    if is_path_allowed(proposed_data_dir, allow_nonexistent=True):
        st.session_state["dv_data_dir"] = proposed_data_dir
    st.session_state["dv_selected_runs"] = list(plot_spec.get("selected_runs", st.session_state.get("dv_selected_runs", [])))
    st.session_state["dv_selected_dtype"] = plot_spec.get("data_type", st.session_state.get("dv_selected_dtype"))
    st.session_state["dv_selected_plot_type"] = plot_spec.get("plot_type", st.session_state.get("dv_selected_plot_type"))
    st.session_state["dv_x_scale"] = plot_spec.get("x_scale", st.session_state.get("dv_x_scale", SCALE_OPTIONS[0]))
    st.session_state["dv_y_scale"] = plot_spec.get("y_scale", st.session_state.get("dv_y_scale", SCALE_OPTIONS[0]))
    st.session_state["dv_cmap"] = plot_spec.get("cmap", st.session_state.get("dv_cmap"))
    st.session_state["dv_show_markers"] = _to_bool(plot_spec.get("show_markers", st.session_state.get("dv_show_markers", False)), False)
    st.session_state["dv_line_alpha"] = _to_float(plot_spec.get("line_alpha", st.session_state.get("dv_line_alpha", 0.8)), 0.8, 0.1, 1.0)
    st.session_state["dv_image_idx"] = _to_int(plot_spec.get("image_idx", st.session_state.get("dv_image_idx", 0)), 0, 0, 10**6)
    st.session_state["dv_selector_value"] = plot_spec.get("selector_value", st.session_state.get("dv_selector_value"))


def _execute_data_viewer_editor(code_text, base_plot_spec, run_keys, available_dtypes,
                                plot_types, selector_values):
    """Execute editor code and sanitize returned Data Viewer spec."""
    execution_locals = {
        "plot_spec": copy.deepcopy(base_plot_spec),
        "result": None,
        "run_keys": list(run_keys),
        "available_data_types": list(available_dtypes),
        "available_plot_types": list(plot_types),
        "selector_values": list(selector_values),
        "copy": copy,
    }
    exec(code_text, {"__builtins__": __builtins__}, execution_locals)
    candidate = execution_locals.get("result")
    if candidate is None:
        candidate = execution_locals.get("plot_spec")
    return _sanitize_data_viewer_plot_spec(
        candidate, base_plot_spec, run_keys, available_dtypes, plot_types, selector_values
    )


# ---------------------------------------------------------------------------
# main app
# ---------------------------------------------------------------------------

st.title("NanoOrganizer — Data Browser")

# Floating sidebar toggle button (bottom-left)
floating_sidebar_toggle()

default_path = _auto_detect_demo()
if not is_path_allowed(default_path, allow_nonexistent=True):
    default_path = st.session_state.get("user_start_dir", str(Path.cwd()))
st.session_state.setdefault("dv_data_dir", default_path)
st.session_state.setdefault("dv_selected_runs", [])
st.session_state.setdefault("dv_selected_dtype", None)
st.session_state.setdefault("dv_selected_plot_type", None)
st.session_state.setdefault("dv_x_scale", SCALE_OPTIONS[0])
st.session_state.setdefault("dv_y_scale", SCALE_OPTIONS[0])
st.session_state.setdefault("dv_cmap", COLORMAPS[0])
st.session_state.setdefault("dv_show_markers", False)
st.session_state.setdefault("dv_line_alpha", 0.8)
st.session_state.setdefault("dv_image_idx", 0)
st.session_state.setdefault("dv_selector_value", None)
st.session_state.setdefault("dv_editor_code", "")
st.session_state.setdefault("dv_editor_status", "")
st.session_state.setdefault("dv_editor_warnings", [])

# ---- sidebar: data directory & load ----------------------------------------
with st.sidebar:
    st.header("📁 Data Source")

    if "dv_pending_plot_spec" in st.session_state:
        pending_spec = st.session_state.pop("dv_pending_plot_spec")
        _apply_data_viewer_plot_spec_to_state(pending_spec)

    data_dir = st.text_input("Data directory", key="dv_data_dir")
    if data_dir and not is_path_allowed(data_dir, allow_nonexistent=True):
        st.error("Data directory is outside your allowed folders.")

    if "org" not in st.session_state or st.button("🔄 Load/Reload"):
        try:
            safe_data_dir = assert_path_allowed(data_dir, path_label="Data directory")
            st.session_state["dv_data_dir"] = str(safe_data_dir)
            st.session_state["org"] = DataOrganizer.load(str(safe_data_dir))
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
    selected_run_defaults = st.session_state.get("dv_selected_runs", [])
    selected_run_defaults = [rk for rk in selected_run_defaults if rk in run_keys]
    if not selected_run_defaults:
        selected_run_defaults = [run_keys[0]] if run_keys else []
    st.session_state["dv_selected_runs"] = selected_run_defaults

    selected_keys = st.multiselect(
        "Select Run(s)",
        run_keys,
        default=selected_run_defaults,
        key="dv_selected_runs",
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

    if st.session_state.get("dv_selected_dtype") not in available:
        st.session_state["dv_selected_dtype"] = available[0]
    selected_dtype = st.selectbox("Data type", available, key="dv_selected_dtype")

    # ---- plot-type selector -------------------------------------------------
    plotter_cls = PLOTTER_REGISTRY.get(selected_dtype)
    if plotter_cls is None:
        st.error(f"No plotter registered for '{selected_dtype}'.")
        st.stop()

    plotter = plotter_cls()
    plot_types = plotter.available_plot_types
    if st.session_state.get("dv_selected_plot_type") not in plot_types:
        st.session_state["dv_selected_plot_type"] = plot_types[0]
    selected_plot_type = st.selectbox("Plot type", plot_types, key="dv_selected_plot_type")

    # ---- Plot Controls ------------------------------------------------------
    st.header("⚙️ Plot Controls")

    # Scale controls for non-image plots
    if not _is_image_type(selected_dtype):
        col1, col2 = st.columns(2)
        with col1:
            if st.session_state.get("dv_x_scale") not in SCALE_OPTIONS:
                st.session_state["dv_x_scale"] = SCALE_OPTIONS[0]
            x_scale = st.radio("X Scale", SCALE_OPTIONS, horizontal=True, key="dv_x_scale")
        with col2:
            if st.session_state.get("dv_y_scale") not in SCALE_OPTIONS:
                st.session_state["dv_y_scale"] = SCALE_OPTIONS[0]
            y_scale = st.radio("Y Scale", SCALE_OPTIONS, horizontal=True, key="dv_y_scale")

    # Colormap for heatmaps/2D plots
    if _is_heatmap_plot(selected_plot_type) or _is_image_type(selected_dtype):
        if st.session_state.get("dv_cmap") not in COLORMAPS:
            st.session_state["dv_cmap"] = COLORMAPS[0]
        cmap = st.selectbox("Colormap", COLORMAPS, key="dv_cmap")
    else:
        cmap = None

    # Line style controls for overlay plots (when multiple runs selected)
    if len(selected_keys) > 1 and not _is_image_type(selected_dtype):
        with st.expander("🎨 Line Styles", expanded=False):
            show_markers = st.checkbox("Show markers", key="dv_show_markers")
            line_alpha = st.slider("Line opacity", 0.1, 1.0, 0.8, 0.1, key="dv_line_alpha")
    else:
        show_markers = st.session_state.get("dv_show_markers", False)
        line_alpha = st.session_state.get("dv_line_alpha", 1.0)

# ---------------------------------------------------------------------------
# main area
# ---------------------------------------------------------------------------

st.header(f"📈 Visualization: {selected_dtype.upper()} - {selected_plot_type}")

selector_values = []

if _is_image_type(selected_dtype):
    # ----- IMAGE BRANCH --------------------------------------------------------
    # For images, show side-by-side comparison if multiple runs selected

    loaders = [getattr(run, selected_dtype) for _, run in selected_runs]

    # Get image indices
    n_files = len(loaders[0].link.file_paths)
    image_choices = list(range(n_files))
    if st.session_state.get("dv_image_idx") not in image_choices and image_choices:
        st.session_state["dv_image_idx"] = image_choices[0]
    image_idx = st.sidebar.selectbox("Image #", image_choices, key="dv_image_idx")

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
    selector_values = []
    selector_key = (selected_dtype, selected_plot_type)
    if selector_key in SELECTORS:
        kwarg_name, label, data_key = SELECTORS[selector_key]
        first_data = run_data_pairs[0][1]
        values = first_data[data_key]
        values_list = [round(float(v), 4) for v in values]
        selector_values = values_list
        if st.session_state.get("dv_selector_value") not in values_list and values_list:
            st.session_state["dv_selector_value"] = values_list[0]
        chosen = st.sidebar.selectbox(label, values_list, key="dv_selector_value")
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

# ---------------------------------------------------------------------------
# Python Editor (Two-way GUI <-> Code)
# ---------------------------------------------------------------------------

current_dv_plot_spec = _build_data_viewer_plot_spec(
    data_dir=data_dir,
    selected_keys=selected_keys,
    selected_dtype=selected_dtype,
    selected_plot_type=selected_plot_type,
    x_scale=st.session_state.get("dv_x_scale", SCALE_OPTIONS[0]),
    y_scale=st.session_state.get("dv_y_scale", SCALE_OPTIONS[0]),
    cmap=st.session_state.get("dv_cmap"),
    show_markers=st.session_state.get("dv_show_markers", False),
    line_alpha=st.session_state.get("dv_line_alpha", 0.8),
    image_idx=st.session_state.get("dv_image_idx", 0),
    selector_value=st.session_state.get("dv_selector_value"),
)
st.session_state["dv_current_plot_spec"] = current_dv_plot_spec

if not st.session_state.get("dv_editor_code"):
    st.session_state["dv_editor_code"] = _generate_data_viewer_editor_python(current_dv_plot_spec)

st.divider()
st.header("🧠 Python Plot Editor (Experimental)")
st.caption("Two-way control: GUI -> Python script -> GUI.")
st.caption("Code runs in the app process. Only run trusted code.")

pending_editor_code = st.session_state.pop("dv_editor_code_pending", None)
if pending_editor_code is not None:
    st.session_state["dv_editor_code"] = pending_editor_code

editor_code = st.text_area(
    "Editable Python script",
    key="dv_editor_code",
    height=280,
    help="Edit plot_spec and click 'Run Edited Python' to sync Data Viewer controls."
)

ed_col1, ed_col2 = st.columns(2)
with ed_col1:
    if st.button("🧾 Show Python from Current GUI", key="dv_editor_generate"):
        st.session_state["dv_editor_code_pending"] = _generate_data_viewer_editor_python(current_dv_plot_spec)
        st.session_state["dv_editor_status"] = "Editor refreshed from current GUI state."
        st.session_state["dv_editor_warnings"] = []
        st.rerun()

with ed_col2:
    if st.button("▶️ Run Edited Python", key="dv_editor_run", type="primary"):
        try:
            normalized_spec, warnings = _execute_data_viewer_editor(
                editor_code,
                current_dv_plot_spec,
                run_keys,
                available,
                plot_types,
                selector_values,
            )
            if normalized_spec.get("data_dir") != data_dir:
                warnings.append("Data directory changed in script. Click 'Load/Reload' to refresh data.")
            st.session_state["dv_pending_plot_spec"] = normalized_spec
            st.session_state["dv_editor_status"] = "Script applied. GUI synced from edited plot_spec."
            st.session_state["dv_editor_warnings"] = warnings
            st.rerun()
        except Exception as exc:
            st.session_state["dv_editor_status"] = f"Script execution failed: {exc}"
            st.session_state["dv_editor_warnings"] = []

if st.session_state.get("dv_editor_status"):
    status_text = st.session_state["dv_editor_status"]
    if status_text.lower().startswith("script execution failed"):
        st.error(status_text)
    else:
        st.success(status_text)
for warning_msg in st.session_state.get("dv_editor_warnings", []):
    st.warning(warning_msg)

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
