#!/usr/bin/env python3
"""
Enhanced CSV/NPZ Plotter - Quick visualization with per-curve styling.

Features:
- CSV, TXT, DAT, NPZ file support
- Individual color/marker selection per curve
- Smart filename display
- Multi-curve overlay
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402

import streamlit as st  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pathlib import Path  # noqa: E402
import io  # noqa: E402
import sys  # noqa: E402
import copy  # noqa: E402
import pprint  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

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
# Styling options
# ---------------------------------------------------------------------------
COLORS_NAMED = {
    'Blue': '#1f77b4', 'Orange': '#ff7f0e', 'Green': '#2ca02c',
    'Red': '#d62728', 'Purple': '#9467bd', 'Brown': '#8c564b',
    'Pink': '#e377c2', 'Gray': '#7f7f7f', 'Olive': '#bcbd22',
    'Cyan': '#17becf', 'Navy': '#000080', 'Black': '#000000', 'Magenta': '#FF00FF',
    'Yellow': '#FFD700', 'Teal': '#008080', 'Lime': '#00FF00'
}

MARKERS_DICT = {
    'Circle': 'o', 'Square': 's', 'Triangle Up': '^', 'Triangle Down': 'v',
    'Diamond': 'D', 'Pentagon': 'p', 'Star': '*', 'Hexagon': 'h',
    'Plus': '+', 'X': 'x', 'Point': '.', 'None': 'None'
}

LINESTYLES_DICT = {
    'Solid': '-', 'Dashed': '--', 'Dash-dot': '-.', 'Dotted': ':',
    'None': 'None'
}

PLOT_MODE_OPTIONS = ["Interactive (Plotly)", "Static (Matplotlib)"]
SCALE_OPTIONS = ["linear", "log"]


def _default_curve_style(curve_idx):
    """Return default style dict for one curve."""
    return {
        'color': list(COLORS_NAMED.keys())[curve_idx % len(COLORS_NAMED)],
        'marker': list(MARKERS_DICT.keys())[curve_idx % len(MARKERS_DICT)],
        'linestyle': 'Solid',
        'linewidth': 2.0,
        'markersize': 8.0,
        'alpha': 0.8,
        'enabled': True,
    }


def _to_bool(value, default=False):
    """Convert arbitrary value to bool with fallback."""
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
    """Convert value to float with optional clamp."""
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
    """Convert value to int with optional clamp."""
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


def _normalize_color_name(value, fallback='Blue'):
    """Normalize color representation to one of COLORS_NAMED keys."""
    if isinstance(value, str):
        if value in COLORS_NAMED:
            return value
        for color_name in COLORS_NAMED:
            if value.lower() == color_name.lower():
                return color_name
        try:
            normalized_hex = mcolors.to_hex(value).lower()
        except Exception:
            normalized_hex = None
        if normalized_hex:
            for color_name, color_hex in COLORS_NAMED.items():
                if normalized_hex == mcolors.to_hex(color_hex).lower():
                    return color_name
        for color_name, color_hex in COLORS_NAMED.items():
            if value.lower() == color_hex.lower():
                return color_name
    return fallback if fallback in COLORS_NAMED else 'Blue'


def _normalize_marker_name(value, fallback='Circle'):
    """Normalize marker representation to one of MARKERS_DICT keys."""
    if isinstance(value, str):
        if value in MARKERS_DICT:
            return value
        symbol_to_name = {v: k for k, v in MARKERS_DICT.items()}
        if value in symbol_to_name:
            return symbol_to_name[value]
    return fallback if fallback in MARKERS_DICT else 'Circle'


def _normalize_linestyle_name(value, fallback='Solid'):
    """Normalize line-style representation to one of LINESTYLES_DICT keys."""
    if isinstance(value, str):
        if value in LINESTYLES_DICT:
            return value
        symbol_to_name = {v: k for k, v in LINESTYLES_DICT.items()}
        if value in symbol_to_name:
            return symbol_to_name[value]
    return fallback if fallback in LINESTYLES_DICT else 'Solid'


def _build_plot_spec_from_gui(
    x_col,
    file_y_columns,
    plot_mode,
    x_scale,
    y_scale,
    use_xlim,
    xlim_min,
    xlim_max,
    use_ylim,
    ylim_min,
    ylim_max,
    show_grid,
    show_legend,
    use_custom_size,
    fig_width,
    fig_height,
    plot_title,
    x_label,
    y_label,
):
    """Build a serializable plot spec from current GUI state."""
    curves = {}
    curve_idx = 0
    for file_name, y_cols in file_y_columns.items():
        for y_col in y_cols:
            curve_key = f"{file_name}::{y_col}"
            fallback = _default_curve_style(curve_idx)
            raw = st.session_state.get('curve_styles', {}).get(curve_key, {})
            curves[curve_key] = {
                'enabled': _to_bool(raw.get('enabled', fallback['enabled']), fallback['enabled']),
                'color': _normalize_color_name(raw.get('color', fallback['color']), fallback['color']),
                'marker': _normalize_marker_name(raw.get('marker', fallback['marker']), fallback['marker']),
                'linestyle': _normalize_linestyle_name(raw.get('linestyle', fallback['linestyle']), fallback['linestyle']),
                'linewidth': _to_float(raw.get('linewidth', fallback['linewidth']), fallback['linewidth'], 0.5, 5.0),
                'markersize': _to_float(raw.get('markersize', fallback['markersize']), fallback['markersize'], 1.0, 20.0),
                'alpha': _to_float(raw.get('alpha', fallback['alpha']), fallback['alpha'], 0.1, 1.0),
            }
            curve_idx += 1

    return {
        "version": 1,
        "x_col": str(x_col),
        "file_y_columns": {str(k): [str(v) for v in vals] for k, vals in file_y_columns.items()},
        "plot_mode": plot_mode,
        "x_scale": x_scale,
        "y_scale": y_scale,
        "axis_limits": {
            "use_xlim": bool(use_xlim),
            "xlim_min": float(xlim_min) if use_xlim and xlim_min is not None else None,
            "xlim_max": float(xlim_max) if use_xlim and xlim_max is not None else None,
            "use_ylim": bool(use_ylim),
            "ylim_min": float(ylim_min) if use_ylim and ylim_min is not None else None,
            "ylim_max": float(ylim_max) if use_ylim and ylim_max is not None else None,
        },
        "global_style": {
            "show_grid": bool(show_grid),
            "show_legend": bool(show_legend),
        },
        "figure": {
            "use_custom_size": bool(use_custom_size),
            "width": int(fig_width) if use_custom_size and fig_width is not None else None,
            "height": int(fig_height) if fig_height is not None else 600,
        },
        "labels": {
            "title": str(plot_title),
            "x_label": str(x_label),
            "y_label": str(y_label),
        },
        "curves": curves,
    }


def _generate_python_from_plot_spec(plot_spec):
    """Generate editable Python code from a plot spec."""
    spec_text = pprint.pformat(plot_spec, sort_dicts=False, width=100, compact=False)
    return (
        "# NanoOrganizer plot editor (experimental)\n"
        "# Edit plot_spec below and click 'Run Edited Python'.\n"
        "# The app uses `result` (if defined) otherwise `plot_spec`.\n\n"
        f"plot_spec = {spec_text}\n\n"
        "# Example tweaks:\n"
        "# plot_spec['x_scale'] = 'log'\n"
        "# plot_spec['labels']['title'] = 'Custom Title'\n\n"
        "result = plot_spec\n"
    )


def _sanitize_plot_spec(candidate, fallback_spec, dataframes, all_columns):
    """Sanitize user-edited spec and return (normalized_spec, warnings)."""
    warnings = []
    if not isinstance(candidate, dict):
        warnings.append("Edited code did not return a dict; keeping previous settings.")
        return copy.deepcopy(fallback_spec), warnings

    normalized = copy.deepcopy(fallback_spec)

    # X column
    proposed_x = str(candidate.get("x_col", normalized["x_col"]))
    if proposed_x in all_columns:
        normalized["x_col"] = proposed_x
    elif "x_col" in candidate:
        warnings.append(f"Ignored unknown x_col '{proposed_x}'.")

    # Per-file Y columns
    raw_file_y = candidate.get("file_y_columns", normalized.get("file_y_columns", {}))
    if not isinstance(raw_file_y, dict):
        raw_file_y = normalized.get("file_y_columns", {})
        warnings.append("file_y_columns must be a dict; keeping previous selections.")

    normalized_file_y = {}
    for file_name, df in dataframes.items():
        available_y = [col for col in df.columns if col != normalized["x_col"]]
        fallback_y = normalized.get("file_y_columns", {}).get(file_name, [])
        incoming = raw_file_y.get(file_name, fallback_y)
        if isinstance(incoming, str):
            incoming = [incoming]
        if not isinstance(incoming, (list, tuple, set)):
            incoming = list(fallback_y)

        valid = []
        for y_col in incoming:
            y_col = str(y_col)
            if y_col in available_y and y_col not in valid:
                valid.append(y_col)

        if not valid and available_y:
            for y_col in fallback_y:
                if y_col in available_y and y_col not in valid:
                    valid.append(y_col)
            if not valid:
                valid = [available_y[0]]
        normalized_file_y[file_name] = valid
    normalized["file_y_columns"] = normalized_file_y

    total_curves = sum(len(v) for v in normalized_file_y.values())
    if total_curves == 0:
        warnings.append("No valid curves remained after edits; restoring previous selections.")
        normalized["file_y_columns"] = copy.deepcopy(fallback_spec.get("file_y_columns", {}))

    # Plot mode and scales
    plot_mode = candidate.get("plot_mode", normalized["plot_mode"])
    if plot_mode in PLOT_MODE_OPTIONS:
        normalized["plot_mode"] = plot_mode
    elif "plot_mode" in candidate:
        warnings.append(f"Ignored unsupported plot_mode '{plot_mode}'.")

    x_scale = candidate.get("x_scale", normalized["x_scale"])
    y_scale = candidate.get("y_scale", normalized["y_scale"])
    normalized["x_scale"] = x_scale if x_scale in SCALE_OPTIONS else normalized["x_scale"]
    normalized["y_scale"] = y_scale if y_scale in SCALE_OPTIONS else normalized["y_scale"]

    # Axis limits
    axis_limits = candidate.get("axis_limits", {})
    if not isinstance(axis_limits, dict):
        axis_limits = {}
        warnings.append("axis_limits must be a dict; keeping previous limits.")
    fallback_limits = normalized.get("axis_limits", {})
    use_xlim = _to_bool(axis_limits.get("use_xlim", fallback_limits.get("use_xlim", False)), False)
    use_ylim = _to_bool(axis_limits.get("use_ylim", fallback_limits.get("use_ylim", False)), False)
    xlim_min = _to_float(axis_limits.get("xlim_min", fallback_limits.get("xlim_min", 0.0)), fallback_limits.get("xlim_min", 0.0))
    xlim_max = _to_float(axis_limits.get("xlim_max", fallback_limits.get("xlim_max", 100.0)), fallback_limits.get("xlim_max", 100.0))
    ylim_min = _to_float(axis_limits.get("ylim_min", fallback_limits.get("ylim_min", 0.0)), fallback_limits.get("ylim_min", 0.0))
    ylim_max = _to_float(axis_limits.get("ylim_max", fallback_limits.get("ylim_max", 100.0)), fallback_limits.get("ylim_max", 100.0))
    if use_xlim and xlim_min >= xlim_max:
        warnings.append("X limits invalid (min >= max); keeping previous X limits.")
        xlim_min = fallback_limits.get("xlim_min", 0.0)
        xlim_max = fallback_limits.get("xlim_max", 100.0)
    if use_ylim and ylim_min >= ylim_max:
        warnings.append("Y limits invalid (min >= max); keeping previous Y limits.")
        ylim_min = fallback_limits.get("ylim_min", 0.0)
        ylim_max = fallback_limits.get("ylim_max", 100.0)
    normalized["axis_limits"] = {
        "use_xlim": use_xlim,
        "xlim_min": xlim_min if use_xlim else None,
        "xlim_max": xlim_max if use_xlim else None,
        "use_ylim": use_ylim,
        "ylim_min": ylim_min if use_ylim else None,
        "ylim_max": ylim_max if use_ylim else None,
    }

    # Global style
    global_style = candidate.get("global_style", {})
    if not isinstance(global_style, dict):
        global_style = {}
        warnings.append("global_style must be a dict; keeping previous style.")
    fallback_style = normalized.get("global_style", {})
    normalized["global_style"] = {
        "show_grid": _to_bool(global_style.get("show_grid", fallback_style.get("show_grid", True)), True),
        "show_legend": _to_bool(global_style.get("show_legend", fallback_style.get("show_legend", True)), True),
    }

    # Figure
    figure = candidate.get("figure", {})
    if not isinstance(figure, dict):
        figure = {}
        warnings.append("figure must be a dict; keeping previous figure settings.")
    fallback_figure = normalized.get("figure", {})
    use_custom_size = _to_bool(figure.get("use_custom_size", fallback_figure.get("use_custom_size", False)), False)
    fig_width = _to_int(figure.get("width", fallback_figure.get("width", 1000)), 1000, 300, 3000)
    fig_height = _to_int(figure.get("height", fallback_figure.get("height", 600)), 600, 200, 2000)
    normalized["figure"] = {
        "use_custom_size": use_custom_size,
        "width": fig_width if use_custom_size else None,
        "height": fig_height,
    }

    # Labels
    labels = candidate.get("labels", {})
    if not isinstance(labels, dict):
        labels = {}
        warnings.append("labels must be a dict; keeping previous labels.")
    fallback_labels = normalized.get("labels", {})
    normalized["labels"] = {
        "title": str(labels.get("title", fallback_labels.get("title", "Data Comparison"))),
        "x_label": str(labels.get("x_label", fallback_labels.get("x_label", normalized["x_col"]))),
        "y_label": str(labels.get("y_label", fallback_labels.get("y_label", "Intensity"))),
    }

    # Curves
    raw_curves = candidate.get("curves", {})
    if not isinstance(raw_curves, dict):
        raw_curves = {}
        warnings.append("curves must be a dict; keeping previous curve styles.")
    fallback_curves = normalized.get("curves", {})
    normalized_curves = {}
    curve_idx = 0
    for file_name, y_cols in normalized["file_y_columns"].items():
        for y_col in y_cols:
            curve_key = f"{file_name}::{y_col}"
            fallback_style = fallback_curves.get(curve_key, _default_curve_style(curve_idx))
            incoming = raw_curves.get(curve_key, fallback_style)
            if not isinstance(incoming, dict):
                incoming = fallback_style

            normalized_curves[curve_key] = {
                "enabled": _to_bool(incoming.get("enabled", fallback_style.get("enabled", True)), True),
                "color": _normalize_color_name(incoming.get("color", fallback_style.get("color", "Blue")),
                                               fallback_style.get("color", "Blue")),
                "marker": _normalize_marker_name(incoming.get("marker", fallback_style.get("marker", "Circle")),
                                                 fallback_style.get("marker", "Circle")),
                "linestyle": _normalize_linestyle_name(incoming.get("linestyle", fallback_style.get("linestyle", "Solid")),
                                                       fallback_style.get("linestyle", "Solid")),
                "linewidth": _to_float(incoming.get("linewidth", fallback_style.get("linewidth", 2.0)),
                                       fallback_style.get("linewidth", 2.0), 0.5, 5.0),
                "markersize": _to_float(incoming.get("markersize", fallback_style.get("markersize", 8.0)),
                                        fallback_style.get("markersize", 8.0), 1.0, 20.0),
                "alpha": _to_float(incoming.get("alpha", fallback_style.get("alpha", 0.8)),
                                   fallback_style.get("alpha", 0.8), 0.1, 1.0),
            }
            curve_idx += 1
    normalized["curves"] = normalized_curves

    return normalized, warnings


def _apply_plot_spec_to_session_state(plot_spec, dataframes):
    """Apply normalized plot spec into session state before widgets render."""
    st.session_state["csv_x_col"] = plot_spec.get("x_col")

    st.session_state["csv_plot_mode"] = plot_spec.get("plot_mode", PLOT_MODE_OPTIONS[0])
    st.session_state["csv_x_scale"] = plot_spec.get("x_scale", "linear")
    st.session_state["csv_y_scale"] = plot_spec.get("y_scale", "linear")

    axis_limits = plot_spec.get("axis_limits", {})
    st.session_state["csv_use_xlim"] = _to_bool(axis_limits.get("use_xlim", False), False)
    st.session_state["csv_xlim_min"] = _to_float(axis_limits.get("xlim_min", 0.0), 0.0)
    st.session_state["csv_xlim_max"] = _to_float(axis_limits.get("xlim_max", 100.0), 100.0)
    st.session_state["csv_use_ylim"] = _to_bool(axis_limits.get("use_ylim", False), False)
    st.session_state["csv_ylim_min"] = _to_float(axis_limits.get("ylim_min", 0.0), 0.0)
    st.session_state["csv_ylim_max"] = _to_float(axis_limits.get("ylim_max", 100.0), 100.0)

    global_style = plot_spec.get("global_style", {})
    st.session_state["csv_show_grid"] = _to_bool(global_style.get("show_grid", True), True)
    st.session_state["csv_show_legend"] = _to_bool(global_style.get("show_legend", True), True)

    figure = plot_spec.get("figure", {})
    st.session_state["csv_use_custom_size"] = _to_bool(figure.get("use_custom_size", False), False)
    st.session_state["csv_fig_width"] = _to_int(figure.get("width", 1000), 1000, 300, 3000)
    st.session_state["csv_fig_height"] = _to_int(figure.get("height", 600), 600, 200, 2000)

    labels = plot_spec.get("labels", {})
    st.session_state["csv_plot_title"] = str(labels.get("title", "Data Comparison"))
    st.session_state["csv_x_label"] = str(labels.get("x_label", plot_spec.get("x_col", "X")))
    st.session_state["csv_y_label"] = str(labels.get("y_label", "Intensity"))
    st.session_state["csv_last_x_col_for_label"] = plot_spec.get("x_col")

    if 'y_column_selections' not in st.session_state:
        st.session_state['y_column_selections'] = {}

    file_y_columns = plot_spec.get("file_y_columns", {})
    for file_name in dataframes.keys():
        y_cols = [str(y) for y in file_y_columns.get(file_name, [])]
        st.session_state['y_column_selections'][file_name] = y_cols
        st.session_state[f"y_cols_{file_name}"] = y_cols

    if 'curve_styles' not in st.session_state:
        st.session_state['curve_styles'] = {}

    curve_styles = st.session_state['curve_styles']
    active_curve_keys = set()
    for curve_key, style in plot_spec.get("curves", {}).items():
        active_curve_keys.add(curve_key)
        normalized_style = {
            "enabled": _to_bool(style.get("enabled", True), True),
            "color": _normalize_color_name(style.get("color", "Blue"), "Blue"),
            "marker": _normalize_marker_name(style.get("marker", "Circle"), "Circle"),
            "linestyle": _normalize_linestyle_name(style.get("linestyle", "Solid"), "Solid"),
            "linewidth": _to_float(style.get("linewidth", 2.0), 2.0, 0.5, 5.0),
            "markersize": _to_float(style.get("markersize", 8.0), 8.0, 1.0, 20.0),
            "alpha": _to_float(style.get("alpha", 0.8), 0.8, 0.1, 1.0),
        }
        curve_styles[curve_key] = normalized_style

        # Seed widget-state keys so UI reflects script edits.
        st.session_state[f"enabled_{curve_key}"] = normalized_style["enabled"]
        st.session_state[f"color_{curve_key}"] = normalized_style["color"]
        st.session_state[f"marker_{curve_key}"] = normalized_style["marker"]
        st.session_state[f"linestyle_{curve_key}"] = normalized_style["linestyle"]
        st.session_state[f"linewidth_{curve_key}"] = normalized_style["linewidth"]
        st.session_state[f"markersize_{curve_key}"] = normalized_style["markersize"]
        st.session_state[f"alpha_{curve_key}"] = normalized_style["alpha"]

    for stale_curve in list(curve_styles.keys()):
        if "::" in stale_curve and stale_curve not in active_curve_keys:
            curve_styles.pop(stale_curve, None)


def _execute_editor_code(code_text, base_plot_spec, dataframes, all_columns):
    """Execute editor code and return sanitized plot spec and warnings."""
    execution_locals = {
        "plot_spec": copy.deepcopy(base_plot_spec),
        "result": None,
        "data_files": list(dataframes.keys()),
        "columns_by_file": {k: list(v.columns) for k, v in dataframes.items()},
        "all_columns": list(all_columns),
        "np": np,
        "pd": pd,
        "copy": copy,
    }
    exec(code_text, {"__builtins__": __builtins__}, execution_locals)

    candidate = execution_locals.get("result")
    if candidate is None:
        candidate = execution_locals.get("plot_spec")

    return _sanitize_plot_spec(candidate, base_plot_spec, dataframes, all_columns)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def shorten_path(path_str, max_length=40):
    """Shorten long file paths for display."""
    if len(path_str) <= max_length:
        return path_str

    path = Path(path_str)
    filename = path.name

    if len(filename) > max_length - 3:
        return "..." + filename[-(max_length-3):]

    # Show ... parent .../filename
    parent = str(path.parent)
    if len(parent) + len(filename) + 4 > max_length:
        return ".../" + filename
    else:
        remaining = max_length - len(filename) - 4
        return parent[:remaining] + ".../" + filename


def load_data_file(file_path):
    """Load CSV, TXT, DAT, or NPZ file."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    try:
        if suffix == '.npz':
            data = np.load(file_path)
            # Convert to dataframe (assumes 1D or 2D arrays)
            df_dict = {}
            for key in data.files:
                arr = data[key]
                if arr.ndim == 1:
                    df_dict[key] = arr
                elif arr.ndim == 2:
                    # Flatten or take first column
                    df_dict[key] = arr.flatten()
            return pd.DataFrame(df_dict)
        else:
            # Try CSV/TXT with different delimiters
            df = pd.read_csv(file_path, sep=',')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep='\t')
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, sep=r'\s+')
            return df
    except Exception as e:
        st.error(f"Error loading {path.name}: {e}")
        return None


