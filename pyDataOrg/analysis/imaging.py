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

Segmentation is deliberately classical: the background taken out, Otsu, then
a watershed to split particles that touch. Heavy-metal particles on a carbon
film are high-contrast once the film's own unevenness — holes, thicker
strands, illumination fall-off — is removed, which is the case classical
thresholding handles well and where a learned model would add a dependency
and an unaudited failure mode for nothing. Every length it needs is read off
the image, so one set of settings serves every magnification.

Kernels and adapter (``docs/kernel_adapter_rule.md``) — the functions on
arrays:

``particle_scale(image)``           typical particle radius, and polarity
``flatten_background(image, r)``    contrast against the local background
``segment_particles(image, ...)``   label map from one image
``measure_particles(labels, ...)``  diameters from one label map
``size_from_image(image, ...)``     the two above, in one call
``size_statistics(diameters)``      the pooled numbers
``particle_sizing_method(images, scales, ...)``
    the method: every frame sized, pooled, as an :class:`AnalysisResult`
``particle_sizing(measurement, resolver, ...)``
    the **adapter** — reads every frame and calls the method.
``segment_micrograph(measurement, resolver, ...)``
    the adapter for *checking* — one frame, segmented, returned as a
    :class:`Segmentation` for :func:`~pyDataOrg.viz.plots.plot_segmentation`
    to draw. Segmenting and drawing are two calls, not one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from pyDataOrg.analysis.result import AnalysisResult

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

#: The background disc, in particle radii: wide enough that a particle — and
#: two touching ones — fit inside it, narrow enough that a hole in the film,
#: or the film's edge, does not.
BACKGROUND_RADII = 2.5


def _shrink(image: np.ndarray, factor: float) -> np.ndarray:
    """*image* reduced *factor* times, averaged rather than sampled."""
    from skimage.transform import resize

    if factor <= 1.0:
        return np.asarray(image, dtype=float)
    shape = (max(1, round(image.shape[0] / factor)),
             max(1, round(image.shape[1] / factor)))
    return resize(image, shape, anti_aliasing=True, preserve_range=True)


def particle_scale(image: np.ndarray, *, working_size: int = 512,
                   ) -> Tuple[float, bool, Dict[str, Any]]:
    """The typical particle radius in pixels, and whether particles are dark.

    Returns ``(radius_px, dark, info)``. Read off a scale-normalised
    Laplacian of Gaussian: a disc of radius *r* answers it most strongly at
    σ = r/√2, a dark disc with one sign and a bright one with the other. The
    particles are the stronger of the two answers — film texture and holes
    in the film are blob-like too, but weakly.

    Computed on a copy shrunk to about *working_size* pixels, so a 4k frame
    costs what a small one does; if the answer is at the finest scale that
    copy can show, it is looked for again at full size.
    """
    from scipy import ndimage as ndi

    factor = max(1.0, max(image.shape) / float(working_size))
    sigmas = None
    while True:
        small = _shrink(image, factor)
        small = (small - small.mean()) / (small.std() or 1.0)
        if sigmas is None:
            sigmas = np.geomspace(1.0, max(1.5, min(small.shape) / 6.0), 24)
        dark = np.empty(sigmas.size)
        bright = np.empty(sigmas.size)
        for index, sigma in enumerate(sigmas):
            # σ²·LoG does not change when the image is shrunk, so a wide
            # scale is measured on a smaller copy, at σ = 4.
            step = max(1.0, sigma / 4.0)
            response = (sigma / step) ** 2 * ndi.gaussian_laplace(
                _shrink(small, step), sigma / step)
            dark[index] = np.percentile(response, 99.9)
            bright[index] = np.percentile(-response, 99.9)
        is_dark = bool(dark.max() >= bright.max())
        best = int(np.argmax(dark if is_dark else bright))
        if best > 0 or factor == 1.0:
            break
        # Finer than the shrunk copy shows: once more at full size, up to
        # the scale the shrunk copy started at.
        sigmas, factor = np.geomspace(1.0, 2.0 * factor, 8), 1.0

    radius = float(sigmas[best] * np.sqrt(2.0) * factor)
    return radius, is_dark, {
        "blob_radius_px": radius,
        "blob_strength_dark": float(dark.max()),
        "blob_strength_bright": float(bright.max()),
    }


