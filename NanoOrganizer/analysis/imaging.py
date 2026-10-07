#!/usr/bin/env python3
"""
Particle sizing from micrographs, in nanometres rather than pixels.

A size distribution in pixels is not a result. The calibration therefore comes
first, and the analysis refuses to report nanometres it cannot justify: if no
pixel size is found and none is supplied, diameters come back in pixels with
``calibrated = False`` in the diagnostics, so nothing downstream can mistake
one for the other.

JEOL instruments write the calibration into the TIFF ``ImageDescription`` tag::

    BNL JEM-1400 … XpixCal=2520.415000YpixCal=2520.415000Unit=um …

which is 2520.415 pixels per micrometre, i.e. 0.3968 nm per pixel. They also
append an information banner below the image — on a 2048-wide frame the file is
2372 rows tall — and the banner is bright, uniform, and would otherwise be
segmented as one enormous particle.

Segmentation is deliberately classical: Otsu, then watershed on the distance
transform to split particles that touch. Gold on a carbon film is a
high-contrast, nearly bimodal image, which is the case classical thresholding
handles well and where a learned model would add a dependency and an unaudited
failure mode for nothing.

Kernels and adapter (``docs/kernel_adapter_rule.md``) — four of the five
functions here take arrays:

``segment_particles(image, ...)``   label map from one image
``measure_particles(labels, ...)``  diameters from one label map
``size_from_image(image, ...)``     the two above, in one call
``size_statistics(diameters)``      the pooled numbers
``particle_sizing(measurement, resolver, ...)``
    the **adapter** — reads every frame, calls the kernels, pools, and files
    the answer as an :class:`AnalysisResult`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from NanoOrganizer.analysis.result import AnalysisResult

# JEOL writes the calibration as pixels per `Unit`.
_CAL_RE = re.compile(
    r"XpixCal=(?P<x>[0-9.]+).*?(?:YpixCal=(?P<y>[0-9.]+))?.*?Unit=(?P<unit>\w+)",
    re.DOTALL,
)

_UNIT_NM = {"nm": 1.0, "um": 1e3, "µm": 1e3, "mm": 1e6, "m": 1e9}


def pixel_size_nm(path: Path) -> Tuple[Optional[float], Dict[str, Any]]:
    """Read nm-per-pixel out of a micrograph's embedded calibration.

    Returns ``(nm_per_pixel, info)``; ``nm_per_pixel`` is None when the file
    carries no calibration this function understands.
    """
    info: Dict[str, Any] = {}
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is an optional extra
        return None, {"error": "Pillow is not installed"}

    try:
        with Image.open(path) as image:
            description = ""
            if hasattr(image, "tag_v2"):
                description = str(image.tag_v2.get(270, "") or "")
            if not description:
                description = str(image.info.get("ImageDescription", "") or "")
            info["size"] = image.size
    except (OSError, ValueError) as exc:
        return None, {"error": f"cannot read {path.name}: {exc}"}

    match = _CAL_RE.search(description)
    if not match:
        return None, info

    unit = match.group("unit").lower()
    scale = _UNIT_NM.get(unit)
    if scale is None:
        info["unit"] = unit
        return None, info

    per_unit = float(match.group("x"))
    if per_unit <= 0:
        return None, info

    info.update({"calibration_unit": unit, "pixels_per_unit": per_unit,
                 "instrument": description.split("XpixCal")[0].strip()[:60]})
    return scale / per_unit, info


def read_micrograph(path, *, crop_banner: bool = True,
                    nm_per_pixel: Optional[float] = None,
                    ) -> Tuple[np.ndarray, Optional[float], Dict[str, Any]]:
    """Load a micrograph as a 2D float array, cropped and calibrated.

    Parameters
    ----------
    crop_banner : bool
        Remove a non-square instrument banner. A frame taller than it is wide
        is cropped to its leading square, which is how JEOL writes them; a
        frame that is already square is left alone.
    nm_per_pixel : float, optional
        Override the embedded calibration — for a microscope that writes none,
        or when you have a better number from a standard.
    """
    from PIL import Image

    path = Path(path)
    calibrated, info = pixel_size_nm(path)
    scale = nm_per_pixel if nm_per_pixel is not None else calibrated
    info["nm_per_pixel_source"] = (
        "override" if nm_per_pixel is not None
        else ("embedded" if calibrated is not None else "none")
    )

    with Image.open(path) as image:
        array = np.asarray(image.convert("F" if image.mode not in ("L", "I;16")
                                         else image.mode), dtype=float)

    info["raw_shape"] = array.shape
    if crop_banner and array.ndim == 2 and array.shape[0] > array.shape[1]:
        info["banner_rows"] = int(array.shape[0] - array.shape[1])
        array = array[: array.shape[1], :]
    info["shape"] = array.shape
    return array, scale, info


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

def segment_particles(image: np.ndarray, *,
                      dark_particles: Optional[bool] = None,
                      smooth_sigma: float = 1.0,
                      min_area_px: int = 20,
                      split_touching: bool = True,
                      min_distance_px: Optional[int] = None,
                      min_contrast_frac: float = 0.2,
                      ) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Label particles in a micrograph; return ``(labels, info)``.

    Parameters
    ----------
    dark_particles : bool, optional
        True for TEM, where metal absorbs and particles are darker than the
        support; False for SEM, where they are usually brighter. Left as None
        the polarity is read off the image: particles are the minority phase
        either side of the Otsu threshold, because a field of view that is
        more than half particle is not one you can size anyway. Getting this
        backwards segments the *support*, which is the single most common way
        a sizing run produces confident nonsense, so it is worth not having to
        remember.
    split_touching : bool
        Watershed on the distance transform, which separates particles that
        merely touch. It cannot separate genuinely overlapping ones — those
        stay merged and are usually caught by the shape filter afterwards.
    min_distance_px : int, optional
        Minimum separation between watershed seeds. Left as None it is derived
        from the distance transform of the mask itself, which is the only way
        it can be right across magnifications: these grids are imaged anywhere
        from 0.07 to 0.4 nm per pixel, and a fixed seed spacing that keeps two
        touching particles apart at one magnification cuts a single particle in
        half at another.
    min_contrast_frac : float
        Reject regions whose mean intensity is less than this fraction of the
        way from the threshold to the darkest part of the image. Gold absorbs
        strongly; the carbon film's texture does not, so a faint blob the size
        of a small particle is film, not gold. Set to 0 to keep everything.
    """
    from scipy import ndimage as ndi
    from skimage.feature import peak_local_max
    from skimage.filters import gaussian, threshold_otsu
    from skimage.morphology import remove_small_objects
    from skimage.segmentation import watershed

    info: Dict[str, Any] = {}
    work = gaussian(image, sigma=smooth_sigma, preserve_range=True)
    threshold = float(threshold_otsu(work))
    if dark_particles is None:
        dark_fraction = float((work < threshold).mean())
        dark_particles = dark_fraction <= 0.5
        info["dark_particles_auto"] = True
        info["dark_area_fraction"] = dark_fraction
    mask = work < threshold if dark_particles else work > threshold
    info["threshold"] = threshold
    info["dark_particles"] = bool(dark_particles)

    mask = ndi.binary_fill_holes(mask)
    mask = remove_small_objects(mask, min_size=max(int(min_area_px), 1))
    if not mask.any():
        return np.zeros(image.shape, dtype=int), info

    distance = ndi.distance_transform_edt(mask)

    if split_touching:
        if min_distance_px is None:
            # The typical particle radius in pixels, read off the distance
            # transform: seeds closer than ~0.7 of it are two maxima inside
            # one particle, not two particles.
            radius = float(np.percentile(distance[mask], 95))
            min_distance_px = max(3, int(round(0.7 * radius)))
            info["min_distance_auto"] = True
        info["min_distance_px"] = int(min_distance_px)

        coordinates = peak_local_max(
            distance, min_distance=max(int(min_distance_px), 1), labels=mask)
        markers = np.zeros(distance.shape, dtype=int)
        for index, (row, column) in enumerate(coordinates, start=1):
            markers[row, column] = index
        labels = (watershed(-distance, markers, mask=mask)
                  if markers.max() else ndi.label(mask)[0])
    else:
        labels = ndi.label(mask)[0]

    if min_contrast_frac > 0:
        labels, n_faint = _drop_faint(image, labels, threshold, dark_particles,
                                      min_contrast_frac)
        info["n_rejected_contrast"] = n_faint

    return labels, info


