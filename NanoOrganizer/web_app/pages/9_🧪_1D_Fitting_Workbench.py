#!/usr/bin/env python3
"""
1D Fitting Workbench - dedicated page for curve fitting workflow.

Design goals:
- Keep CSV Plotter for broad visualization.
- Keep fitting workflow focused: load/select data, optional preview, then fit.
"""

import streamlit as st
import numpy as np
import pandas as pd
from pathlib import Path
import sys
import copy
import pprint
import plotly.graph_objects as go

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.folder_browser import folder_browser  # noqa: E402
from components.floating_button import floating_sidebar_toggle  # noqa: E402
from components.security import (  # noqa: E402
    initialize_security_context,
    require_authentication,
)
from components.fitting_engine_registry import (  # noqa: E402
    get_engine_schema_rows as registry_get_engine_schema_rows,
    get_ready_backend_labels as registry_get_ready_backend_labels,
    list_engine_rows as registry_list_engine_rows,
)
from components.fitting_adapters import (  # noqa: E402
    PYFITTING_AVAILABLE,
    PYFITTING_IMPORT_ERROR,
    PYSAXS_AVAILABLE,
    PYSAXS_IMPORT_ERROR,
    SAXS_MODEL_LABEL_TO_KEY,
    SAXS_MODEL_KEY_TO_LABEL,
    build_batch_fit_zip_bytes as adapter_build_batch_fit_zip_bytes,
    build_fit_zip_bytes as adapter_build_fit_zip_bytes,
    create_fit_plot_figure as adapter_create_fit_plot_figure,
    dedupe_sorted as adapter_dedupe_sorted,
    format_metric as adapter_format_metric,
    get_saxs_shape_options,
    list_ml_models as adapter_list_ml_models,
    run_general_peak_fit,
    run_ml_prediction as adapter_run_ml_prediction,
    run_saxs_fit,
    sanitize_filename as adapter_sanitize_filename,
    save_batch_fit_to_server as adapter_save_batch_fit_to_server,
    save_single_fit_to_server as adapter_save_single_fit_to_server,
    simulate_saxs_curve,
)


FIT_SHAPES = {
    "Gaussian": "gaussian",
    "Lorentzian": "lorentzian",
    "Pseudo-Voigt": "pseudo_voigt",
}

FIT_BACKENDS = {
    "General Peaks": "general_peaks",
    "SAXS Physics": "saxs_physics",
}

AXIS_SCALE_OPTIONS = ["linear-linear", "log-x", "log-y", "log-log"]

# User-mode restriction (set by nanoorganizer_user)
initialize_security_context()
require_authentication()
_user_mode = st.session_state.get("user_mode", False)
_start_dir = st.session_state.get("user_start_dir", None)


def shorten_path(path_str, max_length=40):
    """Shorten long file paths for compact labels."""
    if len(path_str) <= max_length:
        return path_str

    path = Path(path_str)
    filename = path.name
    if len(filename) > max_length - 3:
        return "..." + filename[-(max_length - 3):]

    parent = str(path.parent)
    if len(parent) + len(filename) + 4 > max_length:
        return ".../" + filename
    remaining = max_length - len(filename) - 4
    return parent[:remaining] + ".../" + filename


def load_data_file(file_path):
    """Load CSV, TXT, DAT, or NPZ into a dataframe."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".npz":
            data = np.load(file_path)
            df_dict = {}
            for key in data.files:
                arr = data[key]
                if arr.ndim == 1:
                    df_dict[key] = arr
                elif arr.ndim == 2:
                    df_dict[key] = arr.flatten()
            return pd.DataFrame(df_dict)

        df = pd.read_csv(file_path, sep=",")
        if len(df.columns) == 1:
            df = pd.read_csv(file_path, sep="\t")
        if len(df.columns) == 1:
            df = pd.read_csv(file_path, sep=r"\s+")
        return df
    except Exception as e:
        st.error(f"Error loading {path.name}: {e}")
        return None


def _safe_widget_key(prefix, name):
    """Create compact deterministic keys for widgets."""
    return f"{prefix}_{abs(hash(str(name)))}"


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


def _prepare_xy(x_values, y_values, x_min=None, x_max=None):
    """Convert to numeric arrays, drop NaNs, optionally apply x-range."""
    x = pd.to_numeric(pd.Series(x_values), errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(pd.Series(y_values), errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if x_min is not None:
        mask &= x >= float(x_min)
    if x_max is not None:
        mask &= x <= float(x_max)
    x = x[mask]
    y = y[mask]
    if len(x) == 0:
        return x, y
    order = np.argsort(x)
    return x[order], y[order]


def _shape_profile(x, center, width, shape, eta=0.5):
    """Return normalized 1D peak profile."""
    width = max(abs(float(width)), 1e-12)
    x = np.asarray(x, dtype=float)
    if shape == "gaussian":
        return np.exp(-0.5 * ((x - center) / width) ** 2)
    if shape == "lorentzian":
        return 1.0 / (1.0 + ((x - center) / width) ** 2)
    eta = float(np.clip(eta, 0.0, 1.0))
    gaussian = np.exp(-0.5 * ((x - center) / width) ** 2)
    lorentzian = 1.0 / (1.0 + ((x - center) / width) ** 2)
    return eta * lorentzian + (1.0 - eta) * gaussian


def _simulate_peak_curve(n_peaks, shape, x_min, x_max, n_points, baseline, noise_level, seed):
    """Generate synthetic 1D multi-peak curve."""
    rng = np.random.default_rng(int(seed))
    x = np.linspace(float(x_min), float(x_max), int(n_points))
    span = max(float(x_max) - float(x_min), 1e-12)
    centers = np.sort(rng.uniform(x_min + 0.1 * span, x_max - 0.1 * span, size=int(n_peaks)))
    widths = rng.uniform(0.02 * span, 0.08 * span, size=int(n_peaks))
    amplitudes = rng.uniform(0.8, 2.0, size=int(n_peaks))
    etas = rng.uniform(0.2, 0.8, size=int(n_peaks)) if shape == "pseudo_voigt" else np.zeros(int(n_peaks))

    y = np.full_like(x, float(baseline), dtype=float)
    component_rows = []
    for i in range(int(n_peaks)):
        eta = float(etas[i]) if shape == "pseudo_voigt" else 0.5
        profile = _shape_profile(x, centers[i], widths[i], shape, eta=eta)
        y += amplitudes[i] * profile
        component_rows.append(
            {
                "peak": i + 1,
                "A": float(amplitudes[i]),
                "mu": float(centers[i]),
                "w": float(widths[i]),
                "eta": float(eta) if shape == "pseudo_voigt" else np.nan,
            }
        )

    noise_sigma = float(noise_level) * max(float(np.ptp(y)), 1e-9)
    if noise_sigma > 0:
        y = y + rng.normal(0.0, noise_sigma, size=len(x))

    return pd.DataFrame({"x": x, "intensity": y}), component_rows


def _parse_float_list(text_value, default_values=None):
    """Parse comma/space/semicolon separated float list."""
    if default_values is None:
        default_values = []
    raw = str(text_value or "").strip().replace(";", ",").replace(" ", ",")
    values = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except Exception:
            continue
    if values:
        return values
    return [float(v) for v in default_values]


def _format_noise_tag(value):
    """Build compact filename fragment for noise value."""
    return f"{float(value):.4f}".rstrip("0").rstrip(".").replace(".", "p")


def _default_saxs_initial_overrides(x_values, y_values, *, polydisperse=False, use_porod=False):
    """Estimate practical SAXS initial guesses from current fitting window."""
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    x = x[np.isfinite(x)]
    y = y[np.isfinite(y)]

    # SAXS default: start from 100 A size-scale when no explicit prior exists.
    radius_guess = 100.0

    if len(y):
        y_min = float(np.min(y))
        y_max = float(np.max(y))
    else:
        y_min = 0.0
        y_max = 1.0

    overrides = {
        "radius": float(radius_guess),
        "scale": float(max(y_max, 1e-9)),
        "background": float(y_min),
    }
    if polydisperse:
        overrides["sigma_rel"] = 0.10
    if use_porod:
        overrides["porod_scale"] = 0.01
        overrides["porod_exp"] = 4.0
    return overrides


def _apply_axis_scale(fig, scale_mode):
    """Apply axis scale mode to a plotly figure."""
    scale_mode = str(scale_mode).strip().lower()
    x_log = scale_mode in {"log-x", "log-log"}
    y_log = scale_mode in {"log-y", "log-log"}
    fig.update_xaxes(type="log" if x_log else "linear")
    fig.update_yaxes(type="log" if y_log else "linear")
    return fig


def _build_preview_figure(
    x,
    y,
    *,
    x_name,
    y_name,
    curve_label,
    peak_positions=None,
    fit_state=None,
    scale_mode="linear-linear",
):
    """Build preview figure for selected curve."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            name="Data",
            marker=dict(size=6, color="#111111"),
            hovertemplate=f"<b>{x_name}</b>: %{{x:.5g}}<br><b>{y_name}</b>: %{{y:.5g}}<extra></extra>",
        )
    )

    peak_positions = peak_positions or []
    for peak_x in peak_positions:
        fig.add_vline(
            x=float(peak_x),
            line_width=1.2,
            line_dash="dot",
            line_color="#d62728",
        )

    if fit_state and fit_state.get("success"):
        try:
            fig.add_trace(
                go.Scatter(
                    x=np.asarray(fit_state.get("x", []), dtype=float),
                    y=np.asarray(fit_state.get("y_fit", []), dtype=float),
                    mode="lines",
                    name="Latest fit",
                    line=dict(color="#d62728", width=2.0),
                )
            )
        except Exception:
            pass

    fig.update_layout(
        title=f"Preview: {curve_label}",
        height=440,
        showlegend=True,
        dragmode="select",
        clickmode="event+select",
    )
    fig.update_xaxes(title=x_name)
    fig.update_yaxes(title=y_name)
    _apply_axis_scale(fig, scale_mode)
    return fig


def _build_curve_options(dataframes, x_col):
    """Build selectable curve options for a given x column."""
    curve_options = []
    for file_name, df in dataframes.items():
        for y_col in df.columns:
            if y_col == x_col:
                continue
            curve_key = f"{file_name}::{y_col}"
            curve_options.append(
                {
                    "label": f"{shorten_path(file_name, 34)} : {y_col}",
                    "curve_key": curve_key,
                    "file_name": file_name,
                    "y_col": y_col,
                }
            )
    return curve_options


def _get_curve_bounds(dataframes, x_col, curve_item):
    """Get numeric x bounds for a selected curve item."""
    if not curve_item:
        return None
    file_name = curve_item.get("file_name")
    y_col = curve_item.get("y_col")
    df = dataframes.get(file_name)
    if df is None or x_col not in df.columns or y_col not in df.columns:
        return None
    x_values, y_values = _prepare_xy(df[x_col].values, df[y_col].values)
    if len(x_values) < 2:
        return None
    return float(np.min(x_values)), float(np.max(x_values))