def flatten_background(image: np.ndarray, radius_px: float, *,
                       dark_particles: bool = True) -> np.ndarray:
    """How much each pixel stands out from its surroundings; particles > 0.

    The background is a morphological closing of the image (an opening, for
    bright particles) with a disc of *radius_px*: anything narrower than the
    disc — a particle — is lifted out of it, anything wider — the film, a
    hole in it, uneven illumination — stays, steps included, so the edge of
    a hole is not mistaken for a particle. **Kernel.**

    Dark particles are seen in transmission: a particle passes a *fraction*
    of what reaches it, so the same particle on a thicker, darker patch of
    film is darker by less. Their contrast is therefore relative,
    ``(background − image) / background`` — the fraction of the light the
    particle stops. Bright particles (SEM, dark field) add signal, so theirs
    is ``image − background``. A particle is positive either way. Computed on
    a copy shrunk until the disc is ~15 px wide, and brought back to size.
    """
    from scipy import ndimage as ndi
    from skimage.morphology import disk
    from skimage.transform import resize

    image = np.asarray(image, dtype=float)
    factor = max(1.0, float(radius_px) / 15.0)
    small = _shrink(image, factor)
    footprint = disk(max(1, int(round(radius_px / factor))))
    background = (ndi.grey_closing(small, footprint=footprint)
                  if dark_particles
                  else ndi.grey_opening(small, footprint=footprint))
    background = ndi.gaussian_filter(background, 1.0)
    if background.shape != image.shape:
        background = resize(background, image.shape, order=1,
                            preserve_range=True)
    if not dark_particles:
        return image - background
    # Measured from zero signal; an image with negative values (a processed
    # float frame) is measured from its own minimum instead.
    floor = min(0.0, float(image.min()))
    spread = float(np.ptp(image)) or 1.0
    return (background - image) / np.maximum(background - floor,
                                             1e-6 * spread)


def _blob_response(contrast: np.ndarray, sigma: float) -> np.ndarray:
    """The blob detector's answer at scale *sigma*: highest at a particle's
    centre, lowest in the neck between two that touch."""
    from scipy import ndimage as ndi
    from skimage.transform import resize

    sigma = max(float(sigma), 1.0)
    factor = max(1.0, sigma / 4.0)
    small = _shrink(contrast, factor)
    response = -ndi.gaussian_laplace(small, sigma / factor)
    if response.shape != contrast.shape:
        response = resize(response, contrast.shape, order=1,
                          preserve_range=True)
    return response