def _save_fig_to_bytes(fig, format='png', dpi=300):
    """Save matplotlib figure to bytes buffer for download."""
    buf = io.BytesIO()
    fig.savefig(buf, format=format, dpi=dpi, bbox_inches='tight')
    buf.seek(0)
    return buf


def browse_directory(base_dir, pattern="*.*"):
    """Browse directory and find files matching pattern."""
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    files = list(base_path.rglob(pattern))
    return [str(f) for f in sorted(files)]


def _safe_widget_key(prefix, name):
    """Create compact deterministic keys for Streamlit widgets."""
    return f"{prefix}_{abs(hash(str(name)))}"


# ---------------------------------------------------------------------------
# Initialize session state
# ---------------------------------------------------------------------------

if 'curve_styles' not in st.session_state:
    st.session_state['curve_styles'] = {}

if 'dataframes_csv' not in st.session_state:
    st.session_state['dataframes_csv'] = {}

if 'file_paths_csv' not in st.session_state:
    st.session_state['file_paths_csv'] = {}

if 'y_column_selections' not in st.session_state:
    st.session_state['y_column_selections'] = {}

st.session_state.setdefault("csv_plot_mode", PLOT_MODE_OPTIONS[0])
st.session_state.setdefault("csv_x_scale", "linear")
st.session_state.setdefault("csv_y_scale", "linear")
st.session_state.setdefault("csv_use_xlim", False)
st.session_state.setdefault("csv_xlim_min", 0.0)
st.session_state.setdefault("csv_xlim_max", 100.0)
st.session_state.setdefault("csv_use_ylim", False)
st.session_state.setdefault("csv_ylim_min", 0.0)
st.session_state.setdefault("csv_ylim_max", 100.0)
st.session_state.setdefault("csv_show_grid", True)
st.session_state.setdefault("csv_show_legend", True)
st.session_state.setdefault("csv_use_custom_size", False)
st.session_state.setdefault("csv_fig_width", 1000)
st.session_state.setdefault("csv_fig_height", 600)
st.session_state.setdefault("csv_plot_title", "Data Comparison")
st.session_state.setdefault("csv_x_label", "X")
st.session_state.setdefault("csv_y_label", "Intensity")
st.session_state.setdefault("csv_last_x_col_for_label", None)
st.session_state.setdefault("csv_editor_code", "")
st.session_state.setdefault("csv_editor_status", "")
st.session_state.setdefault("csv_editor_warnings", [])

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.title("📊 Enhanced CSV/NPZ Plotter")
st.markdown("Quick visualization with per-curve styling - supports CSV, TXT, DAT, NPZ")