def _sanitize_range_pair(range_value, bounds, fallback_pair=None):
    """Sanitize numeric range pair against bounds."""
    if bounds is None:
        return fallback_pair
    b_min, b_max = bounds
    if fallback_pair is None:
        fallback_pair = [b_min, b_max]
    if (
        isinstance(range_value, (list, tuple))
        and len(range_value) == 2
    ):
        left = _to_float(range_value[0], fallback_pair[0])
        right = _to_float(range_value[1], fallback_pair[1])
    else:
        left, right = fallback_pair
    if left > right:
        left, right = right, left
    left = float(np.clip(left, b_min, b_max))
    right = float(np.clip(right, b_min, b_max))
    if left == right:
        left, right = fallback_pair
    return [left, right]


def _build_wb_setup_spec(
    *,
    x_col,
    working_curves,
    target_curve,
    show_preview,
    preview_scale,
    use_viz_range,
    viz_range,
    fit_backend_label,
    fit_use_range,
    fit_range,
    fit_shape_label,
    fit_maxiter,
    batch_default_peaks,
    use_manual_peaks_single,
    saxs_shape_label,
    saxs_polydisperse,
    saxs_use_porod,
    saxs_maxiter,
    use_saxs_init_overrides,
    saxs_initial_overrides,
):
    """Build serializable fit-setup spec from current controls."""
    return {
        "version": 1,
        "x_col": str(x_col),
        "working_curves": [str(v) for v in working_curves],
        "target_curve": str(target_curve),
        "preview": {
            "show": bool(show_preview),
            "axis_scale": str(preview_scale),
            "use_range": bool(use_viz_range),
            "range": [float(viz_range[0]), float(viz_range[1])] if use_viz_range and viz_range is not None else None,
        },
        "fit": {
            "backend_label": str(fit_backend_label),
            "use_range": bool(fit_use_range),
            "range": [float(fit_range[0]), float(fit_range[1])] if fit_use_range and fit_range is not None else None,
            "general": {
                "shape_label": str(fit_shape_label),
                "maxiter": int(fit_maxiter),
                "default_peak_count": int(batch_default_peaks),
                "use_manual_peaks_single": bool(use_manual_peaks_single),
            },
            "saxs": {
                "shape_label": str(saxs_shape_label) if saxs_shape_label else None,
                "polydisperse": bool(saxs_polydisperse),
                "use_porod": bool(saxs_use_porod),
                "maxiter": int(saxs_maxiter),
                "use_init_overrides": bool(use_saxs_init_overrides),
                "initial_overrides": {
                    k: float(v)
                    for k, v in (saxs_initial_overrides or {}).items()
                },
            },
        },
    }


def _generate_wb_editor_python(plot_spec):
    """Generate editable Python code for fit-setup spec."""
    spec_text = pprint.pformat(plot_spec, sort_dicts=False, width=100, compact=False)
    return (
        "# NanoOrganizer fitting-workbench setup editor (experimental)\n"
        "# Edit plot_spec below and click 'Run Edited Python'.\n"
        "# The app uses `result` (if defined) otherwise `plot_spec`.\n\n"
        f"plot_spec = {spec_text}\n\n"
        "# Example tweaks:\n"
        "# plot_spec['fit']['backend_label'] = 'General Peaks'\n"
        "# plot_spec['fit']['general']['maxiter'] = 4000\n\n"
        "result = plot_spec\n"
    )


def _sanitize_wb_setup_spec(
    candidate,
    fallback_spec,
    *,
    dataframes,
    all_columns,
    backend_labels,
    saxs_shape_labels,
):
    """Sanitize edited fit-setup spec and return (spec, warnings)."""
    warnings = []
    if not isinstance(candidate, dict):
        warnings.append("Edited code did not return a dict; keeping previous setup.")
        return copy.deepcopy(fallback_spec), warnings

    normalized = copy.deepcopy(fallback_spec)

    # X column and curve selections
    candidate_x_col = str(candidate.get("x_col", normalized.get("x_col")))
    if candidate_x_col in all_columns:
        normalized["x_col"] = candidate_x_col
    elif "x_col" in candidate:
        warnings.append(f"Ignored unknown x_col '{candidate_x_col}'.")

    curve_options = _build_curve_options(dataframes, normalized["x_col"])
    curve_map = {item["label"]: item for item in curve_options}
    curve_labels = list(curve_map.keys())

    working_curves = candidate.get("working_curves", normalized.get("working_curves", []))
    if isinstance(working_curves, str):
        working_curves = [working_curves]
    if not isinstance(working_curves, (list, tuple, set)):
        working_curves = []
    working_curves = [str(v) for v in working_curves if str(v) in curve_labels]
    if not working_curves and curve_labels:
        fallback_working = [v for v in normalized.get("working_curves", []) if v in curve_labels]
        working_curves = fallback_working if fallback_working else curve_labels[: min(8, len(curve_labels))]
    normalized["working_curves"] = working_curves

    target_curve = str(candidate.get("target_curve", normalized.get("target_curve", "")))
    if target_curve not in working_curves and working_curves:
        target_curve = working_curves[0]
    normalized["target_curve"] = target_curve

    bounds = _get_curve_bounds(dataframes, normalized["x_col"], curve_map.get(target_curve))

    preview = candidate.get("preview", {})
    if not isinstance(preview, dict):
        preview = {}
        warnings.append("preview must be a dict; keeping previous preview settings.")
    fallback_preview = normalized.get("preview", {})
    preview_show = _to_bool(preview.get("show", fallback_preview.get("show", False)), False)
    preview_scale = str(preview.get("axis_scale", fallback_preview.get("axis_scale", AXIS_SCALE_OPTIONS[0])))
    if preview_scale not in AXIS_SCALE_OPTIONS:
        preview_scale = AXIS_SCALE_OPTIONS[0]
    preview_use_range = _to_bool(preview.get("use_range", fallback_preview.get("use_range", True)), True)
    preview_range = _sanitize_range_pair(
        preview.get("range", fallback_preview.get("range")),
        bounds,
        fallback_preview.get("range"),
    )
    normalized["preview"] = {
        "show": preview_show,
        "axis_scale": preview_scale,
        "use_range": preview_use_range,
        "range": preview_range if preview_use_range else None,
    }

    fit = candidate.get("fit", {})
    if not isinstance(fit, dict):
        fit = {}
        warnings.append("fit must be a dict; keeping previous fit settings.")
    fallback_fit = normalized.get("fit", {})
    backend_label = str(fit.get("backend_label", fallback_fit.get("backend_label", "")))
    if backend_label not in backend_labels:
        backend_label = backend_labels[0] if backend_labels else "General Peaks"
        if "backend_label" in fit:
            warnings.append("Requested backend is not ready in this environment; defaulted to first ready backend.")

    fit_use_range = _to_bool(fit.get("use_range", fallback_fit.get("use_range", True)), True)
    fit_range = _sanitize_range_pair(
        fit.get("range", fallback_fit.get("range")),
        bounds,
        fallback_fit.get("range"),
    )

    general = fit.get("general", {})
    if not isinstance(general, dict):
        general = {}
    fallback_general = fallback_fit.get("general", {})
    general_shape = str(general.get("shape_label", fallback_general.get("shape_label", "Gaussian")))
    if general_shape not in FIT_SHAPES:
        general_shape = "Gaussian"
    general_maxiter = _to_int(general.get("maxiter", fallback_general.get("maxiter", 2000)), 2000, 100, 10000)
    general_default_peak_count = _to_int(
        general.get("default_peak_count", fallback_general.get("default_peak_count", 2)),
        2,
        1,
        12,
    )
    general_manual = _to_bool(
        general.get("use_manual_peaks_single", fallback_general.get("use_manual_peaks_single", True)),
        True,
    )

    saxs = fit.get("saxs", {})
    if not isinstance(saxs, dict):
        saxs = {}
    fallback_saxs = fallback_fit.get("saxs", {})
    saxs_shape = saxs.get("shape_label", fallback_saxs.get("shape_label"))
    if saxs_shape_labels:
        if saxs_shape not in saxs_shape_labels:
            saxs_shape = fallback_saxs.get("shape_label")
        if saxs_shape not in saxs_shape_labels:
            saxs_shape = saxs_shape_labels[0]
    else:
        saxs_shape = None
    saxs_poly = _to_bool(saxs.get("polydisperse", fallback_saxs.get("polydisperse", True)), True)
    saxs_porod = _to_bool(saxs.get("use_porod", fallback_saxs.get("use_porod", False)), False)
    saxs_maxiter = _to_int(saxs.get("maxiter", fallback_saxs.get("maxiter", 2000)), 2000, 100, 20000)
    saxs_use_init = _to_bool(
        saxs.get("use_init_overrides", fallback_saxs.get("use_init_overrides", True)),
        True,
    )
    incoming_overrides = saxs.get("initial_overrides", fallback_saxs.get("initial_overrides", {}))
    if not isinstance(incoming_overrides, dict):
        incoming_overrides = {}
    fallback_overrides = fallback_saxs.get("initial_overrides", {})
    init_overrides = {
        "radius": _to_float(incoming_overrides.get("radius", fallback_overrides.get("radius", 100.0)), 100.0, 1e-6),
        "scale": _to_float(incoming_overrides.get("scale", fallback_overrides.get("scale", 1.0)), 1.0, 1e-12),
        "background": _to_float(incoming_overrides.get("background", fallback_overrides.get("background", 0.0)), 0.0),
    }
    if saxs_poly:
        init_overrides["sigma_rel"] = _to_float(
            incoming_overrides.get("sigma_rel", fallback_overrides.get("sigma_rel", 0.10)),
            0.10,
            0.0,
            2.0,
        )
    if saxs_porod:
        init_overrides["porod_scale"] = _to_float(
            incoming_overrides.get("porod_scale", fallback_overrides.get("porod_scale", 0.01)),
            0.01,
            0.0,
        )
        init_overrides["porod_exp"] = _to_float(
            incoming_overrides.get("porod_exp", fallback_overrides.get("porod_exp", 4.0)),
            4.0,
            0.0,
            8.0,
        )

    normalized["fit"] = {
        "backend_label": backend_label,
        "use_range": fit_use_range,
        "range": fit_range if fit_use_range else None,
        "general": {
            "shape_label": general_shape,
            "maxiter": general_maxiter,
            "default_peak_count": general_default_peak_count,
            "use_manual_peaks_single": general_manual,
        },
        "saxs": {
            "shape_label": saxs_shape,
            "polydisperse": saxs_poly,
            "use_porod": saxs_porod,
            "maxiter": saxs_maxiter,
            "use_init_overrides": saxs_use_init,
            "initial_overrides": init_overrides,
        },
    }

    return normalized, warnings


