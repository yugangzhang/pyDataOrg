"""
Synthetic data generators for testing and demos.

Each sub-module simulates how a real instrument signal evolves during a
nanoparticle synthesis.  The physics models are simplified but produce
data that is visually and statistically representative.

1-D time-series generators return long-format lists
``(times, x_values, y_values)`` – feed them directly into
``save_time_series_to_csv``.

2-D generators (saxs2d, waxs2d) save ``.npy`` files and return
``(file_paths, calibration_dict)``.
"""

import numpy as np

# ---------------------------------------------------------------------------
# 1-D time-series  (long-format output)
# ---------------------------------------------------------------------------
from NanoOrganizer.simulations.uvvis import simulate_uvvis_time_series_data
from NanoOrganizer.simulations.saxs  import simulate_saxs_time_series_data
from NanoOrganizer.simulations.waxs  import simulate_waxs_time_series_data
from NanoOrganizer.simulations.dls   import simulate_dls_time_series_data
from NanoOrganizer.simulations.xas   import simulate_xas_time_series_data

# ---------------------------------------------------------------------------
# 2-D detector images  (saved to disk)
# ---------------------------------------------------------------------------
from NanoOrganizer.simulations.saxs2d import simulate_saxs2d_time_series_data
from NanoOrganizer.simulations.waxs2d import simulate_waxs2d_time_series_data

# ---------------------------------------------------------------------------
# Microscopy images  (saved to disk)
# ---------------------------------------------------------------------------
from NanoOrganizer.simulations.image import create_fake_image_series


# ---------------------------------------------------------------------------
# Noise / drift helpers  (utility, kept here for convenience)
# ---------------------------------------------------------------------------

def add_baseline_drift(values: np.ndarray, drift_rate: float = 0.001) -> np.ndarray:
    """Add a linear baseline drift (common in long measurements)."""
    drift = np.linspace(0, drift_rate * len(values), len(values))
    return values + drift


def add_instrument_noise(values: np.ndarray, noise_type: str = "gaussian",
                         noise_level: float = 0.02) -> np.ndarray:
    """Add Gaussian or Poisson-like noise."""
    n = len(values)
    if noise_type == "gaussian":
        noise = np.random.normal(0, noise_level, n)
    elif noise_type == "poisson":
        noise = np.random.normal(0, noise_level * np.sqrt(np.abs(values) + 1), n)
    else:
        noise = np.zeros(n)
    return values + noise