def segment_particles(image: np.ndarray, *,
                      dark_particles: Optional[bool] = None,
                      smooth_sigma: float = 1.0,
                      min_area_px: int = 20,
                      split_touching: bool = True,
                      min_distance_px: Optional[int] = None,
                      min_contrast_frac: float = 0.2,
                      background_px: Optional[float] = None,
                      ) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Label particles in a micrograph; return ``(labels, info)``.

    The background is taken out first (:func:`flatten_background`), then
    Otsu splits what stands out from what does not, and a watershed
    separates particles that touch, seeded where each particle is both
    furthest from its edge and darkest. Every scale it needs is read off the
    image itself (:func:`particle_scale`, then the regions found): these
    grids are imaged anywhere from 0.07 to 0.4 nm per pixel, and a fixed
    number of pixels that suits one magnification is wrong at another.

    Parameters
    ----------
    dark_particles : bool, optional
        True for TEM, where metal absorbs and particles are darker than the
        support; False for SEM, where they are usually brighter. Left as None
        the polarity is read off the image: particles answer a blob detector
        more strongly than film texture or a hole in the film does. Getting
        this backwards segments the *support*, which is the single most
        common way a sizing run produces confident nonsense, so it is worth
        not having to remember.
    background_px : float, optional
        Radius of the disc the background is estimated with. Features
        narrower than it are particles, wider ones background. Left as None
        it is ``BACKGROUND_RADII`` particle radii; 0 switches flattening off
        (one threshold for the whole frame, which is right only when the
        illumination and the film are even).
    split_touching : bool
        Separate touching particles (watershed). Overlapping ones are
        separated when each still has a darker centre; a pile that has none
        stays merged and is usually caught by the shape filter afterwards.
    min_distance_px : int, optional
        Minimum separation between watershed seeds. Left as None it is 0.7
        of the particle radius read off the image.
    min_contrast_frac : float
        Reject regions whose contrast is less than this fraction of the way
        from the threshold to that of the strongest particles. A metal
        particle absorbs strongly; the carbon film's texture does not, so a
        faint blob the size of a small particle is film, not metal. Set to 0
        to keep everything.
    """
    from scipy import ndimage as ndi
    from skimage.feature import peak_local_max
    from skimage.filters import gaussian, threshold_otsu
    from skimage.morphology import remove_small_holes, remove_small_objects
    from skimage.segmentation import watershed

    info: Dict[str, Any] = {}
    image = np.asarray(image, dtype=float)
    work = gaussian(image, sigma=smooth_sigma, preserve_range=True)
    radius, looks_dark, scale_info = particle_scale(work)
    info.update(scale_info)
    if dark_particles is None:
        dark_particles = looks_dark
        info["dark_particles_auto"] = True
    info["dark_particles"] = bool(dark_particles)

    # At high magnification a pixel is a fraction of a nanometre and the
    # film's grain is many pixels wide; smoothed less than ~1/15 of a
    # radius, every particle's edge comes out ragged.
    edge_sigma = max(float(smooth_sigma), radius / 15.0)
    if edge_sigma > smooth_sigma:
        work = gaussian(image, sigma=edge_sigma, preserve_range=True)
    info["smooth_sigma_px"] = edge_sigma

    if background_px is None:
        background_px = BACKGROUND_RADII * radius
        info["background_auto"] = True
    info["background_px"] = float(background_px)
    if background_px > 0:
        contrast = flatten_background(work, background_px,
                                      dark_particles=dark_particles)
    else:
        contrast = -work if dark_particles else work

    threshold = float(threshold_otsu(contrast))
    info["threshold"] = threshold
    mask = contrast > threshold

    # A particle's own holes (a bright twin boundary) are filled; the gap a
    # ring of touching particles encloses is not — filled, the ring would be
    # one particle.
    mask = remove_small_holes(mask, area_threshold=max(
        int(0.2 * np.pi * radius ** 2), 1))
    mask = remove_small_objects(mask, min_size=max(int(min_area_px), 1))
    if not mask.any():
        return np.zeros(image.shape, dtype=int), info

    regions, n_regions = ndi.label(mask)
    distance = ndi.distance_transform_edt(mask)
    # The blob detector answers clusters too, so its radius can only be too
    # big; so can the typical region's inscribed radius when one cluster
    # dominates the frame. The smaller of the two is the particle.
    inscribed = ndi.maximum(distance, regions, np.arange(1, n_regions + 1))
    radius = min(radius, float(np.median(inscribed)))
    info["particle_radius_px"] = radius

    if split_touching:
        if min_distance_px is None:
            # Seeds closer than ~0.7 of a radius are two maxima inside one
            # particle, not two particles.
            min_distance_px = max(3, int(round(0.7 * radius)))
            info["min_distance_auto"] = True
        info["min_distance_px"] = int(min_distance_px)

        # A particle's centre is both the furthest point from its edge and,
        # being thickest, its darkest: seeds where the sum of the two peaks
        # find the two of a pair that overlap as well as the two that merely
        # touch. Flooded on the same surface, they part at the neck.
        response = _blob_response(contrast, radius / np.sqrt(2.0))
        strongest = float(np.percentile(response[mask], 99))
        surface = distance / max(radius, 1.0)
        if strongest > 0:
            surface = surface + response / strongest
        coordinates = peak_local_max(
            surface, min_distance=max(int(min_distance_px), 1),
            labels=regions, exclude_border=False)
        markers = np.zeros(mask.shape, dtype=int)
        for index, (row, column) in enumerate(coordinates, start=1):
            markers[row, column] = index
        labels = watershed(-surface, markers, mask=mask)
        # A region with no seed in it is still one particle.
        unseeded = mask & (labels == 0)
        if unseeded.any():
            extra, _ = ndi.label(unseeded)
            labels = np.where(unseeded, extra + labels.max(), labels)
    else:
        labels = regions

    if min_contrast_frac > 0:
        labels, n_faint = _drop_faint(contrast, labels, threshold,
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


def _drop_faint(contrast: np.ndarray, labels: np.ndarray, threshold: float,
                min_contrast_frac: float) -> Tuple[np.ndarray, int]:
    """Zero out labels whose contrast is too weak: less than
    *min_contrast_frac* of the way from *threshold* to the strongest
    particles' (the 95th percentile inside the labels)."""
    from scipy import ndimage as ndi

    n_labels = int(labels.max())
    if n_labels == 0:
        return labels, 0

    index = np.arange(1, n_labels + 1)
    means = np.asarray(ndi.mean(contrast, labels, index), dtype=float)
    full = float(np.percentile(contrast[labels > 0], 95)) - threshold
    if full <= 0:
        return labels, 0

    weak = (means - threshold) / full < min_contrast_frac
    if not weak.any():
        return labels, 0

    # The rest renumbered 1…n, so the largest label is still the count.
    remap = np.zeros(n_labels + 1, dtype=labels.dtype)
    remap[index[~weak]] = np.arange(1, int((~weak).sum()) + 1)
    return remap[labels], int(weak.sum())


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
# Adapter: one frame, segmented, for looking at
# ---------------------------------------------------------------------------

