#!/usr/bin/env python3
"""
Generic readers – get an array out of a measurement without knowing the technique.

The visualisation layer dispatches on ``shape`` (curve / image / volume /
correlation), so it needs one way to read a frame for each of those, whatever
instrument wrote it. These are the fallbacks: a modality with a real loader of
its own (UV-Vis series, scattering products) should use that instead, and
:func:`load_frame` prefers it where one exists.

Nothing here guesses units. An array is returned with whatever axes the file
carried, and the caller labels it from the modality registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Suffixes we can open at all, by how they are read.
_ARRAY_SUFFIXES = {".npy", ".npz"}
_IMAGE_SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}
_TEXT_SUFFIXES = {".txt", ".csv", ".dat", ".xy"}


def read_array(path) -> np.ndarray:
    """Read *path* into a numpy array, whatever reasonable format it is in.

    Raises
    ------
    ValueError
        If the suffix is not one this module can open, naming what it can.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".npy":
        return np.load(path, allow_pickle=False)

    if suffix == ".npz":
        bundle = np.load(path, allow_pickle=False)
        keys = list(bundle.keys())
        if not keys:
            raise ValueError(f"{path.name} is an empty .npz")
        # Largest array wins: an npz usually bundles the data with its axes.
        return bundle[max(keys, key=lambda k: bundle[k].size)]

    if suffix in _IMAGE_SUFFIXES:
        from PIL import Image
        with Image.open(path) as image:
            return np.asarray(image, dtype=float)

    if suffix in _TEXT_SUFFIXES:
        return _read_text(path, suffix)

    raise ValueError(
        f"Cannot read {path.name}: unsupported suffix {suffix!r}. "
        f"Known: {', '.join(sorted(_ARRAY_SUFFIXES | _IMAGE_SUFFIXES | _TEXT_SUFFIXES))}"
    )


def _read_text(path: Path, suffix: str) -> np.ndarray:
    """Read a delimited text file, tolerating a bare header row.

    Instruments write ``wavelength_nm,absorbance`` on line one as often as they
    write ``# wavelength_nm, absorbance``, and an uncommented header is not a
    corrupt file — it is the single most common shape of exported data. So a
    first line that will not parse as numbers is skipped, once. A *second*
    unparseable line is a real problem and is reported as one.
    """
    delimiter = "," if suffix == ".csv" else None
    comments = ("#", "%", ";")
    try:
        return np.loadtxt(path, delimiter=delimiter, comments=comments, ndmin=2)
    except ValueError:
        pass

    try:
        return np.loadtxt(path, delimiter=delimiter, comments=comments,
                          skiprows=1, ndmin=2)
    except ValueError as exc:
        # Comma-separated data in a ``.dat``/``.txt`` is the other common case.
        if delimiter is None:
            try:
                return np.loadtxt(path, delimiter=",", comments=comments,
                                  skiprows=1, ndmin=2)
            except ValueError:
                pass
        raise ValueError(
            f"Cannot read {path.name} as a numeric table: {exc}. "
            f"More than one header row, or an unusual delimiter — convert it, "
            f"or give this modality a loader of its own."
        ) from exc


def frame_paths(measurement, resolver) -> List[Path]:
    """Readable files of *measurement*, in order."""
    return measurement.resolve(resolver)


