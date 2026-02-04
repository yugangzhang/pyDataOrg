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


# ---------------------------------------------------------------------------
# main app
# ---------------------------------------------------------------------------

st.set_page_config(title="NanoOrganizer Viz", layout="wide")
st.title("NanoOrganizer — Data Browser")

# ---- sidebar: data directory & load ----------------------------------------
with st.sidebar:
    default_path = _auto_detect_demo()
    data_dir = st.text_input("Data directory", value=default_path)

    if "org" not in st.session_state or st.button("Load"):
        try:
            st.session_state["org"] = DataOrganizer.load(data_dir)
            st.session_state.pop("_prev_dir", None)
        except Exception as exc:
            st.error(f"Failed to load: {exc}")
            st.stop()

    org: DataOrganizer = st.session_state.get("org")
    if org is None:
        st.info("Click **Load** to open a data directory.")
        st.stop()

    # ---- run selector ---------------------------------------------------
    run_keys = org.list_runs()
    if not run_keys:
        st.warning("No runs found in the selected directory.")
        st.stop()

    selected_key = st.selectbox("Run", run_keys)
    run = org.get_run(selected_key)

    # ---- run-info expander ----------------------------------------------
    meta = run.metadata
    with st.expander("Run Info"):
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

    # ---- data-type selector ---------------------------------------------
    available = _available_data_types(run)
    if not available:
        st.warning("No linked data in this run.")
        st.stop()

    selected_dtype = st.selectbox("Data type", available)

    # ---- plot-type selector ---------------------------------------------
    # For image types the plotter key is "sem"/"tem"; for others it matches
    # the loader attribute name directly.
    plotter_cls = PLOTTER_REGISTRY.get(selected_dtype)
    if plotter_cls is None:
        st.error(f"No plotter registered for '{selected_dtype}'.")
        st.stop()

    plotter = plotter_cls()
    plot_types = plotter.available_plot_types
    selected_plot_type = st.selectbox("Plot type", plot_types)

# ---------------------------------------------------------------------------
# main area
# ---------------------------------------------------------------------------

loader = getattr(run, selected_dtype)

if _is_image_type(selected_dtype):
    # ----- image branch ----------------------------------------------------
    n_files = len(loader.link.file_paths)
    image_idx = st.sidebar.selectbox("Image #", list(range(n_files)))

    fig, ax = plt.subplots(figsize=(8, 8))
    loader.plot(index=image_idx, ax=ax)
    st.pyplot(fig)
    plt.close(fig)

    with st.expander("Raw Data"):
        st.info(f"{n_files} image file(s) linked.")
        for fp in loader.link.file_paths:
            st.code(fp)

else:
    # ----- time-series / 2-D branch ----------------------------------------
    data = loader.load()

    # dynamic selector control
    kwargs = {}
    selector_key = (selected_dtype, selected_plot_type)
    if selector_key in SELECTORS:
        kwarg_name, label, data_key = SELECTORS[selector_key]
        values = data[data_key]
        # numpy arrays → plain Python list for Streamlit; round for display
        values_list = [round(float(v), 4) for v in values]
        chosen = st.sidebar.selectbox(label, values_list)
        kwargs[kwarg_name] = chosen

    fig, ax = plt.subplots(figsize=(10, 6))
    plotter.plot(data, plot_type=selected_plot_type, ax=ax, **kwargs)
    st.pyplot(fig)
    plt.close(fig)

    # ----- Raw Data expander -----------------------------------------------
    with st.expander("Raw Data"):
        if "images" in data:
            # 2-D detector data
            st.info(
                f"Image stack: {data['images'].shape[0]} frames, "
                f"shape {data['images'].shape[1]}×{data['images'].shape[2]} pixels"
            )
        else:
            # 1-D time-series – find the 2-D array and its axes
            for key, val in data.items():
                if isinstance(val, np.ndarray) and val.ndim == 2:
                    import pandas as pd
                    # Use first axis key as row index when possible
                    st.dataframe(pd.DataFrame(val))
                    break

# ----- Full Metadata expander (always visible) ----------------------------
with st.expander("Full Metadata"):
    st.json(run.to_dict())