@dataclass
class Segmentation:
    """One micrograph and the label map segmentation made of it.

    What :func:`segment_micrograph` returns and
    :func:`~pyDataOrg.viz.plots.plot_segmentation` draws. ``labels`` has
    the shape of ``image``; 0 is background, 1…n are particles.
    """

    image: np.ndarray
    labels: np.ndarray
    nm_per_pixel: Optional[float] = None
    file: str = ""
    info: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_particles(self) -> int:
        return int(self.labels.max()) if self.labels.size else 0

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        scale = (f"{self.nm_per_pixel:.3f} nm/px" if self.nm_per_pixel
                 else "uncalibrated")
        return (f"<Segmentation {self.file or 'image'}: {self.n_particles} "
                f"particles, {self.image.shape[1]}×{self.image.shape[0]} px, "
                f"{scale}>")


def segment_micrograph(measurement, resolver, *, image_index: int = 0,
                       nm_per_pixel: Optional[float] = None,
                       min_diameter_nm: float = 2.0,
                       **segment_options) -> Segmentation:
    """Read one frame of a micrograph measurement and segment it. **Adapter.**

    The look-before-you-trust step: :func:`particle_sizing` pools every frame
    into a histogram, and a histogram looks plausible whether the outlines
    were right or not. This returns the label map for one frame so it can be
    drawn — by :func:`~pyDataOrg.viz.plots.plot_segmentation`, which is a
    separate call on purpose.

    *min_diameter_nm* becomes the smallest kept area in pixels when the frame
    is calibrated; uncalibrated, a 20-pixel floor is used instead.
    """
    paths = measurement.resolve(resolver)
    if not paths:
        raise FileNotFoundError(f"no images for {measurement.measurement_id}")

    path = paths[image_index]
    image, scale, read_info = read_micrograph(path, nm_per_pixel=nm_per_pixel)
    min_area = np.pi * (0.5 * min_diameter_nm / scale) ** 2 if scale else 20.0
    labels, info = segment_particles(
        image, min_area_px=int(max(min_area, 4)), **segment_options)
    info = {**read_info, **info, "image_index": image_index}
    return Segmentation(image=image, labels=labels, nm_per_pixel=scale,
                        file=Path(path).name, info=info)


# ---------------------------------------------------------------------------
# Every frame of a sample, pooled: the method on arrays, then its adapter
# ---------------------------------------------------------------------------