def _consensus(per_image: List[Dict[str, Any]], key: str) -> Any:
    """The value *key* took on most frames, for reporting an auto-decision.

    Frames of one grid should all agree; if they do not, the one that wins is
    still the one most of the pooled particles came from.
    """
    values = [row.get(key) for row in per_image if row.get(key) is not None]
    if not values:
        return None
    return max(set(values), key=values.count)


def _drop_faint(image: np.ndarray, labels: np.ndarray, threshold: float,
                dark_particles: bool, min_contrast_frac: float,
                ) -> Tuple[np.ndarray, int]:
    """Zero out labels whose contrast against the support is too weak."""
    from scipy import ndimage as ndi

    n_labels = int(labels.max())
    if n_labels == 0:
        return labels, 0

    index = np.arange(1, n_labels + 1)
    means = np.asarray(ndi.mean(image, labels, index), dtype=float)

    if dark_particles:
        extreme = float(np.percentile(image, 1))
        depth = threshold - means
        full = threshold - extreme
    else:
        extreme = float(np.percentile(image, 99))
        depth = means - threshold
        full = extreme - threshold

    if full <= 0:
        return labels, 0

    faint = index[(depth / full) < min_contrast_frac]
    if faint.size == 0:
        return labels, 0

    remap = np.arange(n_labels + 1)
    remap[faint] = 0
    return remap[labels], int(faint.size)