# Floating sidebar toggle button (bottom-left)
floating_sidebar_toggle()

# ---------------------------------------------------------------------------
# Sidebar: Data Source
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 Data Source")

    data_source = st.radio(
        "Data location",
        ["Upload files", "Browse server"],
        help="Upload files from your computer or browse server filesystem"
    )

    if data_source == "Upload files":
        uploaded_files = st.file_uploader(
            "Upload data files",
            type=['csv', 'txt', 'dat', 'npz'],
            accept_multiple_files=True,
            help="Upload CSV, TXT, DAT, or NPZ files"
        )

        if uploaded_files:
            for uploaded_file in uploaded_files:
                try:
                    # Save temporarily to load
                    temp_path = Path(f"/tmp/{uploaded_file.name}")
                    with open(temp_path, 'wb') as f:
                        f.write(uploaded_file.getbuffer())

                    df = load_data_file(str(temp_path))
                    if df is not None:
                        st.session_state['dataframes_csv'][uploaded_file.name] = df
                        st.session_state['file_paths_csv'][uploaded_file.name] = uploaded_file.name
                except Exception as e:
                    st.error(f"Error loading {uploaded_file.name}: {e}")

    else:  # Browse server
        st.markdown("**🗂️ Interactive Folder Browser**")
        st.markdown("Click folders to navigate, select files with checkboxes:")

        # File pattern selector
        st.markdown("**📋 File Type Filter:**")
        pattern = st.selectbox(
            "Extension pattern",
            ["*.*", "*.csv", "*.npz", "*.txt", "*.dat"],
            help="Filter files by extension",
            label_visibility="collapsed"
        )

        st.info("💡 Tip: Use '🔍 Advanced Filters' below for name-based filtering (contains, not contains, etc.)")

        # Use folder browser component
        selected_files = folder_browser(
            key="csv_plotter_browser",
            show_files=True,
            file_pattern=pattern,
            multi_select=True,
            initial_path=_start_dir if _user_mode else None,
            restrict_to_start_dir=_user_mode,
        )

        # Load button
        if selected_files and st.button("📥 Load Selected Files", key="csv_load_btn"):
            for full_path in selected_files:
                df = load_data_file(full_path)
                if df is not None:
                    file_name = Path(full_path).name
                    st.session_state['dataframes_csv'][file_name] = df
                    st.session_state['file_paths_csv'][file_name] = full_path
                    st.success(f"✅ Loaded {file_name}")

    # Get dataframes from session state
    dataframes = st.session_state['dataframes_csv']
    file_paths = st.session_state['file_paths_csv']

    # Clear button
    if dataframes:
        if st.button("🗑️ Clear All Data", key="clear_csv_data"):
            st.session_state['dataframes_csv'] = {}
            st.session_state['file_paths_csv'] = {}
            st.session_state['curve_styles'] = {}
            st.session_state['y_column_selections'] = {}
            st.session_state.pop("csv_pending_plot_spec", None)
            st.rerun()

    if not dataframes:
        st.info("👆 Upload or select files to get started")
        st.stop()

    st.success(f"✅ Loaded {len(dataframes)} file(s)")

    # ---------------------------------------------------------------------------
    # Column Selection
    # ---------------------------------------------------------------------------

    st.header("📐 Column Selection")

    # Get all unique column names
    all_columns = set()
    for df in dataframes.values():
        all_columns.update(df.columns)
    all_columns = sorted(list(all_columns))

    if not all_columns:
        st.error("No columns found")
        st.stop()

    if "csv_pending_plot_spec" in st.session_state:
        pending_spec = st.session_state.pop("csv_pending_plot_spec")
        _apply_plot_spec_to_session_state(pending_spec, dataframes)

    # Auto-detect likely X column
    x_default = None
    for col in all_columns:
        col_lower = col.lower()
        if x_default is None and any(kw in col_lower for kw in
                                     ['wavelength', 'q', 'theta', 'energy', 'time', 'x']):
            x_default = col

    if x_default is None and len(all_columns) > 0:
        x_default = all_columns[0]

    if st.session_state.get("csv_x_col") not in all_columns:
        st.session_state["csv_x_col"] = x_default

    x_col = st.selectbox(
        "X-axis column (common for all files)",
        all_columns,
        key="csv_x_col",
        help="Select X-axis column - will be used for all files"
    )

    # Per-file Y column selection
    st.markdown("**Y-axis columns (per file):**")
    st.info("💡 Select multiple Y columns from each file to plot them as separate curves")

    file_y_columns = {}  # {file_name: [y_col1, y_col2, ...]}

    for file_name, df in dataframes.items():
        available_y_cols = [col for col in df.columns if col != x_col]

        if not available_y_cols:
            st.warning(f"⚠️ {file_name}: No Y columns available (only X column found)")
            continue

        # Auto-detect Y columns for first time
        if file_name not in st.session_state['y_column_selections']:
            # Default: select columns with keywords
            default_y = []
            for col in available_y_cols:
                col_lower = col.lower()
                if any(kw in col_lower for kw in ['intensity', 'absorbance', 'absorption', 'y', 'signal']):
                    default_y.append(col)

            # If no keywords match, select first available column
            if not default_y and available_y_cols:
                default_y = [available_y_cols[0]]

            st.session_state['y_column_selections'][file_name] = default_y
        else:
            selected_existing = [
                col for col in st.session_state['y_column_selections'][file_name]
                if col in available_y_cols
            ]
            if not selected_existing and available_y_cols:
                selected_existing = [available_y_cols[0]]
            st.session_state['y_column_selections'][file_name] = selected_existing

        selected_y_cols = st.multiselect(
            f"📄 {shorten_path(file_name, 40)}",
            available_y_cols,
            default=st.session_state['y_column_selections'][file_name],
            key=f"y_cols_{file_name}",
            help=f"Select one or more Y columns from {file_name}"
        )

        st.session_state['y_column_selections'][file_name] = selected_y_cols
        file_y_columns[file_name] = selected_y_cols

    # Check if any Y columns selected
    total_curves = sum(len(cols) for cols in file_y_columns.values())
    if total_curves == 0:
        st.error("No Y columns selected. Please select at least one Y column from any file.")
        st.stop()

    st.success(f"✅ Total curves to plot: {total_curves}")

    # ---------------------------------------------------------------------------
    # Global Plot Controls
    # ---------------------------------------------------------------------------

    st.header("⚙️ Global Controls")

    # Plot mode
    if st.session_state.get("csv_plot_mode") not in PLOT_MODE_OPTIONS:
        st.session_state["csv_plot_mode"] = PLOT_MODE_OPTIONS[0]
    plot_mode = st.radio(
        "Plot mode",
        PLOT_MODE_OPTIONS,
        horizontal=True,
        key="csv_plot_mode",
        help="Plotly shows values on hover! Matplotlib is static but publication-ready."
    )
    use_plotly = plot_mode.startswith("Interactive")

    # Scale
    if st.session_state.get("csv_x_scale") not in SCALE_OPTIONS:
        st.session_state["csv_x_scale"] = "linear"
    if st.session_state.get("csv_y_scale") not in SCALE_OPTIONS:
        st.session_state["csv_y_scale"] = "linear"
    col1, col2 = st.columns(2)
    with col1:
        x_scale = st.radio("X Scale", SCALE_OPTIONS, horizontal=True, key="csv_x_scale")
    with col2:
        y_scale = st.radio("Y Scale", SCALE_OPTIONS, horizontal=True, key="csv_y_scale")

    # Axis limits
    with st.expander("📏 Axis Limits", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**X-axis limits:**")
            use_xlim = st.checkbox("Set X limits", key="csv_use_xlim")
            if use_xlim:
                xlim_min = st.number_input("X min", format="%.4f", key="csv_xlim_min")
                xlim_max = st.number_input("X max", format="%.4f", key="csv_xlim_max")
            else:
                xlim_min, xlim_max = None, None

        with col2:
            st.markdown("**Y-axis limits:**")
            use_ylim = st.checkbox("Set Y limits", key="csv_use_ylim")
            if use_ylim:
                ylim_min = st.number_input("Y min", format="%.4f", key="csv_ylim_min")
                ylim_max = st.number_input("Y max", format="%.4f", key="csv_ylim_max")
            else:
                ylim_min, ylim_max = None, None

    # Global style
    with st.expander("🎨 Global Style", expanded=False):
        show_grid = st.checkbox("Show grid", key="csv_show_grid")
        show_legend = st.checkbox("Show legend", key="csv_show_legend")

    # Figure size
    with st.expander("📐 Figure Size", expanded=False):
        use_custom_size = st.checkbox("Custom figure size", key="csv_use_custom_size",
                                       help="Default: auto width, 600px height")
        if use_custom_size:
            sc1, sc2 = st.columns(2)
            with sc1:
                fig_width = st.number_input("Width (px)", min_value=300, max_value=3000,
                                            step=50, key="csv_fig_width")
            with sc2:
                fig_height = st.number_input("Height (px)", min_value=200, max_value=2000,
                                             step=50, key="csv_fig_height")
        else:
            fig_width = None
            fig_height = st.session_state.get("csv_fig_height", 600)

    # Labels
    if st.session_state.get("csv_last_x_col_for_label") is None:
        st.session_state["csv_last_x_col_for_label"] = x_col
        if st.session_state.get("csv_x_label") in {"", "X"}:
            st.session_state["csv_x_label"] = x_col
    elif (
        st.session_state.get("csv_x_label") == st.session_state.get("csv_last_x_col_for_label")
        and st.session_state.get("csv_last_x_col_for_label") != x_col
    ):
        st.session_state["csv_x_label"] = x_col
    st.session_state["csv_last_x_col_for_label"] = x_col

    with st.expander("📝 Labels", expanded=False):
        plot_title = st.text_input("Plot title", key="csv_plot_title")
        x_label = st.text_input("X-axis label", key="csv_x_label")
        y_label = st.text_input("Y-axis label", key="csv_y_label")

# ---------------------------------------------------------------------------
# Main Area: Per-Curve Styling
# ---------------------------------------------------------------------------

st.header("🎨 Per-Curve Styling")

# Create expanders for each curve (file_name, y_col combination)
curve_settings = {}
curve_idx = 0

for file_name, y_cols in file_y_columns.items():
    for y_col in y_cols:
        curve_key = f"{file_name}::{y_col}"  # Unique key for each curve
        curve_label = f"{shorten_path(file_name, 30)} : {y_col}"

        with st.expander(f"🔧 {curve_label}", expanded=False):
            # Initialize defaults if not in session state
            if curve_key not in st.session_state['curve_styles']:
                st.session_state['curve_styles'][curve_key] = _default_curve_style(curve_idx)

            # Normalize style values before reading as widget defaults.
            default_style = _default_curve_style(curve_idx)
            curve_style = st.session_state['curve_styles'][curve_key]
            curve_style['enabled'] = _to_bool(curve_style.get('enabled', default_style['enabled']), default_style['enabled'])
            curve_style['color'] = _normalize_color_name(curve_style.get('color', default_style['color']), default_style['color'])
            curve_style['marker'] = _normalize_marker_name(curve_style.get('marker', default_style['marker']), default_style['marker'])
            curve_style['linestyle'] = _normalize_linestyle_name(curve_style.get('linestyle', default_style['linestyle']), default_style['linestyle'])
            curve_style['linewidth'] = _to_float(curve_style.get('linewidth', default_style['linewidth']),
                                                 default_style['linewidth'], 0.5, 5.0)
            curve_style['markersize'] = _to_float(curve_style.get('markersize', default_style['markersize']),
                                                  default_style['markersize'], 1.0, 20.0)
            curve_style['alpha'] = _to_float(curve_style.get('alpha', default_style['alpha']),
                                             default_style['alpha'], 0.1, 1.0)
            st.session_state['curve_styles'][curve_key] = curve_style

            # Initialize curve_settings entry
            if curve_key not in curve_settings:
                curve_settings[curve_key] = {}

            # Enable/Disable checkbox
            enabled = st.checkbox(
                f"✅ Show this curve",
                value=curve_style.get('enabled', True),
                key=f"enabled_{curve_key}",
                help="Toggle to show/hide this curve in the plot"
            )
            st.session_state['curve_styles'][curve_key]['enabled'] = enabled
            curve_settings[curve_key]['enabled'] = enabled

            if not enabled:
                st.info("⚠️ This curve is hidden. Enable to show in plot.")
                curve_idx += 1
                continue

            st.divider()
            col1, col2, col3, col4, col5, col6 = st.columns(6)

            with col1:
                color_name = st.selectbox(
                    "Color",
                    list(COLORS_NAMED.keys()),
                    index=list(COLORS_NAMED.keys()).index(curve_style['color']),
                    key=f"color_{curve_key}"
                )
                curve_settings[curve_key]['color'] = COLORS_NAMED[color_name]

            with col2:
                marker_name = st.selectbox(
                    "Marker",
                    list(MARKERS_DICT.keys()),
                    index=list(MARKERS_DICT.keys()).index(curve_style['marker']),
                    key=f"marker_{curve_key}"
                )
                curve_settings[curve_key]['marker'] = MARKERS_DICT[marker_name]

            with col3:
                linestyle_name = st.selectbox(
                    "Line Style",
                    list(LINESTYLES_DICT.keys()),
                    index=list(LINESTYLES_DICT.keys()).index(curve_style['linestyle']),
                    key=f"linestyle_{curve_key}"
                )
                curve_settings[curve_key]['linestyle'] = LINESTYLES_DICT[linestyle_name]

            with col4:
                linewidth = st.slider(
                    "Line Width",
                    0.5, 5.0,
                    curve_style['linewidth'],
                    0.5,
                    key=f"linewidth_{curve_key}"
                )
                curve_settings[curve_key]['linewidth'] = linewidth

            with col5:
                markersize = st.slider(
                    "Marker Size",
                    1.0, 20.0,
                    curve_style.get('markersize', 8.0),
                    1.0,
                    key=f"markersize_{curve_key}"
                )
                curve_settings[curve_key]['markersize'] = markersize

            with col6:
                alpha = st.slider(
                    "Opacity",
                    0.1, 1.0,
                    curve_style['alpha'],
                    0.1,
                    key=f"alpha_{curve_key}"
                )
                curve_settings[curve_key]['alpha'] = alpha

            # Update session state
            st.session_state['curve_styles'][curve_key].update({
                'color': color_name,
                'marker': marker_name,
                'linestyle': linestyle_name,
                'linewidth': linewidth,
                'markersize': markersize,
                'alpha': alpha
            })

        curve_idx += 1

# ---------------------------------------------------------------------------
# Python Editor (Two-way GUI <-> Code)
# ---------------------------------------------------------------------------

current_plot_spec = _build_plot_spec_from_gui(
    x_col=x_col,
    file_y_columns=file_y_columns,
    plot_mode=plot_mode,
    x_scale=x_scale,
    y_scale=y_scale,
    use_xlim=use_xlim,
    xlim_min=xlim_min,
    xlim_max=xlim_max,
    use_ylim=use_ylim,
    ylim_min=ylim_min,
    ylim_max=ylim_max,
    show_grid=show_grid,
    show_legend=show_legend,
    use_custom_size=use_custom_size,
    fig_width=fig_width,
    fig_height=fig_height,
    plot_title=plot_title,
    x_label=x_label,
    y_label=y_label,
)
st.session_state["csv_current_plot_spec"] = current_plot_spec

if not st.session_state.get("csv_editor_code"):
    st.session_state["csv_editor_code"] = _generate_python_from_plot_spec(current_plot_spec)

st.divider()
st.header("🧠 Python Plot Editor (Experimental)")
st.caption("Two-way control: GUI -> Python script -> GUI.")
st.caption("Code runs in the app process. Only run trusted code.")

pending_editor_code = st.session_state.pop("csv_editor_code_pending", None)
if pending_editor_code is not None:
    st.session_state["csv_editor_code"] = pending_editor_code

editor_code = st.text_area(
    "Editable Python script",
    key="csv_editor_code",
    height=320,
    help="Edit plot_spec and click 'Run Edited Python' to update GUI and plot settings."
)

ed_col1, ed_col2 = st.columns(2)
with ed_col1:
    if st.button("🧾 Show Python from Current GUI", key="csv_editor_generate"):
        st.session_state["csv_editor_code_pending"] = _generate_python_from_plot_spec(current_plot_spec)
        st.session_state["csv_editor_status"] = "Editor refreshed from current GUI state."
        st.session_state["csv_editor_warnings"] = []
        st.rerun()

with ed_col2:
    if st.button("▶️ Run Edited Python", key="csv_editor_run", type="primary"):
        try:
            normalized_spec, warnings = _execute_editor_code(
                editor_code,
                current_plot_spec,
                dataframes,
                all_columns,
            )
            st.session_state["csv_pending_plot_spec"] = normalized_spec
            st.session_state["csv_editor_status"] = "Script applied. GUI synced from edited plot_spec."
            st.session_state["csv_editor_warnings"] = warnings
            st.rerun()
        except Exception as exc:
            st.session_state["csv_editor_status"] = f"Script execution failed: {exc}"
            st.session_state["csv_editor_warnings"] = []

if st.session_state.get("csv_editor_status"):
    status_text = st.session_state["csv_editor_status"]
    if status_text.lower().startswith("script execution failed"):
        st.error(status_text)
    else:
        st.success(status_text)
for warning_msg in st.session_state.get("csv_editor_warnings", []):
    st.warning(warning_msg)

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

st.divider()
st.header(f"📈 Plot: Y columns vs {x_col}")

# Debug: Show what will be plotted
with st.expander("🔍 Debug: Curves to Plot", expanded=False):
    for fname, ycols in file_y_columns.items():
        st.write(f"**{fname}**: {len(ycols)} columns → {', '.join(ycols)}")

if use_plotly:
    # -------------------------------------------------------------------------
    # Plotly Interactive Plot (with hover!)
    # -------------------------------------------------------------------------
    fig = go.Figure()

    plotted_count = 0
    skipped_count = 0
    for file_name, y_cols in file_y_columns.items():
        df = dataframes[file_name]

        for y_col in y_cols:
            curve_key = f"{file_name}::{y_col}"

            # Check if enabled
            if not curve_settings.get(curve_key, {}).get('enabled', True):
                skipped_count += 1
                continue

            # Check if columns exist
            if x_col not in df.columns or y_col not in df.columns:
                st.warning(f"⚠️ {file_name}, {y_col}: missing columns")
                continue

            # Get data
            x_data = df[x_col].values
            y_data = df[y_col].values

            # Remove NaN
            mask = ~(np.isnan(x_data) | np.isnan(y_data))
            x_data = x_data[mask]
            y_data = y_data[mask]

            if len(x_data) == 0:
                st.warning(f"⚠️ {file_name}, {y_col}: no valid data")
                continue

                # Get styling
            style = curve_settings.get(curve_key, {})

            # Map matplotlib markers to plotly symbols
            marker_map = {
                'o': 'circle', 's': 'square', '^': 'triangle-up', 'v': 'triangle-down',
                'D': 'diamond', 'p': 'pentagon', '*': 'star', 'h': 'hexagon',
                '+': 'cross', 'x': 'x', '.': 'circle', 'None': None
            }

            # Map matplotlib linestyles to plotly dash
            linestyle_map = {
                '-': 'solid', '--': 'dash', '-.': 'dashdot', ':': 'dot', 'None': None
            }

            marker_style = marker_map.get(style.get('marker', 'o'), 'circle')
            line_dash = linestyle_map.get(style.get('linestyle', '-'), 'solid')

            # Determine mode
            if marker_style and line_dash:
                mode = 'lines+markers'
            elif marker_style:
                mode = 'markers'
            elif line_dash:
                mode = 'lines'
            else:
                mode = 'lines'

            # Add trace
            trace_name = f"{shorten_path(file_name, 20)}: {y_col}"
            fig.add_trace(go.Scatter(
                x=x_data,
                y=y_data,
                mode=mode,
                name=trace_name,
                line=dict(
                    color=style.get('color', '#1f77b4'),
                    width=style.get('linewidth', 2.0),
                    dash=line_dash if line_dash else 'solid'
                ),
                marker=dict(
                    symbol=marker_style if marker_style else 'circle',
                    size=style.get('markersize', 8.0),
                    color=style.get('color', '#1f77b4')
                ),
                opacity=style.get('alpha', 0.8),
                hovertemplate=f'<b>{x_col}</b>: %{{x:.4f}}<br><b>{y_col}</b>: %{{y:.4f}}<extra></extra>'
            ))

            plotted_count += 1

    if plotted_count == 0:
        st.error("No curves enabled. Enable curves in Per-Curve Styling section.")
        st.stop()

    # Apply settings
    fig.update_xaxes(
        title=x_label,
        type='log' if x_scale == 'log' else 'linear',
        range=[np.log10(xlim_min) if x_scale == 'log' and use_xlim and xlim_min > 0 else xlim_min,
               np.log10(xlim_max) if x_scale == 'log' and use_xlim else xlim_max] if use_xlim else None,
        showgrid=show_grid,
        gridcolor='lightgray',
        gridwidth=0.5
    )

    fig.update_yaxes(
        title=y_label,
        type='log' if y_scale == 'log' else 'linear',
        range=[np.log10(ylim_min) if y_scale == 'log' and use_ylim and ylim_min > 0 else ylim_min,
               np.log10(ylim_max) if y_scale == 'log' and use_ylim else ylim_max] if use_ylim else None,
        showgrid=show_grid,
        gridcolor='lightgray',
        gridwidth=0.5
    )

    layout_kwargs = dict(
        title=plot_title,
        height=fig_height,
        hovermode='closest',
        showlegend=show_legend,
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02)
    )
    if fig_width is not None:
        layout_kwargs['width'] = fig_width
    fig.update_layout(**layout_kwargs)

    # Show plot
    st.plotly_chart(fig, use_container_width=(fig_width is None))
    if skipped_count > 0:
        st.success(f"✅ {plotted_count} curve(s) plotted. **Hover over curves to see (x,y) values!** ({skipped_count} disabled)")
    else:
        st.success(f"✅ {plotted_count} curve(s) plotted. **Hover over curves to see (x,y) values!**")

