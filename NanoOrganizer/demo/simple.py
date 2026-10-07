#!/usr/bin/env python3
"""
A synthetic project, so the package has something to run on anywhere.

:func:`build_demo_project` writes a small, complete project to disk: authored
metadata in the form the ingest adapter expects, a folder of 1D spectra per
sample referenced by glob, and a folder of micrographs picked up by the
``<Modality>Data/<SampleID>/`` convention.

The data is fabricated but not arbitrary. A single hidden control variable —
here a synthesis temperature — moves both the spectral band position and the
particle diameter, so the whole pipeline has something true to find:

    filter → analyse → derived columns → a real trend on Compare

Nothing is committed to the repository; the project is generated on demand and
can be deleted freely.

>>> from NanoOrganizer.demo import build_demo_project
>>> root = build_demo_project("/tmp/DemoProject")      # doctest: +SKIP
>>> from NanoOrganizer import open_project             # doctest: +SKIP
>>> wb = open_project(root)                            # doctest: +SKIP
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

#: Wavelength axis of the synthetic spectrometer, in nm.
AXIS = np.linspace(300.0, 900.0, 601)

#: The hidden control variable: synthesis temperature in degrees Celsius.
DEFAULT_TEMPERATURES = (60.0, 70.0, 80.0, 90.0, 100.0, 110.0)

#: Pixel calibration written into the micrographs, mimicking how electron
#: microscopes record it in the TIFF description tag.
PIXELS_PER_MICRON = 2000.0


def band_centre_nm(temperature_C: float) -> float:
    """Where the band sits for a given synthesis temperature."""
    return 500.0 + 0.6 * (temperature_C - 60.0)


def particle_diameter_nm(temperature_C: float) -> float:
    """Mean particle diameter for a given synthesis temperature."""
    return 8.0 + 0.15 * (temperature_C - 60.0)


# ---------------------------------------------------------------------------
# Spectra
# ---------------------------------------------------------------------------

def _spectrum(centre: float, amplitude: float, rng) -> np.ndarray:
    """One band on a sloping background, with a little noise."""
    band = amplitude * np.exp(-0.5 * ((AXIS - centre) / 28.0) ** 2)
    background = 0.08 + 0.00012 * (900.0 - AXIS)
    return band + background + rng.normal(0.0, 0.0015, AXIS.size)


def _write_spectra(folder: Path, batch: str, centre: float, n_frames: int,
                   rng) -> None:
    """A growth series: the band rises towards its final amplitude."""
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(n_frames):
        fraction = (index + 1) / n_frames
        amplitude = 1.0 * (1.0 - np.exp(-3.0 * fraction))
        temperature = 25.0 + 70.0 * fraction
        name = (f"demo_{batch}_t{index * 60:05d}s"
                f"_T{temperature:.0f}C.npy")
        np.save(folder / name, _spectrum(centre, amplitude, rng))


# ---------------------------------------------------------------------------
# Micrographs
# ---------------------------------------------------------------------------

def _micrograph(diameter_nm: float, nm_per_pixel: float, size: int,
                rng) -> np.ndarray:
    """Dark discs on a light support, roughly log-normal in size."""
    image = np.full((size, size), 205.0)
    radius_px = 0.5 * diameter_nm / nm_per_pixel
    spacing = max(int(6 * radius_px), 12)

    yy, xx = np.ogrid[:size, :size]
    for row in range(spacing, size - spacing, spacing):
        for column in range(spacing, size - spacing, spacing):
            jitter = rng.normal(0.0, 0.08 * radius_px, 2)
            this_radius = max(radius_px * rng.lognormal(0.0, 0.12), 1.5)
            mask = ((yy - row - jitter[0]) ** 2
                    + (xx - column - jitter[1]) ** 2) <= this_radius ** 2
            image[mask] = 55.0 + rng.normal(0.0, 3.0)

    return np.clip(image + rng.normal(0.0, 2.5, image.shape), 0, 255)


def _write_micrographs(folder: Path, diameter_nm: float, n_images: int,
                       size: int, rng) -> None:
    """Write TIFFs carrying a pixel calibration in the description tag."""
    try:
        from PIL import Image
    except ImportError:          # pragma: no cover - Pillow is an extra
        return

    folder.mkdir(parents=True, exist_ok=True)
    nm_per_pixel = 1000.0 / PIXELS_PER_MICRON
    description = (
        f"DemoScope XpixCal={PIXELS_PER_MICRON:.6f}"
        f"YpixCal={PIXELS_PER_MICRON:.6f}Unit=um"
    )
    for index in range(1, n_images + 1):
        array = _micrograph(diameter_nm, nm_per_pixel, size, rng)
        image = Image.fromarray(array.astype(np.uint8))
        image.save(folder / f"{index}.tif", description=description)

    (folder / "note.txt").write_text(
        f"synthetic micrographs, nominal d = {diameter_nm:.1f} nm\n")


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

_METADATA_HEADER = '''"""Synthetic synthesis records for the NanoOrganizer demo project.