def measure_particles(labels: np.ndarray, nm_per_pixel: Optional[float], *,
                      min_diameter: float = 0.0,
                      max_diameter: float = np.inf,
                      min_circularity: float = 0.0,
                      border_margin_px: int = 0) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Measure labelled particles, returning diameters and what was rejected.

    Diameters are equivalent-circle diameters. Particles touching the frame
    edge are excluded when *border_margin_px* is positive: a particle cut by
    the edge is measured smaller than it is, and keeping it biases the mean
    down.
    """
    from skimage.measure import regionprops

    scale = nm_per_pixel if nm_per_pixel else 1.0
    height, width = labels.shape

    diameters: List[float] = []
    rejected = {"edge": 0, "size": 0, "shape": 0}

    for region in regionprops(labels):
        if border_margin_px > 0:
            min_row, min_col, max_row, max_col = region.bbox
            if (min_row < border_margin_px or min_col < border_margin_px
                    or max_row > height - border_margin_px
                    or max_col > width - border_margin_px):
                rejected["edge"] += 1
                continue

        diameter = float(region.equivalent_diameter_area * scale)
        if not (min_diameter <= diameter <= max_diameter):
            rejected["size"] += 1
            continue

        if min_circularity > 0:
            perimeter = float(region.perimeter)
            if perimeter <= 0:
                rejected["shape"] += 1
                continue
            circularity = 4.0 * np.pi * float(region.area) / (perimeter ** 2)
            if circularity < min_circularity:
                rejected["shape"] += 1
                continue

        diameters.append(diameter)

    return np.asarray(diameters, dtype=float), rejected


# ---------------------------------------------------------------------------
# Analysis entry point
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Kernels: one image in, sizes out
# ---------------------------------------------------------------------------

def size_from_image(image: np.ndarray, nm_per_pixel: Optional[float] = None, *,
                    min_diameter: float = 2.0, max_diameter: float = 200.0,
                    min_circularity: float = 0.6,
                    border_margin_px: int = 2,
                    **segment_options) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Segment one image and measure its particles. **Kernel.**

    Returns ``(diameters, info)``. With *nm_per_pixel* the diameters are in
    nanometres and the size filters are applied in nanometres; without it they
    are in pixels and the nm limits are **not** applied, because filtering in
    the wrong units silently discards the wrong particles.

    >>> diameters, info = size_from_image(array, 0.4)      # doctest: +SKIP
    """
    calibrated = nm_per_pixel is not None
    if calibrated:
        low, high = min_diameter, max_diameter
        min_area = np.pi * (0.5 * low / nm_per_pixel) ** 2
    else:
        low, high = 0.0, np.inf
        min_area = 20.0

    labels, seg_info = segment_particles(
        image, min_area_px=int(max(min_area, 4)), **segment_options)
    diameters, rejected = measure_particles(
        labels, nm_per_pixel, min_diameter=low, max_diameter=high,
        min_circularity=min_circularity, border_margin_px=border_margin_px)

    info = dict(seg_info)
    info.update({"n_particles": int(diameters.size),
                 "calibrated": calibrated,
                 "nm_per_pixel": nm_per_pixel,
                 "rejected": rejected,
                 "labels": labels})
    return diameters, info


