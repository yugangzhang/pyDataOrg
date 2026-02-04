# Adding a New Data Type to NanoOrganizer

This guide walks you through every file you need to touch to add a first-class
data type — from loader through plotter to web-app selector — with minimal
boilerplate.  Use it as a checklist.

---

## Step 1 — Create the loader: `loaders/mytype.py`

Subclass `BaseLoader`, set `data_type`, and implement `load()`.  The returned
dict must always contain a `times` key (1-D array of unique timestamps) plus
whatever axes and measurements your instrument produces.

```python
#!/usr/bin/env python3
"""Loader for 'mytype' data."""

import numpy as np
from pathlib import Path
from typing import Any, Dict, List

from NanoOrganizer.loaders.base import BaseLoader


class MyTypeLoader(BaseLoader):
    data_type = "mytype"

    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data

        if not self.link.file_paths:
            raise ValueError("No files linked. Call link_data() first.")

        times, x_vals, y_vals = [], [], []

        for fp in sorted(self.link.file_paths):
            # --- read one file ---
            raw = np.loadtxt(fp, delimiter=",", skiprows=1)
            x_vals.append(raw[:, 0])
            y_vals.append(raw[:, 1])

        # Use time_points from metadata if available; otherwise sequential
        time_points = self.link.metadata.get("time_points")
        if time_points is None:
            time_points = list(range(len(self.link.file_paths)))

        times = np.array(time_points, dtype=float)
        x     = np.array(x_vals[0])          # shared x-axis (all files same grid)
        y     = np.array(y_vals)             # (n_times, n_x)

        self._loaded_data = {
            "times": times,
            "x_axis": x,          # rename to something meaningful
            "measurements": y,    # rename to something meaningful
        }
        return self._loaded_data
```

---

## Step 2 — Register the loader in `loaders/__init__.py`

Add one import and one dict entry:

```python
from NanoOrganizer.loaders.mytype import MyTypeLoader   # ← add

LOADER_REGISTRY = {
    ...
    'mytype': MyTypeLoader,   # ← add
}
```

---

## Step 3 — Create the plotter: `viz/mytype.py`

Subclass `BasePlotter`, set the three class attributes, and implement `plot()`
with a dispatch dict.

```python
#!/usr/bin/env python3
"""Plotter for 'mytype' data."""

import numpy as np
from typing import Any, Dict

from NanoOrganizer.viz.base import BasePlotter


class MyTypePlotter(BasePlotter):
    data_type            = "mytype"
    default_plot_type    = "overview"
    available_plot_types = ["overview", "kinetics", "heatmap"]

    def plot(self, data: Dict[str, Any], plot_type: str = None,
             ax=None, **kwargs):
        if plot_type is None:
            plot_type = self.default_plot_type
        ax = self._get_axes(ax, **kwargs)

        dispatch = {
            "overview":  self._overview,
            "kinetics":  self._kinetics,
            "heatmap":   self._heatmap,
        }
        if plot_type not in dispatch:
            raise ValueError(
                f"Unknown plot_type '{plot_type}'. "
                f"Available: {self.available_plot_types}"
            )
        dispatch[plot_type](data, ax, **kwargs)
        return ax

    # ------------------------------------------------------------------
    def _overview(self, data, ax, **kwargs):
        """Single curve at a selected time point."""
        times = data["times"]
        time_point = kwargs.get("time_point")
        if time_point is None:
            time_point = times[len(times) // 2]
        idx = int(np.argmin(np.abs(times - time_point)))

        ax.plot(data["x_axis"], data["measurements"][idx], linewidth=2)
        ax.set_xlabel("X label")
        ax.set_ylabel("Y label")
        ax.set_title(f"MyType at t = {times[idx]:.0f} s")
        ax.grid(True, alpha=0.3)

    def _kinetics(self, data, ax, **kwargs):
        """Value vs time at a fixed x position."""
        x_value = kwargs.get("x_value", data["x_axis"][len(data["x_axis"]) // 2])
        x_idx   = int(np.argmin(np.abs(data["x_axis"] - x_value)))

        ax.plot(data["times"], data["measurements"][:, x_idx], "o-", linewidth=2)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Measurement")
        ax.set_title(f"Kinetics at x = {data['x_axis'][x_idx]:.2f}")
        ax.grid(True, alpha=0.3)

    def _heatmap(self, data, ax, **kwargs):
        import matplotlib.pyplot as plt
        im = ax.pcolormesh(data["x_axis"], data["times"],
                           data["measurements"], shading="auto", cmap="viridis")
        ax.set_xlabel("X label")
        ax.set_ylabel("Time (s)")
        ax.set_title("MyType Evolution")
        plt.colorbar(im, ax=ax, label="Measurement")
```