Generated by ``NanoOrganizer.demo.build_demo_project`` — edit the generator,
not this file. The shape is the one the ``sampledict`` ingest adapter expects:
a module-level dict keyed by stable sample ids, each holding nested parameter
blocks, with any block that names files becoming a measurement.
"""

Synthesis_dict = {
'''


def _metadata_source(records: Sequence[Dict]) -> str:
    lines = [_METADATA_HEADER]
    for record in records:
        lines.append(f'    "{record["sample_id"]}": {{\n')
        lines.append(f'        "sample_id": "{record["sample_id"]}",\n')
        lines.append('        "synthesis_batch": {\n')
        lines.append(f'            "batch_tag": "{record["batch_tag"]}",\n')
        lines.append(f'            "run_id": "{record["run_id"]}",\n')
        lines.append('            "campaign": "demo",\n')
        lines.append(f'            "status": "{record["status"]}",\n')
        lines.append('            "aborted": False,\n')
        lines.append(f'            "started_at": "{record["started_at"]}",\n')
        lines.append(f'            "run_time_s": {record["run_time_s"]:.1f},\n')
        lines.append('        },\n')
        lines.append('        "conditions": {\n')
        lines.append(f'            "temperature_C": {record["temperature_C"]:.1f},\n')
        lines.append(f'            "stir_rate_rpm": {record["stir_rate_rpm"]},\n')
        lines.append('            "solvent": "water",\n')
        lines.append('            "hold_time_min": 30.0,\n')
        lines.append('        },\n')
        lines.append('        "reagents": {\n')
        lines.append('            "precursor": {"concentration_mM": 2.0, '
                     '"volume_uL": 500.0},\n')
        lines.append('            "reductant": {"concentration_mM": 16.0, '
                     f'"volume_uL": {record["reductant_uL"]:.1f}}},\n')
        lines.append('        },\n')
        lines.append('        "spectra": {\n')
        lines.append('            "modality": "uvvis",\n')
        lines.append('            "instrument": "DemoSpec",\n')
        lines.append(f'            "n_frames": {record["n_frames"]},\n')
        lines.append(f'            "spectrum_glob": "{record["spectrum_glob"]}",\n')
        lines.append(f'            "wavelength_file": "{record["wavelength_file"]}",\n')
        lines.append('        },\n')
        lines.append('    },\n')
    lines.append("}\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_demo_project(root, *, temperatures: Sequence[float] = DEFAULT_TEMPERATURES,
                       n_frames: int = 12, n_images: int = 3,
                       image_size: int = 384, seed: int = 0,
                       with_images: bool = True,
                       overwrite: bool = True) -> Path:
    """Write a complete synthetic project and return its root path.

    Parameters
    ----------
    root : path
        Where to write it. Created if missing.
    temperatures : sequence of float
        One sample per entry. This is the hidden control variable that both the
        band position and the particle size follow.
    n_frames : int
        Spectra per sample, written as a growth series over time.
    n_images : int
        Micrographs per sample. Set ``with_images=False`` to skip them.
    overwrite : bool
        Replace an existing demo project. Only ever removes a directory that
        carries the generator's own marker file, so pointing this at real data
        cannot delete it.
    """
    root = Path(root).expanduser().absolute()
    marker = root / ".nanoorganizer-demo"

    if root.exists() and overwrite:
        if any(root.iterdir()) and not marker.exists():
            raise FileExistsError(
                f"{root} is not empty and was not made by build_demo_project. "
                f"Choose another path, or delete it yourself."
            )
        shutil.rmtree(root)

    root.mkdir(parents=True, exist_ok=True)
    marker.write_text("generated by NanoOrganizer.demo.build_demo_project\n")

    rng = np.random.default_rng(seed)
    spectra_root = root / "RawSpectra" / "demo_run"
    spectra_root.mkdir(parents=True, exist_ok=True)
    axis_path = spectra_root / "axis_wavelength.npy"
    np.save(axis_path, AXIS)

    records: List[Dict] = []
    for index, temperature in enumerate(temperatures, start=1):
        sample_id = f"Sample{index:06d}"
        batch = f"b{index:02d}"

        _write_spectra(spectra_root, batch, band_centre_nm(temperature),
                       n_frames, rng)

        if with_images:
            _write_micrographs(root / "TEMData" / sample_id,
                               particle_diameter_nm(temperature),
                               n_images, image_size, rng)

        # One run deliberately failed, so the demo has a row that must be
        # excluded rather than a uniformly tidy table.
        failed = index == len(temperatures)

        records.append({
            "sample_id": sample_id,
            "batch_tag": f"demo_batch_{(index - 1) // 3 + 1}",
            "run_id": f"demo_run_{index:02d}",
            "status": "error" if failed else "done",
            "started_at": f"2026-03-{index + 1:02d}T09:00:00",
            "run_time_s": 1800.0 + 60.0 * index,
            "temperature_C": float(temperature),
            "stir_rate_rpm": 400 + 50 * (index % 3),
            "reductant_uL": 300.0 + 40.0 * index,
            "n_frames": n_frames,
            # Relative to the project root, so the project moves as a folder.
            "spectrum_glob": (spectra_root / f"demo_{batch}_*.npy")
                             .relative_to(root).as_posix(),
            "wavelength_file": axis_path.relative_to(root).as_posix(),
        })

    meta_dir = root / "MetaData"
    meta_dir.mkdir(exist_ok=True)
    (meta_dir / "Synthesis_dict.py").write_text(_metadata_source(records))

    return root


def demo_truth(temperatures: Sequence[float] = DEFAULT_TEMPERATURES):
    """The values the generator used, for checking an analysis against.

    Returns a dataframe of the hidden truth: what band centre and particle
    diameter each sample was built with. Comparing a fit against this is how
    the demo notebooks show that the pipeline recovers something real.
    """
    import pandas as pd

    return pd.DataFrame([
        {
            "sample_id": f"Sample{index:06d}",
            "temperature_C": float(temperature),
            "true_band_centre_nm": band_centre_nm(temperature),
            "true_diameter_nm": particle_diameter_nm(temperature),
        }
        for index, temperature in enumerate(temperatures, start=1)
    ])


__all__ = ["build_demo_project", "demo_truth", "AXIS", "DEFAULT_TEMPERATURES",
           "band_centre_nm", "particle_diameter_nm"]