def size_statistics(diameters, unit: str = "nm") -> Dict[str, Any]:
    """Pooled numbers from a set of diameters. **Kernel.**

    Mean, standard deviation, median, the 10th and 90th percentiles, the
    coefficient of variation, and the count. The standard error of the mean
    comes back as ``d_mean_err``.

    An empty input returns an empty dict rather than a row of NaNs: no
    particles is the absence of a measurement, and reporting it as one makes
    the table lie.
    """
    values = np.asarray(diameters, dtype=float).ravel()
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {}

    spread = float(values.std(ddof=1)) if values.size > 1 else 0.0
    mean = float(values.mean())
    return {
        "d_mean": mean,
        "d_mean_err": (spread / np.sqrt(values.size)) if values.size > 1
                      else None,
        "d_std": spread,
        "d_median": float(np.median(values)),
        "d_p10": float(np.percentile(values, 10)),
        "d_p90": float(np.percentile(values, 90)),
        "d_cv": (spread / mean) if mean > 0 else float("nan"),
        "n_particles": int(values.size),
        "unit": unit,
    }


# ---------------------------------------------------------------------------
# Adapter: every frame of a measurement, pooled
# ---------------------------------------------------------------------------

def particle_sizing(measurement, resolver, *,
                    dark_particles: Optional[bool] = None,
                    nm_per_pixel: Optional[float] = None,
                    smooth_sigma: float = 1.0,
                    min_diameter_nm: float = 2.0,
                    max_diameter_nm: float = 200.0,
                    min_circularity: float = 0.6,
                    border_margin_px: int = 2,
                    min_distance_px: Optional[int] = None,
                    min_contrast_frac: float = 0.2,
                    split_touching: bool = True,
                    max_images: Optional[int] = None,
                    **_ignored) -> AnalysisResult:
    """Size distribution pooled over every micrograph of one measurement.

    All frames of a sample are pooled into one distribution rather than
    averaged per image: five fields of view of the same grid are five samples
    of one population, and averaging per-image means throws away how many
    particles each field contributed.

    The size filters are expressed in nanometres and only applied when the data
    is calibrated; on an uncalibrated image they would silently reject in the
    wrong units, so they are converted to pixels and reported as such.
    """
    result = AnalysisResult(
        analysis="particle_sizing",
        sample_id=measurement.sample_id,
        measurement_id=measurement.measurement_id,
    )

    paths = measurement.resolve(resolver)
    if not paths:
        return AnalysisResult.failure(
            "particle_sizing",
            f"No images resolve for {measurement.measurement_id}",
            sample_id=measurement.sample_id,
            measurement_id=measurement.measurement_id,
        )
    if max_images is not None:
        paths = paths[:max_images]

    try:
        import skimage  # noqa: F401
    except ImportError as exc:
        return AnalysisResult.failure(
            "particle_sizing",
            "particle sizing needs scikit-image: pip install scikit-image",
            sample_id=measurement.sample_id,
            measurement_id=measurement.measurement_id,
        )

    all_diameters: List[np.ndarray] = []
    per_image: List[Dict[str, Any]] = []
    scales: List[float] = []
    rejected_total = {"edge": 0, "size": 0, "shape": 0, "contrast": 0}
    problems: List[str] = []

    for path in paths:
        try:
            image, scale, info = read_micrograph(
                path, nm_per_pixel=nm_per_pixel)
        except Exception as exc:
            problems.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue

        calibrated = scale is not None
        if calibrated:
            scales.append(float(scale))

        diameters, seg_info = size_from_image(
            image, scale, min_diameter=min_diameter_nm,
            max_diameter=max_diameter_nm, min_circularity=min_circularity,
            border_margin_px=border_margin_px,
            dark_particles=dark_particles, smooth_sigma=smooth_sigma,
            split_touching=split_touching, min_distance_px=min_distance_px,
            min_contrast_frac=min_contrast_frac,
        )
        for key, value in seg_info["rejected"].items():
            rejected_total[key] += value
        rejected_total["contrast"] += seg_info.get("n_rejected_contrast", 0)

        all_diameters.append(diameters)
        per_image.append({
            "file": path.name,
            "n_particles": int(diameters.size),
            "nm_per_pixel": scale,
            "calibrated": calibrated,
            "fov_nm": float(image.shape[1] * scale) if calibrated else None,
            "mean_nm": float(diameters.mean()) if diameters.size else float("nan"),
            "shape": info.get("shape"),
            "banner_rows": info.get("banner_rows", 0),
            "min_distance_px": seg_info.get("min_distance_px"),
            "dark_particles": seg_info.get("dark_particles"),
        })

    if not all_diameters:
        return AnalysisResult.failure(
            "particle_sizing", "; ".join(problems) or "no images could be read",
            sample_id=measurement.sample_id,
            measurement_id=measurement.measurement_id,
        )

    pooled = np.concatenate(all_diameters) if all_diameters else np.array([])
    calibrated = bool(scales)
    unit = "nm" if calibrated else "px"

    statistics = size_statistics(pooled, unit=unit)
    if not statistics:
        result.ok = False
        result.message = (
            "no particles survived the filters; check the diameter range, "
            "and set dark_particles explicitly if the contrast was misread"
        )
    else:
        error = statistics.pop("d_mean_err", None)
        statistics.pop("unit", None)
        for name, value in statistics.items():
            result.set(name, value,
                       unit=unit if name.startswith("d_") and
                       name != "d_cv" else "",
                       error=error if name == "d_mean" else None)
        result.set("n_images", len(per_image))

    result.diagnostics.update({
        "calibrated": calibrated,
        "unit": unit,
        "nm_per_pixel_min": float(min(scales)) if scales else None,
        "nm_per_pixel_max": float(max(scales)) if scales else None,
        "magnification_spread": (float(max(scales) / min(scales))
                                 if scales and min(scales) > 0 else None),
        "dark_particles": (dark_particles if dark_particles is not None
                           else _consensus(per_image, "dark_particles")),
        "dark_particles_auto": dark_particles is None,
        "min_diameter_nm": min_diameter_nm,
        "max_diameter_nm": max_diameter_nm,
        "min_circularity": min_circularity,
        "min_contrast_frac": min_contrast_frac,
        "border_margin_px": border_margin_px,
        "split_touching": split_touching,
        "n_rejected_edge": rejected_total["edge"],
        "n_rejected_size": rejected_total["size"],
        "n_rejected_shape": rejected_total["shape"],
        "n_rejected_contrast": rejected_total["contrast"],
        "per_image": per_image,
    })
    result.curves["diameters"] = pooled

    notes: List[str] = []
    if not calibrated:
        notes.append("no pixel calibration found; diameters are in PIXELS. "
                     "Pass nm_per_pixel= to calibrate.")
    spread = result.diagnostics.get("magnification_spread")
    if spread is not None and spread > 2.0 and len(per_image) > 1:
        counts = [im["n_particles"] for im in per_image]
        dominant = max(counts) / max(sum(counts), 1)
        notes.append(
            f"magnifications differ by {spread:.1f}x across {len(per_image)} "
            f"images; the pooled distribution is {dominant:.0%} from the "
            f"widest field. Size one magnification at a time if that matters."
        )
    if result.message:
        notes.insert(0, result.message)
    notes.extend(problems)
    result.message = "; ".join(notes)
    return result


__all__ = [
    # kernels — arrays in
    "segment_particles", "measure_particles", "size_from_image",
    "size_statistics",
    # adapter — a measurement in
    "particle_sizing",
    # readers
    "read_micrograph", "pixel_size_nm",
]