---

## Step 4 — Register the plotter in `viz/__init__.py`

Same pattern as the loader:

```python
from NanoOrganizer.viz.mytype import MyTypePlotter   # ← add

PLOTTER_REGISTRY = {
    ...
    'mytype': MyTypePlotter,   # ← add
}
```

---

## Step 5 — Add to `DEFAULT_LOADERS` in `core/run.py`

Every `Run` object gains an attribute automatically from this list.

```python
DEFAULT_LOADERS = [
    ...
    ('mytype', 'mytype', {}),   # ← add  (attr_name, registry_key, extra_kwargs)
]
```

After this, every run has a `run.mytype` accessor with `link_data()`, `load()`,
`plot()`, and `validate()`.

---

## Step 6 (optional) — Simulation: `simulations/mytype.py`

Not mandatory, but useful for demos and tests.  Follow the same pattern as the
existing 1-D generators (return long-format `(times, x, y)` lists) or the 2-D
generators (save `.npy` files, return `(paths, calibration_dict)`).

```python
def simulate_mytype_time_series_data(
    x_range=(0, 100), n_points=200, time_points=None, ...
):
    """Return (times, x_values, y_values) in long format."""
    ...
```

Register it in `simulations/__init__.py`:

```python
from NanoOrganizer.simulations.mytype import simulate_mytype_time_series_data
```

---

## Step 7 — Update `NanoOrganizer/__init__.py`

Add the new names to the imports and `__all__`:

```python
from NanoOrganizer.loaders import MyTypeLoader          # already pulled in via loaders/__init__
from NanoOrganizer.viz    import MyTypePlotter          # already pulled in via viz/__init__
from NanoOrganizer.simulations import simulate_mytype_time_series_data   # if Step 6 done

__all__ = [
    ...
    'MyTypeLoader',
    'MyTypePlotter',
    'simulate_mytype_time_series_data',   # if Step 6 done
]
```

---

## Step 8 — Add a row to `SELECTORS` in `web/app.py`

If the web app should expose a dynamic selector for your new type, add one (or
more) rows to the `SELECTORS` dict at the top of `NanoOrganizer/web/app.py`:

```python
SELECTORS = {
    ...
    ("mytype", "overview"):  ("time_point", "Time (s)",  "times"),
    ("mytype", "kinetics"):  ("x_value",    "X value",   "x_axis"),
}
```

Plot-type / data-type combinations **not** listed in `SELECTORS` render without
an extra control (e.g. heatmaps that use the full dataset).

---

## Smoke test

Paste this into a Python REPL after a fresh `pip install -e .`:

```python
import tempfile, os
from NanoOrganizer import (
    DataOrganizer, RunMetadata, ReactionParams, ChemicalSpec,
    save_time_series_to_csv,
    simulate_mytype_time_series_data,   # if Step 6 done
)

base = tempfile.mkdtemp()
org  = DataOrganizer(base)
meta = RunMetadata(
    project="Test", experiment="2024-01-01", run_id="smoke_001",
    sample_id="S1",
    reaction=ReactionParams(chemicals=[ChemicalSpec(name="X", concentration=1.0)]),
)
run  = org.create_run(meta)

# --- link synthetic data ---
times, x, y = simulate_mytype_time_series_data()
out_dir = os.path.join(base, "mytype_data")
files   = save_time_series_to_csv(out_dir, "mytype", times, x, y,
                                  x_name="x_axis", y_name="measurements")
run.mytype.link_data(files, time_points=sorted(set(times)))
org.save()

# --- reload & plot ---
org2 = DataOrganizer.load(base)
run2 = org2.get_run("Test/2024-01-01/smoke_001")
data = run2.mytype.load()
print("Keys:", list(data.keys()))
run2.mytype.plot(plot_type="overview")
print("All good!")
```

If this prints **All good!** without errors your new type is fully wired in.