def particle_sizing_method(images, scales=None, names=None, *,
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
                           background_px: Optional[float] = None,
                           max_images: Optional[int] = None,
                           ) -> AnalysisResult:
    """Size distribution pooled over a sample's micrographs. **Kernel.**

    *images* are the frames as 2D arrays, banners already cropped (what
    :func:`read_micrograph` gives, or ``org.data(sample, "tem",
    lazy=True).load()``); *scales* the nm per pixel each file records (None
    for one that records none); *names* what to call each frame in the
    per-image table. *nm_per_pixel* overrides every scale.

    All frames are pooled into one distribution rather than averaged per
    image: five fields of view of the same grid are five samples of one
    population, and averaging per-image means throws away how many particles
    each field contributed.

    The size filters are in nanometres and only applied to calibrated
    frames; on an uncalibrated one they would silently reject in the wrong
    units, so its diameters stay in pixels and say so.
    """
    images = list(images)[:max_images]
    if scales is None:
        scales = [None] * len(images)
    if names is None:
        names = [f"image {index}" for index in range(len(images))]
    result = AnalysisResult(analysis="particle_sizing")
    if not images:
        return AnalysisResult.failure("particle_sizing", "no images to size")

    all_diameters: List[np.ndarray] = []
    per_image: List[Dict[str, Any]] = []
    calibrations: List[float] = []
    rejected_total = {"edge": 0, "size": 0, "shape": 0, "contrast": 0}

    for image, recorded, name in zip(images, scales, names):
        image = np.asarray(image, dtype=float)
        scale = nm_per_pixel if nm_per_pixel is not None else recorded
        calibrated = scale is not None
        if calibrated:
            calibrations.append(float(scale))

        diameters, seg_info = size_from_image(
            image, scale, min_diameter=min_diameter_nm,
            max_diameter=max_diameter_nm, min_circularity=min_circularity,
            border_margin_px=border_margin_px,
            dark_particles=dark_particles, smooth_sigma=smooth_sigma,
            split_touching=split_touching, min_distance_px=min_distance_px,
            min_contrast_frac=min_contrast_frac, background_px=background_px,
        )
        for key, value in seg_info["rejected"].items():
            rejected_total[key] += value
        rejected_total["contrast"] += seg_info.get("n_rejected_contrast", 0)

        all_diameters.append(diameters)
        per_image.append({
            "file": str(name),
            "n_particles": int(diameters.size),
            "nm_per_pixel": scale,
            "calibrated": calibrated,
            "fov_nm": float(image.shape[1] * scale) if calibrated else None,
            "mean_nm": float(diameters.mean()) if diameters.size else float("nan"),
            "shape": image.shape,
            "min_distance_px": seg_info.get("min_distance_px"),
            "background_px": seg_info.get("background_px"),
            "dark_particles": seg_info.get("dark_particles"),
        })

    pooled = np.concatenate(all_diameters)
    calibrated = bool(calibrations)
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
        "nm_per_pixel_min": float(min(calibrations)) if calibrations else None,
        "nm_per_pixel_max": float(max(calibrations)) if calibrations else None,
        "magnification_spread": (float(max(calibrations) / min(calibrations))
                                 if calibrations and min(calibrations) > 0
                                 else None),
        "dark_particles": (dark_particles if dark_particles is not None
                           else _consensus(per_image, "dark_particles")),
        "dark_particles_auto": dark_particles is None,
        "min_diameter_nm": min_diameter_nm,
        "max_diameter_nm": max_diameter_nm,
        "min_circularity": min_circularity,
        "min_contrast_frac": min_contrast_frac,
        "border_margin_px": border_margin_px,
        "split_touching": split_touching,
        "background_px": background_px,
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
    result.message = "; ".join(notes)
    return result


def particle_sizing(measurement, resolver, **settings) -> AnalysisResult:
    """Every micrograph of one measurement, read and sized.

    **Adapter** over :func:`particle_sizing_method`: it reads the frames —
    banner cropped, the calibration each file records — and files the
    answer; the settings are the method's.
    """
    def failure(message: str) -> AnalysisResult:
        return AnalysisResult.failure(
            "particle_sizing", message, sample_id=measurement.sample_id,
            measurement_id=measurement.measurement_id)

    paths = measurement.resolve(resolver)
    if not paths:
        return failure(f"No images resolve for {measurement.measurement_id}")
    paths = paths[:settings.get("max_images")]

    try:
        import skimage  # noqa: F401
    except ImportError:
        return failure("particle sizing needs scikit-image: "
                       "pip install scikit-image")

    images, scales, names, banners, problems = [], [], [], [], []
    for path in paths:
        try:
            image, scale, info = read_micrograph(path)
        except Exception as exc:
            problems.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        images.append(image)
        scales.append(scale)
        names.append(path.name)
        banners.append(info.get("banner_rows", 0))
    if not images:
        return failure("; ".join(problems) or "no images could be read")

    result = particle_sizing_method(images, scales, names, **settings)
    result.sample_id = measurement.sample_id
    result.measurement_id = measurement.measurement_id
    for row, banner in zip(result.diagnostics.get("per_image", []), banners):
        row["banner_rows"] = banner
    if problems:
        result.message = "; ".join(filter(None, [result.message, *problems]))
    return result


__all__ = [
    # kernels — arrays in
    "particle_scale", "flatten_background", "segment_particles",
    "measure_particles", "size_from_image", "size_statistics",
    "particle_sizing_method",
    # adapters — a measurement in
    "particle_sizing", "segment_micrograph", "Segmentation",
    # readers
    "read_micrograph", "pixel_size_nm",
]