def load_image(measurement, resolver, index: int = 0,
               crop_banner: bool = True) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Read one 2D frame, returning ``(array, info)``.

    TIFFs go through the micrograph reader so an instrument banner is cropped
    and the pixel calibration comes back in ``info``; everything else is read
    plainly. A 3D array is treated as a stack and its first plane returned, so
    a detector file with a singleton frame axis still displays.
    """
    paths = frame_paths(measurement, resolver)
    if not paths:
        raise FileNotFoundError(
            f"No files resolve for {measurement.measurement_id}")
    if not 0 <= index < len(paths):
        raise IndexError(f"frame {index} of {len(paths)}")

    path = paths[index]
    info: Dict[str, Any] = {"file": path.name, "n_frames": len(paths),
                            "nm_per_pixel": None}

    if path.suffix.lower() in {".tif", ".tiff"}:
        from NanoOrganizer.analysis.imaging import read_micrograph
        array, scale, extra = read_micrograph(path, crop_banner=crop_banner)
        info.update(extra)
        info["nm_per_pixel"] = scale
    else:
        array = read_array(path)

    array = np.asarray(array, dtype=float)
    if array.ndim == 3:
        # Colour image, or a stack with one plane per frame.
        array = array.mean(axis=2) if array.shape[2] in (3, 4) else array[0]
        info["reduced_from_3d"] = True
    if array.ndim != 2:
        raise ValueError(
            f"{path.name} is {array.ndim}D; expected a 2D image")

    info["shape"] = array.shape
    return array, info


def load_volume(measurement, resolver, index: int = 0
                ) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Read a 3D volume, returning ``(array, info)``.

    A single file holding a 3D array is used as-is. Failing that, every frame
    of the measurement is stacked, which is how a tomographic slice series or a
    z-stack written one file per plane comes back as a volume.
    """
    paths = frame_paths(measurement, resolver)
    if not paths:
        raise FileNotFoundError(
            f"No files resolve for {measurement.measurement_id}")

    first = read_array(paths[index if index < len(paths) else 0])
    if np.ndim(first) == 3:
        volume = np.asarray(first, dtype=float)
        info = {"file": paths[index].name, "source": "single 3D file"}
    else:
        planes = [np.asarray(read_array(p), dtype=float) for p in paths]
        shapes = {p.shape for p in planes}
        if len(shapes) != 1:
            raise ValueError(
                f"{measurement.measurement_id}: frames have different shapes "
                f"({len(shapes)} distinct), so they cannot be stacked")
        volume = np.stack(planes)
        info = {"source": f"stacked {len(planes)} frames"}

    info["shape"] = volume.shape
    return volume, info


def load_curve_set(measurement, resolver, *, max_curves: int = 200,
                   crop: Optional[Tuple[float, float]] = None
                   ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Read a measurement as ``(x, Y, info)`` with ``Y`` of shape (n, len(x)).

    A time series comes back with one row per frame; a set of independent
    two-column files comes back with one row per file, which is what lets the
    same viewer draw a UV-Vis run and a folder of Raman spectra.
    """
    spec = measurement.spec
    if spec is not None and spec.shape in ("series", "corr"):
        try:
            from NanoOrganizer.analysis import frames as _frames
            series = _frames.load_series(measurement, resolver, crop=crop)
            return (np.asarray(series.wavelength, dtype=float),
                    np.asarray(series.absorbance, dtype=float),
                    {"labels": [f"t = {t:.0f} s" for t in series.t_s],
                     "t_s": np.asarray(series.t_s, dtype=float),
                     "source": "time series"})
        except (FileNotFoundError, ValueError, ImportError):
            pass   # fall through to reading the files as plain curves

    from NanoOrganizer.analysis.peaks import load_curve

    paths = frame_paths(measurement, resolver)[:max_curves]
    if not paths:
        raise FileNotFoundError(
            f"No files resolve for {measurement.measurement_id}")

    rows: List[np.ndarray] = []
    labels: List[str] = []
    axis: Optional[np.ndarray] = None

    for path in paths:
        array = read_array(path)
        if array.ndim == 2 and array.shape[1] >= 2:
            x, y = array[:, 0], array[:, 1]
        elif array.ndim == 1 and axis is not None and array.size == axis.size:
            x, y = axis, array
        else:
            continue
        if axis is None:
            axis = np.asarray(x, dtype=float)
        if len(y) != len(axis):
            continue
        rows.append(np.asarray(y, dtype=float))
        labels.append(path.name)

    if axis is None or not rows:
        # Single-column frames on a shared axis: the series path handles those.
        x, y, info = load_curve(measurement, resolver, crop=crop)
        return x, y[None, :], {"labels": [info.get("source", "curve")],
                               "source": "single curve"}

    out_x, out_y = axis, np.vstack(rows)
    if crop is not None:
        keep = (out_x >= crop[0]) & (out_x <= crop[1])
        out_x, out_y = out_x[keep], out_y[:, keep]
    return out_x, out_y, {"labels": labels, "source": f"{len(rows)} files"}


__all__ = ["read_array", "frame_paths", "load_image", "load_volume",
           "load_curve_set"]
