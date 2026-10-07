#!/usr/bin/env python3
"""
The lab demo — a rig writing files, the way a rig does.

This is the data behind the three workflow notebooks (``notebook/10`` → ``12``)
and the web app's **Demo** page. It lives here, once, so the notebook and the
page call the same generator rather than two copies that drift.

It is deliberately **messy in the way real campaigns are messy**: three
instruments, three folder trees, three naming conventions, none agreeing, and
none laid out as ``<Modality>Data/<SampleID>/``::

    <root>/
    ├── RawData/
    │   ├── spectrometer/2026-03-11/   S01_t0000s.csv …  one file per frame
    │   ├── microscope_share/S01/      img_01.tif …      a folder per sample
    │   └── xrd_rig/                   S01_waxs.dat      one file per sample
    └── Meta/
        ├── synthesis_dict.json        what the operator wrote down
        └── truth.csv                  the answer key

Only the spectra are named in the metadata dict. The micrographs and the
diffraction come from other people on other days and are linked by hand —
which is what actually happens.

**The hidden control variable is the synthesis temperature.** It sets the
particle size (:func:`diameter_nm`), which sets the plasmon band
(:func:`band_nm`), the diffraction line width (Scherrer) and what the
micrographs show.

Each instrument is one function, so a notebook can run them one at a time and
look in between; :func:`simulate_lab` runs all of them in order. Passing one
shared ``rng`` through them in that order reproduces the same files.

>>> from NanoOrganizer.demo.lab import simulate_lab
>>> lab = simulate_lab()                 # -> ~/Repos/OrgDemo/Lab   # doctest: +SKIP
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Union

import numpy as np

#: One hidden number per sample. Everything else follows from it.
TEMPERATURE_C: Dict[str, float] = {"S01": 60.0, "S02": 70.0, "S03": 80.0,
                                   "S04": 90.0, "S05": 100.0, "S06": 110.0}

#: The seed notebook 10 uses; change it and every number moves a little.
SEED = 7

WAVELENGTH = np.linspace(380.0, 780.0, 401)
N_FRAMES = 14
FRAME_INTERVAL_S = 90

NM_PER_PIXEL = 0.5
IMAGE_SIZE = 320
IMAGES_PER_SAMPLE = 3
PARTICLES_PER_IMAGE = 26

Q = np.linspace(2.0, 5.0, 900)
PEAKS = ((2.67, 1.00), (3.08, 0.46), (4.36, 0.22))      # fcc 111, 200, 220

#: Scherrer: FWHM = K·2π / D, with D in Å.
SCHERRER_K = 0.9


def diameter_nm(temperature_C: float) -> float:
    """Hotter synthesis, fewer nuclei, bigger particles."""
    return 6.0 + 0.16 * (temperature_C - 60.0)


def band_nm(d: float) -> float:
    """Plasmon band red-shifts as the particle grows."""
    return 512.0 + 1.9 * d


@dataclass(frozen=True)
class LabPaths:
    """Where each instrument writes, under one root."""

    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "RawData"

    @property
    def spectra(self) -> Path:
        return self.raw / "spectrometer" / "2026-03-11"

    @property
    def scope(self) -> Path:
        return self.raw / "microscope_share"

    @property
    def xrd(self) -> Path:
        return self.raw / "xrd_rig"

    @property
    def meta(self) -> Path:
        return self.root / "Meta"

    @property
    def synthesis_dict(self) -> Path:
        return self.meta / "synthesis_dict.json"

    @property
    def truth(self) -> Path:
        return self.meta / "truth.csv"

    @property
    def organizer(self) -> Path:
        """Where notebook 11 and the Demo page save the organizer."""
        return self.root / "lab.json"

    def make(self) -> "LabPaths":
        for folder in (self.spectra, self.scope, self.xrd, self.meta):
            folder.mkdir(parents=True, exist_ok=True)
        return self


def lab_paths(root: Union[str, Path, None] = None) -> LabPaths:
    """The layout under *root* — ``demo_root("Lab")`` by default. Writes nothing."""
    if root is None:
        from NanoOrganizer.demo import demo_root

        root = demo_root("Lab")
    return LabPaths(Path(root).expanduser())


# ---------------------------------------------------------------------------
# The three instruments
# ---------------------------------------------------------------------------

def write_spectra(folder: Union[str, Path],
                  temperatures: Mapping[str, float] = TEMPERATURE_C, *,
                  rng: Optional[np.random.Generator] = None) -> List[Path]:
    """The spectrometer: a growth series per sample, one CSV per frame.

    Fourteen frames over twenty minutes, acquisition time in the filename
    (``S01_t0090s.csv``). The band grows and red-shifts as the particles do,
    on a scattering background.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = rng if rng is not None else np.random.default_rng(SEED)

    written = []
    for sample, temperature in temperatures.items():
        final_d = diameter_nm(temperature)
        for frame in range(N_FRAMES):
            progress = (frame + 1) / N_FRAMES
            # Growth saturates, so the band moves fast early and then settles.
            d = final_d * (1.0 - np.exp(-3.0 * progress))
            centre = band_nm(d)
            width = 44.0 - 0.9 * d
            signal = (0.08 + 0.9 * progress) * np.exp(
                -0.5 * ((WAVELENGTH - centre) / width) ** 2)
            baseline = 0.04 + 8e3 / WAVELENGTH ** 2        # scattering
            noise = rng.normal(0.0, 0.004, WAVELENGTH.size)

            path = folder / f"{sample}_t{frame * FRAME_INTERVAL_S:04d}s.csv"
            np.savetxt(path, np.column_stack([WAVELENGTH,
                                              signal + baseline + noise]),
                       delimiter=",", header="wavelength_nm,absorbance",
                       comments="")
            written.append(path)
    return written