else:
    # -------------------------------------------------------------------------
    # Matplotlib Static Plot
    # -------------------------------------------------------------------------
    if fig_width is not None:
        fig, ax = plt.subplots(figsize=(fig_width / 100, fig_height / 100))
    else:
        fig, ax = plt.subplots(figsize=(12, fig_height / 100))

    plotted_count = 0
    skipped_count = 0
    for file_name, y_cols in file_y_columns.items():
        df = dataframes[file_name]

        for y_col in y_cols:
            curve_key = f"{file_name}::{y_col}"

            # Check if enabled
            if not curve_settings.get(curve_key, {}).get('enabled', True):
                skipped_count += 1
                continue

            # Check if columns exist
            if x_col not in df.columns or y_col not in df.columns:
                st.warning(f"⚠️ {file_name}, {y_col}: missing columns")
                continue

            # Get data
            x_data = df[x_col].values
            y_data = df[y_col].values

            # Remove NaN
            mask = ~(np.isnan(x_data) | np.isnan(y_data))
            x_data = x_data[mask]
            y_data = y_data[mask]

            if len(x_data) == 0:
                st.warning(f"⚠️ {file_name}, {y_col}: no valid data")
                continue

            # Get styling
            style = curve_settings.get(curve_key, {})

            # Plot
            marker = style.get('marker', 'None')
            marker = None if marker == 'None' else marker

            linestyle = style.get('linestyle', '-')
            linestyle = '' if linestyle == 'None' else linestyle

            trace_label = f"{shorten_path(file_name, 20)}: {y_col}"

            ax.plot(
                x_data, y_data,
                color=style.get('color', '#1f77b4'),
                marker=marker,
                linestyle=linestyle,
                linewidth=style.get('linewidth', 2.0),
                alpha=style.get('alpha', 0.8),
                label=trace_label,
                markersize=style.get('markersize', 8.0),
                markevery=max(1, len(x_data)//20) if marker else None
            )

            plotted_count += 1

    if plotted_count == 0:
        st.error("No curves enabled. Enable curves in Per-Curve Styling section.")
        st.stop()

    # Apply settings
    ax.set_xscale(x_scale)
    ax.set_yscale(y_scale)
    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel(y_label, fontsize=12)
    ax.set_title(plot_title, fontsize=14, fontweight='bold')

    # Set axis limits
    if use_xlim:
        ax.set_xlim(xlim_min, xlim_max)
    if use_ylim:
        ax.set_ylim(ylim_min, ylim_max)

    if show_grid:
        ax.grid(True, alpha=0.3, linestyle='--')

    if show_legend and len(dataframes) > 1:
        ax.legend(loc='best', framealpha=0.9, fontsize=9)

    # Show plot
    st.pyplot(fig)
    if skipped_count > 0:
        st.info(f"✅ {plotted_count} curve(s) plotted. Switch to 'Interactive (Plotly)' mode to see hover values! ({skipped_count} disabled)")
    else:
        st.info(f"✅ {plotted_count} curve(s) plotted. Switch to 'Interactive (Plotly)' mode to see hover values!")

# Fitting note for base branch
st.divider()
st.header("🔬 Fitting")
st.info(
    "Advanced fitting workbench is part of the private `viz-adv` track. "
    "This `viz-base` branch keeps visualization and data-management tools only."
)

# Export
st.divider()

if use_plotly:
    # Plotly export
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        html_buffer = io.StringIO()
        fig.write_html(html_buffer)
        html_bytes = html_buffer.getvalue().encode()
        st.download_button(
            label="💾 Download HTML",
            data=html_bytes,
            file_name=f"plot_{x_col}_vs_{y_col}.html",
            mime="text/html",
            help="Interactive plot - preserves hover functionality!"
        )

    with col2:
        try:
            img_bytes = fig.to_image(format="png", width=1200, height=800)
            st.download_button(
                label="💾 Download PNG",
                data=img_bytes,
                file_name=f"plot_{x_col}_vs_{y_col}.png",
                mime="image/png"
            )
        except:
            st.info("Install kaleido for PNG export")

    with col3:
        try:
            img_bytes = fig.to_image(format="svg")
            st.download_button(
                label="💾 Download SVG",
                data=img_bytes,
                file_name=f"plot_{x_col}_vs_{y_col}.svg",
                mime="image/svg+xml"
            )
        except:
            st.info("Install kaleido for SVG export")

    with col4:
        st.metric("Curves", plotted_count)

else:
    # Matplotlib export
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        buf = _save_fig_to_bytes(fig, dpi=300)
        st.download_button(
            label="💾 Download Plot (PNG, 300 DPI)",
            data=buf,
            file_name=f"plot_{x_col}_vs_{y_col}.png",
            mime="image/png"
        )

    with col2:
        buf_svg = _save_fig_to_bytes(fig, format='svg')
        st.download_button(
            label="💾 Download (SVG)",
            data=buf_svg,
            file_name=f"plot_{x_col}_vs_{y_col}.svg",
            mime="image/svg+xml"
        )

    with col3:
        st.metric("Curves", plotted_count)

    plt.close(fig)

# ---------------------------------------------------------------------------
# Data Preview & Statistics
# ---------------------------------------------------------------------------

col1, col2 = st.columns(2)

with col1:
    with st.expander("📄 Data Preview"):
        for file_name, df in dataframes.items():
            st.subheader(shorten_path(file_name, 50))
            st.dataframe(df.head(10))
            st.text(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
            st.divider()

with col2:
    with st.expander("📊 Statistics"):
        for file_name, df in dataframes.items():
            y_cols_for_file = file_y_columns.get(file_name, [])
            if x_col in df.columns and y_cols_for_file:
                st.subheader(shorten_path(file_name, 50))
                if x_col in df.columns:
                    st.markdown(f"**{x_col}**")
                    st.text(f"  Min: {df[x_col].min():.4f}  Max: {df[x_col].max():.4f}  Mean: {df[x_col].mean():.4f}")
                for yc in y_cols_for_file:
                    if yc in df.columns:
                        st.markdown(f"**{yc}**")
                        st.text(f"  Min: {df[yc].min():.4f}  Max: {df[yc].max():.4f}  Mean: {df[yc].mean():.4f}")
                st.divider()