def _apply_wb_setup_spec_to_state(plot_spec):
    """Apply sanitized fit-setup spec to session state."""
    st.session_state["wb_x_col"] = plot_spec.get("x_col")
    st.session_state["wb_working_curves"] = list(plot_spec.get("working_curves", []))
    st.session_state["wb_target_curve"] = plot_spec.get("target_curve")

    preview = plot_spec.get("preview", {})
    st.session_state["wb_show_preview"] = _to_bool(preview.get("show", False), False)
    st.session_state["wb_preview_scale"] = str(preview.get("axis_scale", AXIS_SCALE_OPTIONS[0]))
    st.session_state["wb_use_viz_range"] = _to_bool(preview.get("use_range", True), True)
    st.session_state["wb_pending_viz_range_from_editor"] = preview.get("range")

    fit = plot_spec.get("fit", {})
    st.session_state["wb_fit_backend"] = str(fit.get("backend_label", "General Peaks"))
    st.session_state["wb_use_fit_range"] = _to_bool(fit.get("use_range", True), True)
    st.session_state["wb_pending_fit_range_from_editor"] = fit.get("range")

    general = fit.get("general", {})
    st.session_state["wb_fit_shape"] = str(general.get("shape_label", "Gaussian"))
    st.session_state["wb_fit_maxiter"] = _to_int(general.get("maxiter", 2000), 2000, 100, 10000)
    st.session_state["wb_fit_default_peak_count"] = _to_int(
        general.get("default_peak_count", 2), 2, 1, 12
    )
    st.session_state["wb_use_manual_peaks_single"] = _to_bool(
        general.get("use_manual_peaks_single", True), True
    )

    saxs = fit.get("saxs", {})
    if saxs.get("shape_label") is not None:
        st.session_state["wb_saxs_shape"] = str(saxs.get("shape_label"))
    st.session_state["wb_saxs_poly"] = _to_bool(saxs.get("polydisperse", True), True)
    st.session_state["wb_saxs_porod"] = _to_bool(saxs.get("use_porod", False), False)
    st.session_state["wb_saxs_maxiter"] = _to_int(saxs.get("maxiter", 2000), 2000, 100, 20000)
    st.session_state["wb_saxs_use_init_overrides"] = _to_bool(
        saxs.get("use_init_overrides", True), True
    )
    init_overrides = saxs.get("initial_overrides", {})
    if isinstance(init_overrides, dict):
        if "radius" in init_overrides:
            st.session_state["wb_saxs_init_radius"] = _to_float(init_overrides["radius"], 100.0, 1e-6)
        if "scale" in init_overrides:
            st.session_state["wb_saxs_init_scale"] = _to_float(init_overrides["scale"], 1.0, 1e-12)
        if "background" in init_overrides:
            st.session_state["wb_saxs_init_background"] = _to_float(init_overrides["background"], 0.0)
        if "sigma_rel" in init_overrides:
            st.session_state["wb_saxs_init_sigma_rel"] = _to_float(init_overrides["sigma_rel"], 0.10, 0.0, 2.0)
        if "porod_scale" in init_overrides:
            st.session_state["wb_saxs_init_porod_scale"] = _to_float(init_overrides["porod_scale"], 0.01, 0.0)
        if "porod_exp" in init_overrides:
            st.session_state["wb_saxs_init_porod_exp"] = _to_float(init_overrides["porod_exp"], 4.0, 0.0, 8.0)


def _execute_wb_editor(
    code_text,
    base_plot_spec,
    *,
    dataframes,
    all_columns,
    backend_labels,
    saxs_shape_labels,
):
    """Execute setup-editor code and sanitize returned spec."""
    execution_locals = {
        "plot_spec": copy.deepcopy(base_plot_spec),
        "result": None,
        "available_x_columns": list(all_columns),
        "ready_backends": list(backend_labels),
        "saxs_models": list(saxs_shape_labels),
        "copy": copy,
        "np": np,
        "pd": pd,
    }
    exec(code_text, {"__builtins__": __builtins__}, execution_locals)
    candidate = execution_locals.get("result")
    if candidate is None:
        candidate = execution_locals.get("plot_spec")
    return _sanitize_wb_setup_spec(
        candidate,
        base_plot_spec,
        dataframes=dataframes,
        all_columns=all_columns,
        backend_labels=backend_labels,
        saxs_shape_labels=saxs_shape_labels,
    )


# ---------------------------------------------------------------------------
# Initialize session state
# ---------------------------------------------------------------------------
if "fit_workbench_dataframes" not in st.session_state:
    st.session_state["fit_workbench_dataframes"] = {}
if "fit_workbench_file_paths" not in st.session_state:
    st.session_state["fit_workbench_file_paths"] = {}
if "fit_workbench_sim_meta" not in st.session_state:
    st.session_state["fit_workbench_sim_meta"] = {}
if "fit_workbench_sim_counter" not in st.session_state:
    st.session_state["fit_workbench_sim_counter"] = 0
if "fit_workbench_peak_guesses" not in st.session_state:
    st.session_state["fit_workbench_peak_guesses"] = {}
if "fit_workbench_results" not in st.session_state:
    st.session_state["fit_workbench_results"] = {}
if "fit_workbench_batch_summary" not in st.session_state:
    st.session_state["fit_workbench_batch_summary"] = []
if "fit_workbench_last_backend" not in st.session_state:
    st.session_state["fit_workbench_last_backend"] = None
if "fit_workbench_ml_predictions" not in st.session_state:
    st.session_state["fit_workbench_ml_predictions"] = {}
if "fit_workbench_ml_applied" not in st.session_state:
    st.session_state["fit_workbench_ml_applied"] = {}
if "wb_preview_scale" not in st.session_state:
    st.session_state["wb_preview_scale"] = "log-log"
if "wb_result_scale" not in st.session_state:
    st.session_state["wb_result_scale"] = "log-log"
if "wb_saxs_poly" not in st.session_state:
    st.session_state["wb_saxs_poly"] = True
if "wb_saxs_use_init_overrides" not in st.session_state:
    st.session_state["wb_saxs_use_init_overrides"] = True
st.session_state.setdefault("wb_editor_code", "")
st.session_state.setdefault("wb_editor_status", "")
st.session_state.setdefault("wb_editor_warnings", [])
if st.session_state.get("fit_workbench_saxs_fit_defaults_version") != 2:
    st.session_state["wb_saxs_poly"] = True
    st.session_state["wb_saxs_use_init_overrides"] = True
    st.session_state["wb_saxs_init_radius"] = 100.0
    st.session_state["wb_saxs_init_sigma_rel"] = 0.10
    st.session_state.pop("wb_saxs_init_scale", None)
    st.session_state.pop("wb_saxs_init_background", None)
    st.session_state["fit_workbench_saxs_fit_defaults_version"] = 2


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
st.title("🧪 1D Fitting Workbench")
st.markdown("Focused workflow: load curves, optionally preview, then run single or batch fitting.")
floating_sidebar_toggle()