def micrograph(d_nm: float, rng: np.random.Generator) -> np.ndarray:
    """Dark particles of diameter *d_nm* on a noisy support, as 0–255 floats."""
    field = (np.full((IMAGE_SIZE, IMAGE_SIZE), 196.0)
             + rng.normal(0, 5, (IMAGE_SIZE, IMAGE_SIZE)))
    radius_px = 0.5 * d_nm / NM_PER_PIXEL
    yy, xx = np.ogrid[:IMAGE_SIZE, :IMAGE_SIZE]
    for _ in range(PARTICLES_PER_IMAGE):
        cy, cx = rng.uniform(radius_px, IMAGE_SIZE - radius_px, 2)
        r = radius_px * rng.normal(1.0, 0.12)
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= r ** 2
        field[mask] = 70.0 + rng.normal(0, 4)
    return np.clip(field, 0, 255)


def write_micrographs(folder: Union[str, Path],
                      temperatures: Mapping[str, float] = TEMPERATURE_C, *,
                      rng: Optional[np.random.Generator] = None) -> List[Path]:
    """The microscope: a folder per sample of calibrated TIFFs.

    The pixel calibration goes in the image description, the way the
    instrument writes it, so the micrographs can be read in nanometres
    without anyone remembering the magnification. A ``session.txt`` sits
    beside them and is not a micrograph — linking by technique leaves it out.
    """
    from PIL import Image

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = rng if rng is not None else np.random.default_rng(SEED)

    pixels_per_micron = 1000.0 / NM_PER_PIXEL
    description = (f"LabScope XpixCal={pixels_per_micron:.6f}"
                   f"YpixCal={pixels_per_micron:.6f}Unit=um")

    written = []
    for sample, temperature in temperatures.items():
        session = folder / sample
        session.mkdir(exist_ok=True)
        for index in range(1, IMAGES_PER_SAMPLE + 1):
            array = micrograph(diameter_nm(temperature), rng).astype(np.uint8)
            path = session / f"img_{index:02d}.tif"
            Image.fromarray(array).save(path, description=description)
            written.append(path)
        (session / "session.txt").write_text(
            f"{sample}: {IMAGES_PER_SAMPLE} fields, {NM_PER_PIXEL} nm/px, "
            f"operator RH\n")
    return written


