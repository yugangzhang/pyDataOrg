#!/usr/bin/env python3
"""
Utility functions for NanoOrganizer.
"""

import numpy as np
from pathlib import Path
from typing import List


def save_time_series_to_csv(
    output_dir: Path,
    prefix: str,
    times: List[float],
    x_values: List[float],
    y_values: List[float],
    x_name: str = "x",
    y_name: str = "y",
) -> List[Path]:
    """
    Save time-series data to one CSV per unique time point.

    Parameters
    ----------
    output_dir : Path
        Directory to save CSV files.
    prefix : str
        File prefix (e.g. 'uvvis', 'saxs').
    times : list
        Time value for every data point (long format).
    x_values : list
        X-axis values (wavelength, q, 2theta …).
    y_values : list
        Y-axis values (absorbance, intensity …).
    x_name, y_name : str
        Column headers written into the CSV.

    Returns
    -------
    list of Path
        Paths to the created CSV files, one per unique time.

    Examples
    --------
    >>> files = save_time_series_to_csv(
    ...     Path("./data"), "uvvis",
    ...     [0, 0, 0, 30, 30, 30],
    ...     [200, 201, 202, 200, 201, 202],
    ...     [0.1, 0.12, 0.11, 0.3, 0.32, 0.31],
    ...     x_name="wavelength", y_name="absorbance",
    ... )
    >>> # Creates: uvvis_001.csv  (t=0)
    >>> #          uvvis_002.csv  (t=30)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    times = np.array(times)
    x_values = np.array(x_values)
    y_values = np.array(y_values)

    unique_times = np.unique(times)
    csv_files: List[Path] = []

    for i, t in enumerate(unique_times):
        mask = times == t
        data = np.column_stack([x_values[mask], y_values[mask]])

        csv_file = output_dir / f"{prefix}_{i + 1:03d}.csv"
        header = f"{x_name},{y_name}"
        np.savetxt(csv_file, data, delimiter=',', header=header, comments='')
        csv_files.append(csv_file)

    print(f"  ✓ Saved {len(csv_files)} CSV files to: {output_dir}")
    return csv_files