with st.sidebar:
    st.header("📁 Data Source")
    data_source = st.radio("Data location", ["Upload files", "Browse server"], key="wb_data_source")

    if data_source == "Upload files":
        uploaded_files = st.file_uploader(
            "Upload data files",
            type=["csv", "txt", "dat", "npz"],
            accept_multiple_files=True,
            key="wb_upload_files",
        )
        if uploaded_files:
            for uploaded_file in uploaded_files:
                try:
                    temp_path = Path(f"/tmp/{uploaded_file.name}")
                    with open(temp_path, "wb") as handle:
                        handle.write(uploaded_file.getbuffer())
                    df = load_data_file(str(temp_path))
                    if df is not None:
                        st.session_state["fit_workbench_dataframes"][uploaded_file.name] = df
                        st.session_state["fit_workbench_file_paths"][uploaded_file.name] = uploaded_file.name
                        st.success(f"Loaded {uploaded_file.name}")
                except Exception as e:
                    st.error(f"Failed to load {uploaded_file.name}: {e}")
    else:
        pattern = st.selectbox(
            "File type filter",
            ["*.*", "*.csv", "*.npz", "*.txt", "*.dat"],
            label_visibility="collapsed",
            key="wb_file_pattern",
        )
        selected_files = folder_browser(
            key="fit_workbench_browser",
            show_files=True,
            file_pattern=pattern,
            multi_select=True,
            initial_path=_start_dir if _user_mode else None,
            restrict_to_start_dir=_user_mode,
        )
        if selected_files and st.button("📥 Load Selected Files", key="wb_load_selected"):
            for full_path in selected_files:
                df = load_data_file(full_path)
                if df is not None:
                    file_name = Path(full_path).name
                    st.session_state["fit_workbench_dataframes"][file_name] = df
                    st.session_state["fit_workbench_file_paths"][file_name] = full_path
                    st.success(f"Loaded {file_name}")

    if st.session_state.get("dataframes_csv"):
        if st.button("📥 Copy Loaded Curves from CSV Plotter", key="wb_copy_from_csv_plotter"):
            copied = 0
            for file_name, df in st.session_state["dataframes_csv"].items():
                st.session_state["fit_workbench_dataframes"][file_name] = df.copy()
                st.session_state["fit_workbench_file_paths"][file_name] = st.session_state.get(
                    "file_paths_csv", {}
                ).get(file_name, file_name)
                copied += 1
            st.success(f"Copied {copied} dataset(s) from CSV Plotter.")
            st.rerun()

    with st.expander("🧪 Simulate 1D Peak Curve", expanded=False):
        st.caption("Generate one/two/multi-peak synthetic data for fitting tests.")
        sim_col1, sim_col2 = st.columns(2)
        with sim_col1:
            sim_shape_label = st.selectbox("Peak shape", list(FIT_SHAPES.keys()), index=0, key="wb_sim_shape")
            sim_n_peaks = st.number_input(
                "Number of peaks",
                min_value=1,
                max_value=8,
                value=2,
                step=1,
                key="wb_sim_peak_count",
            )
            sim_points = st.number_input(
                "Data points",
                min_value=100,
                max_value=5000,
                value=1200,
                step=100,
                key="wb_sim_points",
            )
        with sim_col2:
            sim_x_min = st.number_input("X min", value=0.0, format="%.4f", key="wb_sim_x_min")
            sim_x_max = st.number_input("X max", value=100.0, format="%.4f", key="wb_sim_x_max")
            sim_baseline = st.number_input("Baseline c", value=0.1, format="%.4f", key="wb_sim_baseline")
            sim_noise = st.slider("Noise level", 0.0, 0.20, 0.02, 0.01, key="wb_sim_noise")
        sim_seed = st.number_input("Random seed", min_value=0, value=1234, step=1, key="wb_sim_seed")

        if st.button("➕ Generate Simulated Curve", key="wb_generate_sim_curve"):
            if sim_x_max <= sim_x_min:
                st.error("X max must be larger than X min.")
            else:
                shape_key = FIT_SHAPES[sim_shape_label]
                sim_df, sim_params = _simulate_peak_curve(
                    n_peaks=int(sim_n_peaks),
                    shape=shape_key,
                    x_min=float(sim_x_min),
                    x_max=float(sim_x_max),
                    n_points=int(sim_points),
                    baseline=float(sim_baseline),
                    noise_level=float(sim_noise),
                    seed=int(sim_seed),
                )
                st.session_state["fit_workbench_sim_counter"] += 1
                sim_name = (
                    f"fitwb_sim_{shape_key}_{int(sim_n_peaks)}peaks_"
                    f"{st.session_state['fit_workbench_sim_counter']:03d}.csv"
                )
                st.session_state["fit_workbench_dataframes"][sim_name] = sim_df
                st.session_state["fit_workbench_file_paths"][sim_name] = f"[simulated] {sim_name}"
                st.session_state["fit_workbench_sim_meta"][sim_name] = {
                    "shape": shape_key,
                    "params": sim_params,
                    "baseline": float(sim_baseline),
                    "noise_level": float(sim_noise),
                    "seed": int(sim_seed),
                }
                st.success(f"Generated {sim_name}")
                st.rerun()

    with st.expander("🧪 Simulate SAXS Curves", expanded=False):
        st.caption("Generate SAXS form-factor curves with shape, noise, and background variants.")
        if not PYSAXS_AVAILABLE:
            st.warning(
                "SAXS simulator unavailable because pySAXSFitting could not be imported. "
                f"Error: {PYSAXS_IMPORT_ERROR or 'unknown'}"
            )
        else:
            sim_saxs_label_to_key, _ = get_saxs_shape_options()
            if not sim_saxs_label_to_key:
                sim_saxs_label_to_key = dict(SAXS_MODEL_LABEL_TO_KEY)
            sim_saxs_shape_labels = list(sim_saxs_label_to_key.keys())
            sim_saxs_default_shape = None
            for label, key in sim_saxs_label_to_key.items():
                if str(key).strip().lower() == "sphere":
                    sim_saxs_default_shape = label
                    break
            if sim_saxs_default_shape is None and sim_saxs_shape_labels:
                sim_saxs_default_shape = sim_saxs_shape_labels[0]

            if st.session_state.get("fit_workbench_saxs_sim_defaults_version") != 1:
                st.session_state["wb_sim_saxs_shapes"] = [sim_saxs_default_shape] if sim_saxs_default_shape else []
                st.session_state["wb_sim_saxs_q_min"] = 0.0004
                st.session_state["wb_sim_saxs_q_max"] = 0.20
                st.session_state["wb_sim_saxs_radius"] = 100.0
                st.session_state["wb_sim_saxs_scale"] = 100.0
                st.session_state["wb_sim_saxs_poly"] = True
                st.session_state["wb_sim_saxs_sigma"] = 0.10
                st.session_state["wb_sim_saxs_porod"] = False
                st.session_state["wb_sim_saxs_bg_modes"] = ["constant"]
                st.session_state["wb_sim_saxs_bg_const"] = 0.10
                st.session_state["wb_sim_saxs_noise_levels"] = "0.005"
                st.session_state["wb_sim_saxs_components"] = False
                st.session_state["fit_workbench_saxs_sim_defaults_version"] = 1

            ss_col1, ss_col2, ss_col3 = st.columns(3)
            with ss_col1:
                sim_saxs_shapes = st.multiselect(
                    "SAXS shapes",
                    sim_saxs_shape_labels,
                    default=[sim_saxs_default_shape] if sim_saxs_default_shape else [],
                    key="wb_sim_saxs_shapes",
                )
                sim_saxs_q_min = st.number_input(
                    "q min (A^-1)",
                    value=0.0004,
                    min_value=0.0,
                    format="%.6f",
                    key="wb_sim_saxs_q_min",
                )
                sim_saxs_q_max = st.number_input(
                    "q max (A^-1)",
                    value=0.20,
                    min_value=0.0,
                    format="%.6f",
                    key="wb_sim_saxs_q_max",
                )
                sim_saxs_points = st.number_input(
                    "Data points",
                    min_value=100,
                    max_value=5000,
                    value=1200,
                    step=100,
                    key="wb_sim_saxs_points",
                )
                sim_saxs_seed = st.number_input(
                    "Base seed",
                    min_value=0,
                    value=4242,
                    step=1,
                    key="wb_sim_saxs_seed",
                )
            with ss_col2:
                sim_saxs_radius = st.number_input(
                    "Radius (A)",
                    min_value=1.0,
                    value=100.0,
                    format="%.3f",
                    key="wb_sim_saxs_radius",
                )
                sim_saxs_scale = st.number_input(
                    "Scale",
                    min_value=0.001,
                    value=100.0,
                    format="%.5f",
                    key="wb_sim_saxs_scale",
                )
                sim_saxs_polydisperse = st.checkbox("Polydisperse", value=True, key="wb_sim_saxs_poly")
                sim_saxs_sigma_rel = st.slider("sigma_rel", 0.01, 0.40, 0.10, 0.01, key="wb_sim_saxs_sigma")
                sim_saxs_use_porod = st.checkbox("Include Porod term", value=False, key="wb_sim_saxs_porod")
            with ss_col3:
                sim_saxs_bg_modes = st.multiselect(
                    "Background modes",
                    ["constant", "decay"],
                    default=["constant"],
                    key="wb_sim_saxs_bg_modes",
                )
                sim_saxs_bg_const = st.number_input(
                    "Background constant",
                    value=0.10,
                    min_value=0.0,
                    format="%.6f",
                    key="wb_sim_saxs_bg_const",
                )
                sim_saxs_bg_amp = st.number_input(
                    "Decay amplitude",
                    value=0.08,
                    min_value=0.0,
                    format="%.6f",
                    key="wb_sim_saxs_bg_amp",
                )
                sim_saxs_bg_q0 = st.number_input(
                    "Decay q0 (A^-1)",
                    value=0.035,
                    min_value=1e-6,
                    format="%.6f",
                    key="wb_sim_saxs_bg_q0",
                )
                sim_saxs_bg_exp = st.number_input(
                    "Decay exponent",
                    value=3.5,
                    min_value=0.1,
                    format="%.3f",
                    key="wb_sim_saxs_bg_exp",
                )

            sim_saxs_noise_text = st.text_input(
                "Noise levels (comma-separated)",
                value="0.005",
                key="wb_sim_saxs_noise_levels",
            )
            st.caption("Noise model: `noise_sigma = noise_level * ptp(intensity_clean)` (relative to clean signal span).")
            sim_saxs_include_components = st.checkbox(
                "Include clean/background component columns",
                value=False,
                key="wb_sim_saxs_components",
            )

            if st.button("➕ Generate SAXS Simulation Curves", key="wb_generate_sim_saxs_curves"):
                if sim_saxs_q_max <= sim_saxs_q_min:
                    st.error("q max must be larger than q min.")
                elif not sim_saxs_shapes:
                    st.error("Select at least one SAXS shape.")
                elif not sim_saxs_bg_modes:
                    st.error("Select at least one background mode.")
                else:
                    sim_saxs_noises = [
                        max(0.0, float(v))
                        for v in _parse_float_list(sim_saxs_noise_text, default_values=[0.005])
                    ]
                    generated_names = []
                    run_idx = 0
                    for shape_label in sim_saxs_shapes:
                        shape_key = sim_saxs_label_to_key.get(shape_label, str(shape_label).lower())
                        for bg_mode in sim_saxs_bg_modes:
                            for noise_level in sim_saxs_noises:
                                run_idx += 1
                                try:
                                    sim_df, sim_meta = simulate_saxs_curve(
                                        shape=shape_key,
                                        q_min=float(sim_saxs_q_min),
                                        q_max=float(sim_saxs_q_max),
                                        n_points=int(sim_saxs_points),
                                        radius=float(sim_saxs_radius),
                                        scale=float(sim_saxs_scale),
                                        polydisperse=bool(sim_saxs_polydisperse),
                                        sigma_rel=float(sim_saxs_sigma_rel),
                                        use_porod=bool(sim_saxs_use_porod),
                                        background_mode=str(bg_mode),
                                        background_const=float(sim_saxs_bg_const),
                                        background_decay_amp=float(sim_saxs_bg_amp),
                                        background_decay_q0=float(sim_saxs_bg_q0),
                                        background_decay_exp=float(sim_saxs_bg_exp),
                                        noise_level=float(noise_level),
                                        seed=int(sim_saxs_seed) + run_idx - 1,
                                        include_components=bool(sim_saxs_include_components),
                                    )
                                except Exception as sim_error:
                                    st.warning(
                                        f"Failed {shape_label}/{bg_mode}/noise={noise_level:.4g}: {sim_error}"
                                    )
                                    continue

                                st.session_state["fit_workbench_sim_counter"] += 1
                                noise_tag = _format_noise_tag(noise_level)
                                sim_name = (
                                    f"fitwb_saxs_{shape_key}_{bg_mode}_n{noise_tag}_"
                                    f"{st.session_state['fit_workbench_sim_counter']:03d}.csv"
                                )
                                st.session_state["fit_workbench_dataframes"][sim_name] = sim_df
                                st.session_state["fit_workbench_file_paths"][sim_name] = f"[simulated] {sim_name}"
                                sim_meta = dict(sim_meta)
                                sim_meta["source"] = "saxs_simulator"
                                st.session_state["fit_workbench_sim_meta"][sim_name] = sim_meta
                                generated_names.append(sim_name)

                    if generated_names:
                        st.success(f"Generated {len(generated_names)} SAXS simulated curve(s).")
                        st.rerun()

    if st.session_state["fit_workbench_dataframes"]:
        if st.button("🗑️ Clear Workbench Data", key="wb_clear_data"):
            st.session_state["fit_workbench_dataframes"] = {}
            st.session_state["fit_workbench_file_paths"] = {}
            st.session_state["fit_workbench_sim_meta"] = {}
            st.session_state["fit_workbench_peak_guesses"] = {}
            st.session_state["fit_workbench_results"] = {}
            st.session_state["fit_workbench_batch_summary"] = []
            st.rerun()


dataframes = st.session_state["fit_workbench_dataframes"]
if not dataframes:
    st.info("Load or simulate curves from the sidebar to start.")
    st.stop()

st.success(f"Loaded {len(dataframes)} dataset(s)")

# Column and curve selection
all_columns = set()
for df in dataframes.values():
    all_columns.update(df.columns)
all_columns = sorted(all_columns)
if not all_columns:
    st.error("No columns found in loaded datasets.")
    st.stop()

if "q" in all_columns:
    default_x_col = "q"
elif "x" in all_columns:
    default_x_col = "x"
else:
    default_x_col = all_columns[0]

if "wb_pending_setup_spec" in st.session_state:
    _pending_setup_spec = st.session_state.pop("wb_pending_setup_spec")
    _apply_wb_setup_spec_to_state(_pending_setup_spec)

x_col_default_for_widget = st.session_state.get("wb_x_col", default_x_col)
if x_col_default_for_widget not in all_columns:
    x_col_default_for_widget = default_x_col
x_col = st.selectbox(
    "X column",
    all_columns,
    index=all_columns.index(x_col_default_for_widget),
    key="wb_x_col",
)

curve_options = _build_curve_options(dataframes, x_col)

if not curve_options:
    st.info("No curve candidates found for current x-column selection.")
    st.stop()

curve_labels = [item["label"] for item in curve_options]
curve_option_by_label = {item["label"]: item for item in curve_options}

default_working = curve_labels[: min(8, len(curve_labels))]
current_working = [
    str(v) for v in st.session_state.get("wb_working_curves", []) if str(v) in curve_labels
]
if not current_working:
    current_working = default_working
st.session_state["wb_working_curves"] = current_working
if st.session_state.get("wb_target_curve") not in current_working and current_working:
    st.session_state["wb_target_curve"] = current_working[0]