def write_diffraction(folder: Union[str, Path],
                      temperatures: Mapping[str, float] = TEMPERATURE_C, *,
                      rng: Optional[np.random.Generator] = None) -> List[Path]:
    """The diffractometer: one two-column pattern per sample.

    The line width narrows as the crystallites grow — Scherrer — so
    diffraction sees the same hidden number the spectra do, from a
    completely different direction.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = rng if rng is not None else np.random.default_rng(SEED)

    written = []
    for sample, temperature in temperatures.items():
        d = diameter_nm(temperature)
        fwhm = SCHERRER_K * 2 * np.pi / (d * 10.0)        # 1/Å
        sigma = fwhm / 2.355
        pattern = 60.0 / Q                                 # background
        for centre, height in PEAKS:
            pattern += 900 * height * np.exp(-0.5 * ((Q - centre) / sigma) ** 2)
        pattern += rng.normal(0, 4, Q.size)

        path = folder / f"{sample}_waxs.dat"
        np.savetxt(path, np.column_stack([Q, pattern]),
                   header="q_invA  intensity", comments="# ")
        written.append(path)
    return written


# ---------------------------------------------------------------------------
# What the operator wrote down, and the answer key
# ---------------------------------------------------------------------------

def synthesis_dict(spectra_folder: Union[str, Path],
                   temperatures: Mapping[str, float] = TEMPERATURE_C
                   ) -> Dict[str, dict]:
    """The metadata dict: one record per sample, keyed by sample id.

    It holds the synthesis conditions and **the spectra only** — the block
    naming files becomes a measurement when it is ingested. The micrographs and
    the diffraction are not in here; nobody wrote them down.
    """
    record = {}
    for index, (sample, temperature) in enumerate(temperatures.items(),
                                                  start=1):
        record[sample] = {
            "sample_id": sample,
            "synthesis_batch": {
                "run_id": f"run_{index:03d}",
                "batch_tag": "2026-03-11",
                "campaign": "lab-demo",
                "status": "done",
                "started_at": f"2026-03-11T09:{index * 7:02d}:00",
            },
            "conditions": {
                "temperature_C": temperature,
                "hold_time_min": 21.0,
                "stir_rate_rpm": 400,
                "solvent": "water",
            },
            "reagents": {
                "precursor": {"concentration_mM": 2.0, "volume_uL": 500.0},
                "reductant": {"concentration_mM": 16.0, "volume_uL": 250.0},
            },
            "uvvis_growth": {
                "modality": "uvvis",
                "instrument": "LabSpec 2000",
                "n_frames": N_FRAMES,
                "spectrum_glob": f"{spectra_folder}/{sample}_t*.csv",
            },
        }
    return record


def write_synthesis_dict(path: Union[str, Path], record: Mapping) -> Path:
    """Save the metadata dict as JSON, so a later session loads the real dict."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2))
    return path


def lab_truth(temperatures: Mapping[str, float] = TEMPERATURE_C):
    """The answer key as a table: what the generator actually used."""
    import pandas as pd

    return pd.DataFrame([
        {"sample_id": sample,
         "temperature_C": temperature,
         "true_diameter_nm": round(diameter_nm(temperature), 2),
         "true_band_nm": round(band_nm(diameter_nm(temperature)), 1)}
        for sample, temperature in temperatures.items()
    ])


# ---------------------------------------------------------------------------
# All of it
# ---------------------------------------------------------------------------

def simulate_lab(root: Union[str, Path, None] = None, *,
                 temperatures: Mapping[str, float] = TEMPERATURE_C,
                 seed: int = SEED) -> LabPaths:
    """Write the whole lab — spectra, micrographs, diffraction, dict, truth.

    *root* defaults to ``demo_root("Lab")`` (``~/Repos/OrgDemo/Lab``). Files
    are overwritten in place; nothing else under *root* is touched, and no
    organizer is built — that is notebook 11's job, or the Demo page's.
    Returns the :class:`LabPaths`.
    """
    paths = lab_paths(root).make()
    rng = np.random.default_rng(seed)

    write_spectra(paths.spectra, temperatures, rng=rng)
    write_micrographs(paths.scope, temperatures, rng=rng)
    write_diffraction(paths.xrd, temperatures, rng=rng)
    write_synthesis_dict(paths.synthesis_dict,
                         synthesis_dict(paths.spectra, temperatures))
    lab_truth(temperatures).to_csv(paths.truth, index=False)
    return paths


__all__ = [
    "TEMPERATURE_C", "SEED", "WAVELENGTH", "N_FRAMES", "NM_PER_PIXEL", "Q",
    "PEAKS", "diameter_nm", "band_nm",
    "LabPaths", "lab_paths",
    "write_spectra", "micrograph", "write_micrographs", "write_diffraction",
    "synthesis_dict", "write_synthesis_dict", "lab_truth", "simulate_lab",
]
