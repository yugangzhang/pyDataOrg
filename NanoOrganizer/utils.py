#!/usr/bin/env python3
"""
Utility functions for NanoOrganizer.

Contains helper functions for:
- Saving time-series data to CSV files
- Data processing and formatting
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
    y_name: str = "y"
) -> List[Path]:
    """
    Save time-series data to individual CSV files.
    
    Each unique time point gets its own CSV file.
    
    Parameters
    ----------
    output_dir : Path
        Directory to save CSV files
    prefix : str
        File prefix (e.g., 'uvvis', 'saxs')
    times : list
        Time values for each data point
    x_values : list
        X-axis values (wavelength, q, 2theta, etc.)
    y_values : list
        Y-axis values (absorbance, intensity, etc.)
    x_name : str
        Name for x column
    y_name : str
        Name for y column
    
    Returns
    -------
    csv_files : list
        List of created CSV file paths
    
    Examples
    --------
    >>> times = [0, 0, 0, 30, 30, 30]
    >>> wavelengths = [200, 201, 202, 200, 201, 202]
    >>> absorbance = [0.1, 0.12, 0.11, 0.3, 0.32, 0.31]
    >>> files = save_time_series_to_csv(
    ...     Path("./data"), "uvvis", 
    ...     times, wavelengths, absorbance,
    ...     x_name="wavelength", y_name="absorbance"
    ... )
    >>> # Creates: uvvis_001.csv (t=0), uvvis_002.csv (t=30)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    times = np.array(times)
    x_values = np.array(x_values)
    y_values = np.array(y_values)
    
    unique_times = np.unique(times)
    csv_files = []
    
    for i, t in enumerate(unique_times):
        mask = times == t
        x_at_t = x_values[mask]
        y_at_t = y_values[mask]
        
        # Create CSV filename
        csv_file = output_dir / f"{prefix}_{i+1:03d}.csv"
        
        # Save CSV
        header = f"{x_name},{y_name}"
        data = np.column_stack([x_at_t, y_at_t])
        np.savetxt(csv_file, data, delimiter=',', header=header, comments='')
        
        csv_files.append(csv_file)
    
    print(f"  ✓ Saved {len(csv_files)} CSV files to: {output_dir}")
    return csv_files