working_labels = st.multiselect(
    "Curves in current fitting set",
    curve_labels,
    default=default_working,
    key="wb_working_curves",
)
if not working_labels:
    st.info("Select at least one curve in the fitting set.")
    st.stop()

target_label = st.selectbox("Target curve for single-fit workflow", working_labels, key="wb_target_curve")
target = curve_option_by_label[target_label]
target_curve_key = target["curve_key"]
target_file = target["file_name"]
target_y_col = target["y_col"]
target_df = dataframes[target_file]

x_full, y_full = _prepare_xy(target_df[x_col].values, target_df[target_y_col].values)
if len(x_full) < 5:
    st.error("Selected curve has too few valid numeric points.")
    st.stop()

# Backend-aware visualization defaults.
active_backend_label = st.session_state.get("wb_fit_backend", "General Peaks")
if st.session_state.get("fit_workbench_last_backend") != active_backend_label:
    if active_backend_label == "SAXS Physics":
        st.session_state["wb_preview_scale"] = "log-log"
        st.session_state["wb_result_scale"] = "log-log"
    st.session_state["fit_workbench_last_backend"] = active_backend_label

st.divider()
st.header("📈 Visualization")
show_preview = st.checkbox("Show selected-curve preview plot", value=False, key="wb_show_preview")
preview_scale = st.selectbox("Preview axis scale", AXIS_SCALE_OPTIONS, index=0, key="wb_preview_scale")
use_viz_range = st.checkbox("Use visualization range", value=True, key="wb_use_viz_range")

viz_x_min, viz_x_max = None, None
if use_viz_range:
    x_min_full = float(np.min(x_full))
    x_max_full = float(np.max(x_full))
    if x_max_full > x_min_full:
        viz_slider_bounds = (x_min_full, x_max_full)
        viz_slider_default = _sanitize_range_pair(
            st.session_state.get("wb_viz_range"),
            viz_slider_bounds,
            [x_min_full, x_max_full],
        )
        pending_viz_range = st.session_state.pop("wb_pending_viz_range_from_editor", None)
        if pending_viz_range is not None:
            viz_slider_default = _sanitize_range_pair(
                pending_viz_range,
                viz_slider_bounds,
                viz_slider_default,
            )
        if viz_slider_default is None:
            viz_slider_default = [x_min_full, x_max_full]
        st.session_state["wb_viz_range"] = (float(viz_slider_default[0]), float(viz_slider_default[1]))
        viz_x_min, viz_x_max = st.slider(
            "Visualization x-range",
            min_value=x_min_full,
            max_value=x_max_full,
            value=(float(viz_slider_default[0]), float(viz_slider_default[1])),
            key="wb_viz_range",
        )

x_viz, y_viz = _prepare_xy(
    target_df[x_col].values,
    target_df[target_y_col].values,
    x_min=viz_x_min,
    x_max=viz_x_max,
)

peak_tol = max(float(np.ptp(x_viz if len(x_viz) else x_full)) / 5000.0, 1e-9)
picked_peaks = st.session_state["fit_workbench_peak_guesses"].setdefault(target_curve_key, [])
picked_peaks[:] = adapter_dedupe_sorted(picked_peaks, peak_tol)

if show_preview:
    if len(x_viz) < 5:
        st.warning("Not enough points in visualization range.")
    else:
        picked_peaks[:] = [p for p in picked_peaks if float(np.min(x_viz)) <= p <= float(np.max(x_viz))]
        existing_fit_state = st.session_state["fit_workbench_results"].get(target_curve_key)

        preview_fig = _build_preview_figure(
            x_viz,
            y_viz,
            x_name=x_col,
            y_name=target_y_col,
            curve_label=target_label,
            peak_positions=picked_peaks,
            fit_state=existing_fit_state,
            scale_mode=preview_scale,
        )

        selection_state = st.plotly_chart(
            preview_fig,
            use_container_width=True,
            key=_safe_widget_key("wb_preview_plot", target_curve_key),
            on_select="rerun",
            selection_mode="points",
        )

        selected_points = []
        try:
            selected_points = list(selection_state.selection.points)
        except Exception:
            selected_points = []
        selected_peak_x = adapter_dedupe_sorted(
            [
                float(p["x"])
                for p in selected_points
                if "x" in p and int(p.get("curve_number", 0)) == 0
            ],
            peak_tol,
        )

        manual_peak_x = st.number_input(
            "Manual peak x",
            value=float(np.median(x_viz)),
            format="%.6f",
            key=_safe_widget_key("wb_manual_peak_x", target_curve_key),
        )

        action_col1, action_col2, action_col3, action_col4 = st.columns(4)
        with action_col1:
            if st.button("➕ Add Selected", key=_safe_widget_key("wb_add_selected", target_curve_key)):
                if selected_peak_x:
                    st.session_state["fit_workbench_peak_guesses"][target_curve_key] = adapter_dedupe_sorted(
                        picked_peaks + selected_peak_x, peak_tol
                    )
                    st.rerun()
                st.warning("No selected points to add.")
        with action_col2:
            if st.button("➕ Add Manual", key=_safe_widget_key("wb_add_manual", target_curve_key)):
                st.session_state["fit_workbench_peak_guesses"][target_curve_key] = adapter_dedupe_sorted(
                    picked_peaks + [float(manual_peak_x)], peak_tol
                )
                st.rerun()
        with action_col3:
            if st.button("↩️ Undo Last", key=_safe_widget_key("wb_undo_peak", target_curve_key)):
                if picked_peaks:
                    st.session_state["fit_workbench_peak_guesses"][target_curve_key] = picked_peaks[:-1]
                    st.rerun()
        with action_col4:
            if st.button("🧹 Clear Peaks", key=_safe_widget_key("wb_clear_peaks", target_curve_key)):
                st.session_state["fit_workbench_peak_guesses"][target_curve_key] = []
                st.rerun()

        current_peaks_preview = adapter_dedupe_sorted(
            st.session_state["fit_workbench_peak_guesses"].get(target_curve_key, []), peak_tol
        )
        if current_peaks_preview:
            st.dataframe(
                pd.DataFrame(
                    {
                        "peak_index": np.arange(1, len(current_peaks_preview) + 1),
                        "x_guess": current_peaks_preview,
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            remove_options = [f"#{idx + 1} @ {value:.6g}" for idx, value in enumerate(current_peaks_preview)]
            peaks_to_remove = st.multiselect(
                "Remove selected peak(s)",
                remove_options,
                key=_safe_widget_key("wb_remove_choices", target_curve_key),
            )
            if st.button("🗑️ Remove Selected Peak(s)", key=_safe_widget_key("wb_remove_selected", target_curve_key)):
                remove_indices = {remove_options.index(item) for item in peaks_to_remove if item in remove_options}
                remaining = [peak for idx, peak in enumerate(current_peaks_preview) if idx not in remove_indices]
                st.session_state["fit_workbench_peak_guesses"][target_curve_key] = remaining
                st.rerun()
        else:
            st.caption("No peak guesses yet.")
else:
    st.caption("Preview hidden. Enable it to visualize the selected curve and pick peaks.")

current_peaks = adapter_dedupe_sorted(st.session_state["fit_workbench_peak_guesses"].get(target_curve_key, []), peak_tol)

st.divider()
st.header("🔬 Fitting")
if not PYFITTING_AVAILABLE:
    st.warning(
        "pyFitting is not available in this environment. "
        f"Import error: {PYFITTING_IMPORT_ERROR or 'unknown'}"
    )
    st.stop()

ready_engine_labels = registry_get_ready_backend_labels(FIT_BACKENDS)
if not ready_engine_labels:
    ready_engine_labels = list(FIT_BACKENDS.keys())
if st.session_state.get("wb_fit_backend") not in ready_engine_labels:
    st.session_state["wb_fit_backend"] = ready_engine_labels[0]
fit_backend_label = st.radio("Fitting backend", ready_engine_labels, horizontal=True, key="wb_fit_backend")
fit_backend = FIT_BACKENDS[fit_backend_label]

fit_use_range = st.checkbox("Use fitting range", value=True, key="wb_use_fit_range")
fit_x_min, fit_x_max = None, None
if fit_use_range:
    fx_min = float(np.min(x_full))
    fx_max = float(np.max(x_full))
    if fx_max > fx_min:
        fit_slider_bounds = (fx_min, fx_max)
        fit_slider_default = _sanitize_range_pair(
            st.session_state.get("wb_fit_range"),
            fit_slider_bounds,
            [fx_min, fx_max],
        )
        pending_fit_range = st.session_state.pop("wb_pending_fit_range_from_editor", None)
        if pending_fit_range is not None:
            fit_slider_default = _sanitize_range_pair(
                pending_fit_range,
                fit_slider_bounds,
                fit_slider_default,
            )
        if fit_slider_default is None:
            fit_slider_default = [fx_min, fx_max]
        st.session_state["wb_fit_range"] = (float(fit_slider_default[0]), float(fit_slider_default[1]))
        fit_x_min, fit_x_max = st.slider(
            "Fitting x-range",
            min_value=fx_min,
            max_value=fx_max,
            value=(float(fit_slider_default[0]), float(fit_slider_default[1])),
            key="wb_fit_range",
        )

x_fit, y_fit_data = _prepare_xy(
    target_df[x_col].values,
    target_df[target_y_col].values,
    x_min=fit_x_min,
    x_max=fit_x_max,
)
if len(x_fit) < 5:
    st.error("Not enough points remain after fitting-range filtering.")
    st.stop()

with st.expander("🤖 ML Assist (optional)", expanded=False):
    st.caption("Use ML/heuristic seed models to initialize peak guesses or SAXS settings.")
    ml_catalog = [row for row in adapter_list_ml_models() if str(row.get("status", "")).lower() in {"ready", "fallback"}]
    ml_label_options = [str(row.get("label", row.get("key", "model"))) for row in ml_catalog]
    ml_lookup = {str(row.get("label", row.get("key", "model"))): row for row in ml_catalog}

    if not ml_label_options:
        st.info("No ML seed model is available in this environment.")
    else:
        preferred_backend = "saxs_physics" if fit_backend == FIT_BACKENDS["SAXS Physics"] else "general_peaks"
        default_ml_idx = 0
        for idx, label in enumerate(ml_label_options):
            target_backend = str(ml_lookup[label].get("target_backend", "")).strip().lower()
            if target_backend == preferred_backend:
                default_ml_idx = idx
                break
        ml_model_label = st.selectbox("ML seed model", ml_label_options, index=default_ml_idx, key="wb_ml_model_label")
        selected_ml = ml_lookup[ml_model_label]
        st.caption(
            f"Target backend: `{selected_ml.get('target_backend', 'unknown')}` | "
            f"status: `{selected_ml.get('status', 'unknown')}`"
        )
        st.caption(str(selected_ml.get("description", "")))

        ml_col1, ml_col2, ml_col3, ml_col4 = st.columns(4)
        with ml_col1:
            ml_log_y_default = bool(fit_backend == FIT_BACKENDS["SAXS Physics"])
            ml_log_y = st.checkbox("log(y) preprocess", value=ml_log_y_default, key="wb_ml_log_y")
        with ml_col2:
            ml_normalize = st.checkbox("normalize(y)", value=True, key="wb_ml_normalize")
        with ml_col3:
            ml_smooth_window = st.number_input(
                "smooth window",
                min_value=1,
                max_value=51,
                value=7,
                step=2,
                key="wb_ml_smooth_window",
            )
        with ml_col4:
            ml_resample_points = st.number_input(
                "resample points",
                min_value=64,
                max_value=2048,
                value=256,
                step=32,
                key="wb_ml_resample_points",
            )

        if st.button("🧠 Run ML Seed", key="wb_run_ml_seed"):
            try:
                ml_result = adapter_run_ml_prediction(
                    x_fit,
                    y_fit_data,
                    model_key=str(selected_ml.get("key", "")),
                    log_y=bool(ml_log_y),
                    normalize_y=bool(ml_normalize),
                    smooth_window=int(ml_smooth_window),
                    resample_points=int(ml_resample_points),
                )
                st.session_state["fit_workbench_ml_predictions"][target_curve_key] = ml_result
                st.success("ML seed generated.")
            except Exception as ml_error:
                st.error(f"ML seed failed: {ml_error}")

        ml_result = st.session_state["fit_workbench_ml_predictions"].get(target_curve_key)
        if ml_result:
            pred = dict(ml_result.get("prediction", {}))
            confidence = pred.get("confidence")
            pcol1, pcol2, pcol3 = st.columns(3)
            pcol1.metric("Recommended backend", str(pred.get("recommended_backend", "-")))
            pcol2.metric("Model key", str(pred.get("model_key", "-")))
            pcol3.metric("Confidence", adapter_format_metric(confidence))
            if pred.get("notes"):
                st.caption(str(pred.get("notes")))

            peak_centers = pred.get("peak_centers") or []
            if peak_centers:
                st.dataframe(
                    pd.DataFrame({"peak_index": np.arange(1, len(peak_centers) + 1), "x_center": peak_centers}),
                    use_container_width=True,
                    hide_index=True,
                )

            apply_ml_seed = st.button("✨ Apply ML Seed To Controls", key="wb_apply_ml_seed")
            if apply_ml_seed:
                rec_backend = str(pred.get("recommended_backend", "")).strip().lower()
                backend_key_to_label = {value: key for key, value in FIT_BACKENDS.items()}
                if rec_backend in backend_key_to_label:
                    st.session_state["wb_fit_backend"] = backend_key_to_label[rec_backend]

                if rec_backend == "general_peaks":
                    peak_shape_label = str(pred.get("peak_shape_label", "")).strip()
                    if peak_shape_label in FIT_SHAPES:
                        st.session_state["wb_fit_shape"] = peak_shape_label

                    peak_count = pred.get("peak_count")
                    if peak_count is not None:
                        try:
                            peak_count = int(np.clip(int(round(float(peak_count))), 1, 12))
                            st.session_state["wb_fit_default_peak_count"] = peak_count
                        except Exception:
                            pass

                    centers = []
                    for value in pred.get("peak_centers") or []:
                        try:
                            fv = float(value)
                            if np.isfinite(fv):
                                centers.append(fv)
                        except Exception:
                            continue
                    if centers:
                        local_tol = max(float(np.ptp(x_fit)) / 5000.0, 1e-9)
                        st.session_state["fit_workbench_peak_guesses"][target_curve_key] = adapter_dedupe_sorted(
                            centers,
                            local_tol,
                        )
                        st.session_state["wb_use_manual_peaks_single"] = True

                if rec_backend == "saxs_physics":
                    saxs_shape_key = str(pred.get("saxs_shape", "")).strip().lower()
                    saxs_label_to_key, _ = get_saxs_shape_options()
                    if not saxs_label_to_key:
                        saxs_label_to_key = dict(SAXS_MODEL_LABEL_TO_KEY)
                    for label, key in saxs_label_to_key.items():
                        if str(key).lower() == saxs_shape_key:
                            st.session_state["wb_saxs_shape"] = label
                            break

                    if pred.get("saxs_polydisperse") is not None:
                        st.session_state["wb_saxs_poly"] = bool(pred.get("saxs_polydisperse"))
                    if pred.get("saxs_use_porod") is not None:
                        st.session_state["wb_saxs_porod"] = bool(pred.get("saxs_use_porod"))

                    initial_overrides = pred.get("initial_overrides") or {}
                    if initial_overrides:
                        st.session_state["wb_saxs_use_init_overrides"] = True
                    for source_key, state_key in [
                        ("radius", "wb_saxs_init_radius"),
                        ("scale", "wb_saxs_init_scale"),
                        ("background", "wb_saxs_init_background"),
                        ("sigma_rel", "wb_saxs_init_sigma_rel"),
                        ("porod_scale", "wb_saxs_init_porod_scale"),
                        ("porod_exp", "wb_saxs_init_porod_exp"),
                    ]:
                        if source_key in initial_overrides:
                            try:
                                st.session_state[state_key] = float(initial_overrides[source_key])
                            except Exception:
                                pass

                ml_record = {
                    "model_key": pred.get("model_key"),
                    "confidence": pred.get("confidence"),
                }
                st.session_state["fit_workbench_ml_applied"][target_curve_key] = ml_record
                st.success("ML seed applied to current fitting controls.")
                st.rerun()

fit_shape_label = str(st.session_state.get("wb_fit_shape", "Gaussian"))
if fit_shape_label not in FIT_SHAPES:
    fit_shape_label = "Gaussian"
fit_shape = FIT_SHAPES[fit_shape_label]
fit_maxiter = int(st.session_state.get("wb_fit_maxiter", 2000))
batch_default_peaks = int(st.session_state.get("wb_fit_default_peak_count", max(1, len(current_peaks))))
batch_default_peaks = int(np.clip(batch_default_peaks, 1, 12))
use_manual_peaks_single = bool(st.session_state.get("wb_use_manual_peaks_single", True))

saxs_shape = None
saxs_shape_label = None
saxs_polydisperse = bool(st.session_state.get("wb_saxs_poly", False))
saxs_use_porod = bool(st.session_state.get("wb_saxs_porod", False))
saxs_maxiter = int(st.session_state.get("wb_saxs_maxiter", 2000))
saxs_initial_overrides = None

with st.expander("🧠 General Peaks Engine", expanded=fit_backend == FIT_BACKENDS["General Peaks"]):
    st.caption("Generic multi-peak fitting route for broad 1D use-cases.")
    if fit_backend != FIT_BACKENDS["General Peaks"]:
        st.caption("Set backend to `General Peaks` above to configure and run.")
    else:
        gcol1, gcol2, gcol3 = st.columns(3)
        with gcol1:
            fit_shape_label = st.selectbox("Fit shape", list(FIT_SHAPES.keys()), index=0, key="wb_fit_shape")
            fit_shape = FIT_SHAPES[fit_shape_label]
        with gcol2:
            fit_maxiter = st.number_input(
                "Max iterations",
                min_value=100,
                max_value=10000,
                value=int(fit_maxiter),
                step=100,
                key="wb_fit_maxiter",
            )
        with gcol3:
            batch_default_peaks = st.number_input(
                "Default peaks when no picks",
                min_value=1,
                max_value=12,
                value=max(1, len(current_peaks)),
                step=1,
                key="wb_fit_default_peak_count",
            )

        use_manual_peaks_single = st.checkbox(
            "Use manual peak guesses for single fit",
            value=True,
            key="wb_use_manual_peaks_single",
        )
        if use_manual_peaks_single and current_peaks:
            n_peaks_single = len(current_peaks)
            peak_guesses_single = current_peaks
        else:
            n_peaks_single = int(batch_default_peaks)
            peak_guesses_single = []

        run_single_fit = st.button("🚀 Run Single Fit", key="wb_run_single_fit_general")
        if run_single_fit:
            try:
                fit_state = run_general_peak_fit(
                    x_fit,
                    y_fit_data,
                    shape=fit_shape,
                    shape_label=fit_shape_label,
                    n_peaks=int(n_peaks_single),
                    maxiter=int(fit_maxiter),
                    peak_guesses=peak_guesses_single,
                    x_col_name=x_col,
                    y_col_name=target_y_col,
                )
                fit_state.update(
                    {
                        "source_file": target_file,
                        "source_curve_key": target_curve_key,
                        "curve_label": target_label,
                    }
                )
                ml_applied = st.session_state["fit_workbench_ml_applied"].get(target_curve_key, {})
                if ml_applied:
                    fit_state["ml_seed_model"] = ml_applied.get("model_key")
                    fit_state["ml_seed_confidence"] = ml_applied.get("confidence")
                st.session_state["fit_workbench_results"][target_curve_key] = fit_state
                if fit_state.get("success"):
                    st.success("Single fit completed.")
                else:
                    st.warning(f"Single fit completed with warning: {fit_state.get('message')}")
            except Exception as fit_error:
                st.error(f"Single fit failed: {fit_error}")

saxs_label_to_key_editor, _ = get_saxs_shape_options()
if not saxs_label_to_key_editor:
    saxs_label_to_key_editor = dict(SAXS_MODEL_LABEL_TO_KEY)
saxs_shape_labels_editor = list(saxs_label_to_key_editor.keys())

with st.expander("🪐 SAXS Form-Factor Engine", expanded=fit_backend == FIT_BACKENDS["SAXS Physics"]):
    st.caption("Physics-aware SAXS fitting route for form-factor analysis.")
    if fit_backend != FIT_BACKENDS["SAXS Physics"]:
        st.caption("Set backend to `SAXS Physics` above to configure and run.")
    elif not PYSAXS_AVAILABLE:
        st.warning(
            "SAXS backend unavailable. "
            f"Import error: {PYSAXS_IMPORT_ERROR or 'unknown'}"
        )
    else:
        saxs_label_to_key, _ = get_saxs_shape_options()
        if not saxs_label_to_key:
            saxs_label_to_key = dict(SAXS_MODEL_LABEL_TO_KEY)
        scol1, scol2, scol3, scol4 = st.columns(4)
        with scol1:
            saxs_shape_label = st.selectbox("SAXS model", list(saxs_label_to_key.keys()), key="wb_saxs_shape")
            saxs_shape = saxs_label_to_key[saxs_shape_label]
        with scol2:
            saxs_polydisperse = st.checkbox("Polydisperse", value=bool(saxs_polydisperse), key="wb_saxs_poly")
        with scol3:
            saxs_use_porod = st.checkbox("Use Porod term", value=bool(saxs_use_porod), key="wb_saxs_porod")
        with scol4:
            saxs_maxiter = st.number_input(
                "Max iterations",
                min_value=100,
                max_value=20000,
                value=int(saxs_maxiter),
                step=100,
                key="wb_saxs_maxiter",
            )

        default_overrides = _default_saxs_initial_overrides(
            x_fit,
            y_fit_data,
            polydisperse=bool(saxs_polydisperse),
            use_porod=bool(saxs_use_porod),
        )
        for override_key, state_key in [
            ("radius", "wb_saxs_init_radius"),
            ("scale", "wb_saxs_init_scale"),
            ("background", "wb_saxs_init_background"),
            ("sigma_rel", "wb_saxs_init_sigma_rel"),
            ("porod_scale", "wb_saxs_init_porod_scale"),
            ("porod_exp", "wb_saxs_init_porod_exp"),
        ]:
            if state_key not in st.session_state and override_key in default_overrides:
                st.session_state[state_key] = float(default_overrides[override_key])

        use_saxs_init_overrides = st.checkbox(
            "Override SAXS initial guesses",
            value=bool(st.session_state.get("wb_saxs_use_init_overrides", True)),
            key="wb_saxs_use_init_overrides",
            help="Apply the same initial parameter guesses to single and batch SAXS fitting.",
        )
        if use_saxs_init_overrides:
            ocol1, ocol2, ocol3 = st.columns(3)
            with ocol1:
                init_radius = st.number_input(
                    "Init radius",
                    min_value=1e-6,
                    format="%.6g",
                    key="wb_saxs_init_radius",
                )
            with ocol2:
                init_scale = st.number_input(
                    "Init scale",
                    min_value=1e-12,
                    format="%.6g",
                    key="wb_saxs_init_scale",
                )
            with ocol3:
                init_background = st.number_input(
                    "Init background",
                    format="%.6g",
                    key="wb_saxs_init_background",
                )

            saxs_initial_overrides = {
                "radius": float(init_radius),
                "scale": float(init_scale),
                "background": float(init_background),
            }

            if saxs_polydisperse:
                init_sigma_rel = st.number_input(
                    "Init sigma_rel",
                    min_value=0.0,
                    max_value=2.0,
                    step=0.01,
                    format="%.4f",
                    key="wb_saxs_init_sigma_rel",
                )
                saxs_initial_overrides["sigma_rel"] = float(init_sigma_rel)

            if saxs_use_porod:
                pcol1, pcol2 = st.columns(2)
                with pcol1:
                    init_porod_scale = st.number_input(
                        "Init porod_scale",
                        min_value=0.0,
                        format="%.6g",
                        key="wb_saxs_init_porod_scale",
                    )
                with pcol2:
                    init_porod_exp = st.number_input(
                        "Init porod_exp",
                        min_value=0.0,
                        max_value=8.0,
                        step=0.1,
                        format="%.3f",
                        key="wb_saxs_init_porod_exp",
                    )
                saxs_initial_overrides["porod_scale"] = float(init_porod_scale)
                saxs_initial_overrides["porod_exp"] = float(init_porod_exp)
            st.caption("These overrides are applied to both single and batch SAXS fits.")

        run_single_fit = st.button("🚀 Run Single Fit", key="wb_run_single_fit_saxs")
        if run_single_fit:
            try:
                fit_state = run_saxs_fit(
                    x_fit,
                    y_fit_data,
                    shape=saxs_shape,
                    shape_label=saxs_shape_label,
                    polydisperse=bool(saxs_polydisperse),
                    use_porod=bool(saxs_use_porod),
                    maxiter=int(saxs_maxiter),
                    x_col_name=x_col,
                    y_col_name=target_y_col,
                    initial_overrides=saxs_initial_overrides,
                )
                fit_state.update(
                    {
                        "source_file": target_file,
                        "source_curve_key": target_curve_key,
                        "curve_label": target_label,
                    }
                )
                ml_applied = st.session_state["fit_workbench_ml_applied"].get(target_curve_key, {})
                if ml_applied:
                    fit_state["ml_seed_model"] = ml_applied.get("model_key")
                    fit_state["ml_seed_confidence"] = ml_applied.get("confidence")
                st.session_state["fit_workbench_results"][target_curve_key] = fit_state
                if fit_state.get("success"):
                    st.success("Single fit completed.")
                else:
                    st.warning(f"Single fit completed with warning: {fit_state.get('message')}")
            except Exception as fit_error:
                st.error(f"Single fit failed: {fit_error}")

if fit_use_range and fit_x_min is None and fit_x_max is None:
    fit_x_min = float(np.min(x_full))
    fit_x_max = float(np.max(x_full))
if use_viz_range and viz_x_min is None and viz_x_max is None:
    viz_x_min = float(np.min(x_full))
    viz_x_max = float(np.max(x_full))

selected_saxs_shape_label = saxs_shape_label
if selected_saxs_shape_label not in saxs_shape_labels_editor:
    fallback_saxs_shape_label = st.session_state.get("wb_saxs_shape")
    if fallback_saxs_shape_label in saxs_shape_labels_editor:
        selected_saxs_shape_label = str(fallback_saxs_shape_label)
    elif saxs_shape_labels_editor:
        selected_saxs_shape_label = saxs_shape_labels_editor[0]
    else:
        selected_saxs_shape_label = None

use_saxs_init_overrides = bool(st.session_state.get("wb_saxs_use_init_overrides", True))
saxs_initial_overrides_editor = {
    "radius": _to_float(st.session_state.get("wb_saxs_init_radius"), 100.0, 1e-6),
    "scale": _to_float(st.session_state.get("wb_saxs_init_scale"), 1.0, 1e-12),
    "background": _to_float(st.session_state.get("wb_saxs_init_background"), 0.0),
}
if saxs_polydisperse:
    saxs_initial_overrides_editor["sigma_rel"] = _to_float(
        st.session_state.get("wb_saxs_init_sigma_rel"),
        0.10,
        0.0,
        2.0,
    )
if saxs_use_porod:
    saxs_initial_overrides_editor["porod_scale"] = _to_float(
        st.session_state.get("wb_saxs_init_porod_scale"),
        0.01,
        0.0,
    )
    saxs_initial_overrides_editor["porod_exp"] = _to_float(
        st.session_state.get("wb_saxs_init_porod_exp"),
        4.0,
        0.0,
        8.0,
    )

viz_range_for_spec = [float(viz_x_min), float(viz_x_max)] if use_viz_range and viz_x_min is not None and viz_x_max is not None else None
fit_range_for_spec = [float(fit_x_min), float(fit_x_max)] if fit_use_range and fit_x_min is not None and fit_x_max is not None else None

current_wb_setup_spec = _build_wb_setup_spec(
    x_col=x_col,
    working_curves=working_labels,
    target_curve=target_label,
    show_preview=show_preview,
    preview_scale=preview_scale,
    use_viz_range=use_viz_range,
    viz_range=viz_range_for_spec,
    fit_backend_label=fit_backend_label,
    fit_use_range=fit_use_range,
    fit_range=fit_range_for_spec,
    fit_shape_label=fit_shape_label,
    fit_maxiter=fit_maxiter,
    batch_default_peaks=batch_default_peaks,
    use_manual_peaks_single=use_manual_peaks_single,
    saxs_shape_label=selected_saxs_shape_label,
    saxs_polydisperse=saxs_polydisperse,
    saxs_use_porod=saxs_use_porod,
    saxs_maxiter=saxs_maxiter,
    use_saxs_init_overrides=use_saxs_init_overrides,
    saxs_initial_overrides=saxs_initial_overrides_editor,
)
st.session_state["wb_current_setup_spec"] = current_wb_setup_spec

if not st.session_state.get("wb_editor_code"):
    st.session_state["wb_editor_code"] = _generate_wb_editor_python(current_wb_setup_spec)

st.divider()
st.header("🧠 Python Fitting Setup Editor (Experimental)")
st.caption("Two-way control: GUI -> Python script -> GUI.")
st.caption("Code runs in the app process. Only run trusted code.")

pending_editor_code = st.session_state.pop("wb_editor_code_pending", None)
if pending_editor_code is not None:
    st.session_state["wb_editor_code"] = pending_editor_code

wb_editor_code = st.text_area(
    "Editable Python script",
    key="wb_editor_code",
    height=300,
    help="Edit plot_spec and click 'Run Edited Python' to sync fitting controls.",
)

wb_ed_col1, wb_ed_col2 = st.columns(2)
with wb_ed_col1:
    if st.button("🧾 Show Python from Current GUI", key="wb_editor_generate"):
        st.session_state["wb_editor_code_pending"] = _generate_wb_editor_python(current_wb_setup_spec)
        st.session_state["wb_editor_status"] = "Editor refreshed from current GUI state."
        st.session_state["wb_editor_warnings"] = []
        st.rerun()

with wb_ed_col2:
    if st.button("▶️ Run Edited Python", key="wb_editor_run", type="primary"):
        try:
            normalized_spec, warnings = _execute_wb_editor(
                wb_editor_code,
                current_wb_setup_spec,
                dataframes=dataframes,
                all_columns=all_columns,
                backend_labels=ready_engine_labels,
                saxs_shape_labels=saxs_shape_labels_editor,
            )
            st.session_state["wb_pending_setup_spec"] = normalized_spec
            st.session_state["wb_editor_status"] = "Script applied. GUI synced from edited plot_spec."
            st.session_state["wb_editor_warnings"] = warnings
            st.rerun()
        except Exception as exc:
            st.session_state["wb_editor_status"] = f"Script execution failed: {exc}"
            st.session_state["wb_editor_warnings"] = []

if st.session_state.get("wb_editor_status"):
    status_text = str(st.session_state["wb_editor_status"])
    if status_text.lower().startswith("script execution failed"):
        st.error(status_text)
    else:
        st.success(status_text)
for warning_text in st.session_state.get("wb_editor_warnings", []):
    st.warning(str(warning_text))

with st.expander("🧭 Planned 1D Engines", expanded=False):
    planned_rows = registry_list_engine_rows(status="planned")
    if planned_rows:
        schema_preview_rows = []
        for row in planned_rows:
            engine_key = str(row.get("key", ""))
            for schema_row in registry_get_engine_schema_rows(engine_key):
                schema_preview_rows.append(
                    {
                        "engine": row.get("label", engine_key),
                        "section": schema_row.get("section"),
                        "name": schema_row.get("name"),
                        "type": schema_row.get("type"),
                        "default": schema_row.get("default"),
                    }
                )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "engine": row.get("label"),
                        "domain": row.get("domain"),
                        "status": row.get("status"),
                        "notes": row.get("description"),
                    }
                    for row in planned_rows
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        if schema_preview_rows:
            with st.expander("Planned Engine Config Stubs", expanded=False):
                st.dataframe(pd.DataFrame(schema_preview_rows), use_container_width=True, hide_index=True)

single_fit_state = st.session_state["fit_workbench_results"].get(target_curve_key)
with st.expander("📋 Single-Fit Results", expanded=bool(single_fit_state)):
    if single_fit_state:
        result_scale = st.selectbox("Result axis scale", AXIS_SCALE_OPTIONS, index=0, key="wb_result_scale")
        if single_fit_state.get("success"):
            st.success(f"Status: success ({single_fit_state.get('message', 'ok')})")
        else:
            st.warning(f"Status: failed ({single_fit_state.get('message', 'unknown')})")

        fit_plot = adapter_create_fit_plot_figure(single_fit_state)
        _apply_axis_scale(fit_plot, result_scale)
        st.plotly_chart(fit_plot, use_container_width=True)

        metrics = single_fit_state.get("metrics", {})
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("R²", adapter_format_metric(metrics.get("r2")))
        m2.metric("RMSE", adapter_format_metric(metrics.get("rmse")))
        m3.metric("MAE", adapter_format_metric(metrics.get("mae")))
        m4.metric("Chi²(red)", adapter_format_metric(metrics.get("chi2_reduced")))

        param_rows = [{"parameter": k, "value": v} for k, v in sorted(single_fit_state.get("params", {}).items())]
        with st.expander("Model Parameters", expanded=False):
            if param_rows:
                st.dataframe(pd.DataFrame(param_rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No model parameters available.")

        component_table = single_fit_state.get("component_table", [])
        with st.expander("Component Parameters", expanded=False):
            if component_table:
                st.dataframe(pd.DataFrame(component_table), use_container_width=True, hide_index=True)
            else:
                st.caption("No component table available.")

        metric_rows = [{"metric": k, "value": v} for k, v in sorted(metrics.items())]
        with st.expander("Fit Metrics (all)", expanded=False):
            if metric_rows:
                st.dataframe(pd.DataFrame(metric_rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No fit metrics available.")

        single_zip = adapter_build_fit_zip_bytes(single_fit_state)
        single_export_name = adapter_sanitize_filename(single_fit_state.get("curve_label") or target_curve_key)
        export_col1, export_col2 = st.columns(2)
        with export_col1:
            st.download_button(
                label="💾 Export This Fit (ZIP)",
                data=single_zip,
                file_name=f"{single_export_name}_fit_results.zip",
                mime="application/zip",
                key=_safe_widget_key("wb_export_single_zip", target_curve_key),
            )
        with export_col2:
            if st.button("💾 Save This Fit to Server", key=_safe_widget_key("wb_save_single_server", target_curve_key)):
                saved = adapter_save_single_fit_to_server(single_fit_state)
                st.success(f"Saved fit files to `{saved['run_dir']}`")
    else:
        st.info("Run a single fit to view results.")

# Batch fitting
st.divider()
with st.expander("📦 Batch Fitting", expanded=False):
    batch_options = list(curve_labels)
    batch_options_signature = tuple(batch_options)
    if st.session_state.get("wb_batch_options_signature") != batch_options_signature:
        st.session_state["wb_batch_curves"] = list(batch_options)
        st.session_state["wb_batch_options_signature"] = batch_options_signature

    batch_labels = st.multiselect(
        "Curves to batch fit",
        batch_options,
        default=batch_options,
        key="wb_batch_curves",
    )
    if fit_backend == FIT_BACKENDS["SAXS Physics"]:
        st.caption(
            "Batch SAXS uses the same setup as single fit: model, polydispersity, Porod, max iterations, and initial guesses."
        )
    batch_use_fit_range = st.checkbox("Use fitting x-range for batch", value=fit_use_range, key="wb_batch_use_range")
    if fit_backend == FIT_BACKENDS["General Peaks"]:
        batch_use_manual_peaks = st.checkbox(
            "Use per-curve manual peak guesses when available",
            value=True,
            key="wb_batch_use_manual",
        )
    else:
        batch_use_manual_peaks = False
        st.caption("Manual peak guesses apply only to General Peaks. SAXS batch uses SAXS model settings and initial guesses.")
    batch_run = st.button("🚀 Run Batch Fit", key="wb_run_batch_fit", disabled=not batch_labels)

    if batch_run:
        if fit_backend == FIT_BACKENDS["SAXS Physics"] and not PYSAXS_AVAILABLE:
            st.error(
                "SAXS backend unavailable for batch fitting. "
                f"Import error: {PYSAXS_IMPORT_ERROR or 'unknown'}"
            )
        else:
            summary_rows = []
            for label in batch_labels:
                item = curve_option_by_label[label]
                curve_key = item["curve_key"]
                file_name = item["file_name"]
                y_name = item["y_col"]
                df_curve = dataframes[file_name]
                bx, by = _prepare_xy(
                    df_curve[x_col].values,
                    df_curve[y_name].values,
                    x_min=fit_x_min if batch_use_fit_range else None,
                    x_max=fit_x_max if batch_use_fit_range else None,
                )
                if len(bx) < 5:
                    summary_rows.append(
                        {
                            "curve_key": curve_key,
                            "curve": label,
                            "status": "failed",
                            "message": "not enough points after filtering",
                            "shape": np.nan,
                            "r2": np.nan,
                            "rmse": np.nan,
                        }
                    )
                    continue

                try:
                    if fit_backend == FIT_BACKENDS["General Peaks"]:
                        manual_peaks = adapter_dedupe_sorted(
                            st.session_state["fit_workbench_peak_guesses"].get(curve_key, []),
                            max(float(np.ptp(bx)) / 5000.0, 1e-9),
                        )
                        if batch_use_manual_peaks and manual_peaks:
                            n_peaks = len(manual_peaks)
                            peak_guesses = manual_peaks
                        else:
                            n_peaks = int(batch_default_peaks)
                            peak_guesses = []

                        fit_state = run_general_peak_fit(
                            bx,
                            by,
                            shape=fit_shape,
                            shape_label=fit_shape_label,
                            n_peaks=n_peaks,
                            maxiter=int(fit_maxiter),
                            peak_guesses=peak_guesses,
                            x_col_name=x_col,
                            y_col_name=y_name,
                        )
                    else:
                        fit_state = run_saxs_fit(
                            bx,
                            by,
                            shape=saxs_shape,
                            shape_label=saxs_shape_label,
                            polydisperse=bool(saxs_polydisperse),
                            use_porod=bool(saxs_use_porod),
                            maxiter=int(saxs_maxiter),
                            x_col_name=x_col,
                            y_col_name=y_name,
                            initial_overrides=saxs_initial_overrides,
                        )

                    fit_state.update(
                        {
                            "source_file": file_name,
                            "source_curve_key": curve_key,
                            "curve_label": label,
                        }
                    )
                    ml_applied = st.session_state["fit_workbench_ml_applied"].get(curve_key, {})
                    if ml_applied:
                        fit_state["ml_seed_model"] = ml_applied.get("model_key")
                        fit_state["ml_seed_confidence"] = ml_applied.get("confidence")
                    st.session_state["fit_workbench_results"][curve_key] = fit_state
                    summary_rows.append(
                        {
                            "curve_key": curve_key,
                            "curve": label,
                            "status": "success" if fit_state.get("success") else "failed",
                            "message": fit_state.get("message"),
                            "shape": fit_state.get("shape_label", fit_state.get("shape")),
                            "r2": fit_state.get("metrics", {}).get("r2"),
                            "rmse": fit_state.get("metrics", {}).get("rmse"),
                        }
                    )
                except Exception as batch_error:
                    summary_rows.append(
                        {
                            "curve_key": curve_key,
                            "curve": label,
                            "status": "failed",
                            "message": str(batch_error),
                            "shape": np.nan,
                            "r2": np.nan,
                            "rmse": np.nan,
                        }
                    )

            st.session_state["fit_workbench_batch_summary"] = summary_rows
            st.rerun()

    batch_summary = st.session_state.get("fit_workbench_batch_summary", [])
    if batch_summary:
        batch_df = pd.DataFrame(batch_summary)
        st.markdown("**Batch summary**")
        st.dataframe(batch_df, use_container_width=True, hide_index=True)

        successful_states = {}
        for row in batch_summary:
            if row.get("status") == "success":
                ck = row.get("curve_key")
                state = st.session_state["fit_workbench_results"].get(ck) if ck else None
                if ck and state:
                    successful_states[ck] = state

        if successful_states:
            batch_zip = adapter_build_batch_fit_zip_bytes(successful_states)
            bcol1, bcol2 = st.columns(2)
            with bcol1:
                st.download_button(
                    label="💾 Export Batch Results (ZIP)",
                    data=batch_zip,
                    file_name="fit_workbench_batch_results.zip",
                    mime="application/zip",
                    key="wb_batch_export_zip",
                )
            with bcol2:
                if st.button("💾 Save Batch to Server", key="wb_batch_save_server"):
                    saved = adapter_save_batch_fit_to_server(successful_states, batch_summary)
                    st.success(f"Saved batch files to `{saved['run_dir']}`")

            inspect_rows = [
                row
                for row in batch_summary
                if row.get("status") == "success" and row.get("curve_key") in successful_states
            ]
            inspect_labels = [str(row.get("curve", row.get("curve_key"))) for row in inspect_rows]
            inspect_label_to_curve = {
                str(row.get("curve", row.get("curve_key"))): str(row.get("curve_key")) for row in inspect_rows
            }
            if inspect_labels:
                inspect_signature = tuple(inspect_labels)
                if st.session_state.get("wb_batch_inspect_signature") != inspect_signature:
                    st.session_state["wb_batch_inspect_labels"] = inspect_labels[:1]
                    st.session_state["wb_batch_inspect_signature"] = inspect_signature

                current_batch_scale = st.session_state.get(
                    "wb_batch_result_scale",
                    st.session_state.get("wb_result_scale", AXIS_SCALE_OPTIONS[0]),
                )
                if current_batch_scale not in AXIS_SCALE_OPTIONS:
                    current_batch_scale = AXIS_SCALE_OPTIONS[0]
                st.session_state["wb_batch_result_scale"] = current_batch_scale

                st.markdown("**Batch Fit Inspector**")
                batch_result_scale = st.selectbox(
                    "Inspector axis scale",
                    AXIS_SCALE_OPTIONS,
                    index=AXIS_SCALE_OPTIONS.index(current_batch_scale),
                    key="wb_batch_result_scale",
                )
                inspect_selection = st.multiselect(
                    "Inspect fitted curve(s)",
                    inspect_labels,
                    default=inspect_labels[:1],
                    key="wb_batch_inspect_labels",
                )
                for inspect_label in inspect_selection:
                    curve_key = inspect_label_to_curve.get(inspect_label)
                    fit_state = successful_states.get(curve_key) if curve_key else None
                    if not fit_state:
                        continue
                    with st.expander(f"Result: {inspect_label}", expanded=len(inspect_selection) == 1):
                        inspect_plot = adapter_create_fit_plot_figure(fit_state)
                        _apply_axis_scale(inspect_plot, batch_result_scale)
                        st.plotly_chart(inspect_plot, use_container_width=True)

                        inspect_metrics = fit_state.get("metrics", {})
                        im1, im2, im3, im4 = st.columns(4)
                        im1.metric("R²", adapter_format_metric(inspect_metrics.get("r2")))
                        im2.metric("RMSE", adapter_format_metric(inspect_metrics.get("rmse")))
                        im3.metric("MAE", adapter_format_metric(inspect_metrics.get("mae")))
                        im4.metric("Chi²(red)", adapter_format_metric(inspect_metrics.get("chi2_reduced")))

                        with st.expander("Parameters", expanded=False):
                            inspect_param_rows = [
                                {"parameter": k, "value": v} for k, v in sorted(fit_state.get("params", {}).items())
                            ]
                            if inspect_param_rows:
                                st.dataframe(pd.DataFrame(inspect_param_rows), use_container_width=True, hide_index=True)
                            inspect_component_rows = fit_state.get("component_table", [])
                            if inspect_component_rows:
                                st.dataframe(pd.DataFrame(inspect_component_rows), use_container_width=True, hide_index=True)
