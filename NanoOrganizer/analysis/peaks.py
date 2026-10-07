#!/usr/bin/env python3
"""
Generic 1D peak fitting, for any curve modality.

One routine serves UV-Vis plasmon bands, Raman and IR bands, XPS lines, XRD
reflections and SAXS features, because at this level they are the same problem:
a baseline plus some peaks on a shared x axis. The modality only decides the
axis caption and sensible defaults, which the registry already knows.

Peak shapes are fitted with ``scipy.optimize.curve_fit`` — a constant baseline
plus *n* Gaussian, Lorentzian or pseudo-Voigt peaks. Initial guesses come from
the data (the *n* highest well-separated maxima), because a multi-peak fit
started at an arbitrary point converges to nonsense far more often than it
fails outright.

This module follows the kernel/adapter rule (``docs/kernel_adapter_rule.md``):

``fit_peaks(x, y, ...)``
    the **kernel** — arrays in, :class:`PeakFitResult` out.  No files, no
    project, no registry.  This is the one to call when a fit is misbehaving
    and you want to change one number and look again.

``peak_fit(measurement, resolver, ...)``
    the **adapter** — finds the curve, calls the kernel, labels the axes from
    the modality registry and packages the answer as an
    :class:`AnalysisResult`.  This is the one the analysis registry knows
    about and the one ``wb.batch("peak_fit")`` runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from NanoOrganizer.analysis.result import AnalysisResult
from NanoOrganizer.core import modality as _modality

SHAPES = ("gaussian", "lorentzian", "pseudo_voigt")

#: Background models, and how many parameters each costs.
BACKGROUNDS = ("constant", "linear")
_N_BACKGROUND = {"constant": 1, "linear": 2}


# ---------------------------------------------------------------------------
# Getting a curve out of a measurement
# ---------------------------------------------------------------------------

def load_curve(measurement, resolver, *, index: int = -1,
               reduce: str = "frame",
               crop: Optional[Tuple[float, float]] = None,
               ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Return ``(x, y, info)`` for one curve of *measurement*.

    A time series has to be collapsed to a single curve before it can be
    fitted. ``reduce`` says how:

    ``"frame"``
        One frame, selected by *index* (``-1`` is the last).
    ``"mean"``
        The mean of every frame — quieter, but only meaningful when the
        spectrum is not changing.
    ``"last_decile"``
        Mean of the final 10 % of frames. The usual endpoint choice: quieter
        than one frame, and not contaminated by the start of the run.

    For a non-series modality the first resolved file is read as a two-column
    curve (``.txt``, ``.csv``, ``.dat``, ``.npy``, ``.npz``).
    """
    spec = measurement.spec
    if spec is not None and spec.shape == "series":
        try:
            return _curve_from_series(measurement, resolver, index, reduce, crop)
        except (FileNotFoundError, ValueError, ImportError):
            # A modality that *can* be a time series is not always written as
            # one: a single ex-situ XAS scan or an averaged SAXS curve is one
            # two-column file with no clock in its name. Read it as a curve
            # rather than demanding a frame grammar that does not apply.
            pass
    return _curve_from_file(measurement, resolver, crop, index=index,
                            reduce=reduce)


def _curve_from_series(measurement, resolver, index, reduce, crop):
    from NanoOrganizer.analysis import frames as _frames

    series = _frames.load_series(measurement, resolver, kind=_frames.KINETIC,
                                 crop=crop)
    absorbance = np.asarray(series.absorbance, dtype=float)

    if reduce == "mean":
        y = absorbance.mean(axis=0)
        note = f"mean of {len(series)} frames"
    elif reduce == "last_decile":
        keep = max(1, int(round(0.1 * len(series))))
        y = absorbance[-keep:].mean(axis=0)
        note = f"mean of the last {keep} of {len(series)} frames"
    else:
        y = absorbance[index]
        note = f"frame {index} of {len(series)} (t = {series.t_s[index]:.0f} s)"

    return np.asarray(series.wavelength, dtype=float), y, {
        "source": note, "n_frames": int(len(series)),
    }


def _curve_from_file(measurement, resolver, crop, *, index: int = -1,
                     reduce: str = "frame"):
    """Read a curve from the files themselves, honouring *reduce*.

    A growth series is not always written as single-column frames on a shared
    axis; it is just as often a folder of two-column files, one per time
    point.  Those land here, and they are still a series: reading the first
    file and calling it the endpoint would answer a different question from
    the one that was asked — and the diagnostics would still say
    ``last_decile``, which is worse than being wrong loudly.
    """
    paths = measurement.resolve(resolver)
    if not paths:
        raise FileNotFoundError(
            f"No files resolve for {measurement.measurement_id}")

    if len(paths) > 1:
        stacked = _stack_two_column(paths)
        if stacked is not None:
            x, matrix = stacked
            y, note = _reduce_rows(matrix, index, reduce, len(paths))
            if crop is not None:
                keep = (x >= crop[0]) & (x <= crop[1])
                x, y = x[keep], y[keep]
            return x, y, {"source": note, "n_files": len(paths)}

    path = paths[0]
    suffix = path.suffix.lower()

    if suffix == ".npy":
        array = np.load(path)
        if array.ndim != 2 or 2 not in array.shape:
            raise ValueError(f"{path.name}: expected a two-column array, "
                             f"got shape {array.shape}")
        array = array if array.shape[1] == 2 else array.T
        x, y = array[:, 0], array[:, 1]
    elif suffix == ".npz":
        bundle = np.load(path)
        keys = list(bundle.keys())
        if len(keys) < 2:
            raise ValueError(f"{path.name}: need two arrays, found {keys}")
        x, y = bundle[keys[0]], bundle[keys[1]]
    else:
        from NanoOrganizer.analysis.reading import read_array

        array = read_array(path)
        if array.ndim != 2 or array.shape[1] < 2:
            raise ValueError(f"{path.name}: need at least two columns")
        x, y = array[:, 0], array[:, 1]

    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if crop is not None:
        keep = (x >= crop[0]) & (x <= crop[1])
        x, y = x[keep], y[keep]
    return x, y, {"source": path.name, "n_files": len(paths)}


# ---------------------------------------------------------------------------
# The fit
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Kernel: the fit itself, on arrays
# ---------------------------------------------------------------------------

@dataclass
class PeakFitResult:
    """Everything one peak fit computed.

    Returned by :func:`fit_peaks`.  It carries the model curve and the
    residual as well as the parameters, because a caller that has to recompute
    them to draw the fit will get the model subtly wrong sooner or later.

    Attributes
    ----------
    x, y : ndarray
        The data actually fitted, after any windowing and NaN removal.
    y_fit, residual : ndarray
        The model on *x*, and ``y - y_fit``.
    params, errors : dict
        ``{"baseline": ..., "peak1_center": ..., ...}`` and the matching 1σ
        uncertainties.  An undetermined parameter is absent from *errors*
        rather than present as zero.
    r2, rmse : float
        Goodness of fit.  Whether that is *good enough* is the caller's
        decision, not this function's.
    settings : dict
        What was actually used: shape, background, peak count, window, point
        count.
    popt, pcov : ndarray
        The raw ``curve_fit`` output, for anyone who wants the covariance.
    """

    x: np.ndarray
    y: np.ndarray
    y_fit: np.ndarray
    residual: np.ndarray
    params: Dict[str, float] = field(default_factory=dict)
    errors: Dict[str, float] = field(default_factory=dict)
    r2: float = float("nan")
    rmse: float = float("nan")
    settings: Dict[str, Any] = field(default_factory=dict)
    popt: Optional[np.ndarray] = None
    pcov: Optional[np.ndarray] = None

    @property
    def centers(self) -> List[float]:
        """Fitted peak positions, in x order."""
        return [self.params[k] for k in sorted(self.params)
                if k.endswith("_center")]

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        peaks = ", ".join(f"{c:.4g}" for c in self.centers)
        return (f"<PeakFitResult {self.settings.get('n_peaks', '?')} peak(s) "
                f"at [{peaks}], R² = {self.r2:.4f}>")


def fit_peaks(x, y, *, n_peaks: int = 1, shape: str = "gaussian",
              background: str = "constant",
              x_range: Optional[Tuple[float, float]] = None,
              initial_guess: Optional[Sequence[float]] = None,
              bounds: Optional[Dict[str, tuple]] = None,
              maxfev: int = 20000) -> PeakFitResult:
    """Fit *n_peaks* peaks plus a background to ``(x, y)``. **The kernel.**

    Takes two arrays and nothing else — no measurement, no resolver, no
    project — so it can be called on data from anywhere::

        x, Y, info = org.data("S01", "waxs1d")
        fit = fit_peaks(x, Y[0], n_peaks=2, x_range=(2.5, 3.6),
                        background="linear")
        fit.params["peak1_center"], fit.r2

    Parameters
    ----------
    x, y : array-like
        The curve.  Non-finite points are dropped.
    n_peaks : int
        How many components.  Initial positions come from the *n* highest
        well-separated maxima, because a multi-peak fit started at an
        arbitrary point converges to nonsense more often than it fails.
    shape : {"gaussian", "lorentzian", "pseudo_voigt"}
        The line shape.  ``width`` is the Gaussian σ (not the FWHM) for
        ``gaussian``, and the half-width at half-maximum for ``lorentzian``.
    background : {"constant", "linear"}
        A sloping background is the normal case away from UV-Vis — an XPS
        inelastic tail, a Raman fluorescence ramp, an interband edge under a
        plasmon — and fitting a flat one through it does not merely lower R²:
        it drags the peak centre towards the high side of the slope.  If a
        fitted position looks systematically off, this is the first thing to
        try.
    x_range : (float, float), optional
        Fit only this window.
    initial_guess : sequence, optional
        Raw parameter vector, in model order.  Omitted, it is estimated from
        the data.
    bounds : dict, optional
        Overrides for the automatic physical bounds, by parameter name.

    Returns
    -------
    PeakFitResult

    Raises
    ------
    ValueError
        For an unknown *shape* or *background*, or too few usable points to
        determine the parameters.  The kernel raises; the adapter is what
        turns a failure into a row in a results table.
    RuntimeError
        If the optimiser does not converge.
    """
    if shape not in SHAPES:
        raise ValueError(f"shape must be one of {SHAPES}, got {shape!r}")
    if background not in BACKGROUNDS:
        raise ValueError(
            f"background must be one of {BACKGROUNDS}, got {background!r}")
    if n_peaks < 1:
        raise ValueError(f"n_peaks must be at least 1, got {n_peaks}")

    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if x.shape != y.shape:
        raise ValueError(f"x and y must match: {x.shape} vs {y.shape}")

    if x_range is not None:
        keep = (x >= x_range[0]) & (x <= x_range[1])
        x, y = x[keep], y[keep]

    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]

    needed = 4 * n_peaks + 2
    if x.size < needed:
        raise ValueError(
            f"only {x.size} usable points for {n_peaks} peak(s); "
            f"{needed} are needed"
            + (f" — is the x_range {x_range} right for this axis?"
               if x_range is not None else ""))

    order = np.argsort(x)
    x, y = x[order], y[order]

    guess = list(initial_guess) if initial_guess is not None else \
        _initial_guess(x, y, n_peaks, background)
    lower, upper = _bounds(x, y, n_peaks, bounds, background)
    model = _peak_model(shape, n_peaks, background)

    try:
        from scipy.optimize import curve_fit

        popt, pcov = curve_fit(model, x, y, p0=guess, bounds=(lower, upper),
                               maxfev=maxfev)
    except Exception as exc:                        # noqa: BLE001
        raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc

    y_fit = model(x, *popt)
    residual = y - y_fit
    ss_res = float((residual ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    # curve_fit scales the covariance by the residual variance. A non-finite
    # entry means that parameter was not actually determined, so it is left
    # out rather than reported as zero.
    raw_errors = (np.sqrt(np.diag(pcov)) if pcov is not None
                  else np.full(len(popt), np.nan))

    params: Dict[str, float] = {}
    errors: Dict[str, float] = {}
    n_background = _N_BACKGROUND[background]

    def record(name: str, index: int) -> None:
        params[name] = float(popt[index])
        error = _as_error(raw_errors[index])
        if error is not None:
            errors[name] = error

    record("baseline", 0)
    if background == "linear":
        record("baseline_slope", 1)
    for peak in range(n_peaks):
        base = n_background + 3 * peak
        record(f"peak{peak + 1}_amplitude", base + 0)
        record(f"peak{peak + 1}_center", base + 1)
        record(f"peak{peak + 1}_width", base + 2)

    return PeakFitResult(
        x=x, y=y, y_fit=y_fit, residual=residual,
        params=params, errors=errors,
        r2=float(r2), rmse=float(np.sqrt(ss_res / x.size)),
        settings={"n_peaks": n_peaks, "shape": shape,
                  "background": background,
                  "x_range": (float(x[0]), float(x[-1])),
                  "n_points": int(x.size)},
        popt=popt, pcov=pcov,
    )


# ---------------------------------------------------------------------------
# Adapter: the same fit, found and filed
# ---------------------------------------------------------------------------

def peak_fit(measurement, resolver, *, n_peaks: int = 1,
             shape: str = "gaussian",
             background: str = "constant",
             x_range: Optional[Tuple[float, float]] = None,
             index: int = -1,
             reduce: str = "last_decile",
             crop: Optional[Tuple[float, float]] = None,
             initial_guess: Optional[Sequence[float]] = None,
             bounds: Optional[Dict[str, tuple]] = None,
             min_r2: float = 0.9,
             **_ignored) -> AnalysisResult:
    """Fit peaks to a measurement's curve. **The adapter over** :func:`fit_peaks`.

    Everything numerical happens in the kernel; this reads the curve, supplies
    the axis unit from the modality registry, applies the *min_r2* policy, and
    packages the answer as an :class:`AnalysisResult` so it reaches the
    results table.

    Derived values are named ``peak1_center``, ``peak1_amplitude``,
    ``peak1_width`` and so on, with the unit taken from the modality so a
    Raman shift never gets labelled in nanometres.

    ``index``, ``reduce`` and ``crop`` decide *which* curve is fitted when the
    measurement holds many frames — see :func:`load_curve`. They are the only
    arguments here that the kernel does not take, because they are about
    finding the data rather than fitting it.

    ``min_r2`` is a floor, not a target: a fit below it comes back with
    ``ok = False`` so the batch table shows it rather than quietly
    contributing a meaningless peak position. The kernel reports R² and takes
    no view on it.
    """
    def failure(message: str) -> AnalysisResult:
        return AnalysisResult.failure(
            "peak_fit", message,
            sample_id=measurement.sample_id,
            measurement_id=measurement.measurement_id,
        )

    try:
        x, y, info = load_curve(measurement, resolver, index=index,
                                reduce=reduce, crop=crop)
    except (FileNotFoundError, ValueError, ImportError) as exc:
        return failure(str(exc))

    try:
        fit = fit_peaks(x, y, n_peaks=n_peaks, shape=shape,
                        background=background, x_range=x_range,
                        initial_guess=initial_guess, bounds=bounds)
    except (ValueError, RuntimeError) as exc:
        return failure(str(exc))

    spec = measurement.spec
    unit = _axis_unit(spec)

    result = AnalysisResult(
        analysis="peak_fit",
        sample_id=measurement.sample_id,
        measurement_id=measurement.measurement_id,
    )
    for name, value in fit.params.items():
        result.set(name, value,
                   unit="" if name.endswith("_amplitude") else unit,
                   error=fit.errors.get(name))
    result.set("fit_r2", fit.r2)

    result.diagnostics.update(fit.settings)
    result.diagnostics.update({
        "modality": measurement.modality,
        "x_unit": unit,
        "x_label": spec.x_label if spec else "",
        "y_label": spec.y_label if spec else "",
        "curve_source": info.get("source", ""),
        "reduce": reduce,
        "rmse": fit.rmse,
    })
    result.curves.update({"x": fit.x, "y": fit.y, "y_fit": fit.y_fit,
                          "residual": fit.residual})

    if not np.isfinite(fit.r2) or fit.r2 < min_r2:
        result.ok = False
        result.message = (f"fit quality R\u00b2 = {fit.r2:.4g} is below the "
                          f"{min_r2} floor")
    return result


# ---------------------------------------------------------------------------
# Peak shapes, guesses and bounds
# ---------------------------------------------------------------------------

def _stack_two_column(paths):
    """Read two-column files onto one axis; None if they do not share one.

    Files are ordered as they resolve, which for a time series is the order
    their names sort in — the convention every rig that puts a clock in a
    filename already follows.
    """
    from NanoOrganizer.analysis.reading import read_array

    axis = None
    rows = []
    for path in paths:
        try:
            array = read_array(path)
        except (ValueError, OSError):
            return None
        if array.ndim != 2 or array.shape[1] < 2:
            return None
        x, y = array[:, 0], array[:, 1]
        if axis is None:
            axis = np.asarray(x, dtype=float)
        elif len(y) != len(axis):
            return None
        rows.append(np.asarray(y, dtype=float))

    if axis is None or not rows:
        return None
    return axis, np.vstack(rows)


def _reduce_rows(matrix, index: int, reduce: str, n_files: int):
    """Collapse stacked frames to one curve the way *reduce* asks."""
    if reduce == "mean":
        return matrix.mean(axis=0), f"mean of {n_files} files"
    if reduce == "last_decile":
        keep = max(1, int(round(0.1 * matrix.shape[0])))
        return (matrix[-keep:].mean(axis=0),
                f"mean of the last {keep} of {n_files} files")
    return matrix[index], f"file {index % matrix.shape[0]} of {n_files}"


def _profile(shape: str):
    """Return the unit-height line shape for *shape*."""
    if shape == "gaussian":
        return lambda x, mu, w: np.exp(-0.5 * ((x - mu) / w) ** 2)
    if shape == "lorentzian":
        return lambda x, mu, w: 1.0 / (1.0 + ((x - mu) / w) ** 2)
    # Pseudo-Voigt with a fixed 50/50 mix: the mixing fraction is poorly
    # determined from a single band and adding it as a free parameter mostly
    # buys correlated nonsense.
    def pseudo_voigt(x, mu, w):
        gauss = np.exp(-0.5 * ((x - mu) / w) ** 2)
        lorentz = 1.0 / (1.0 + ((x - mu) / w) ** 2)
        return 0.5 * gauss + 0.5 * lorentz
    return pseudo_voigt


def _peak_model(shape: str, n_peaks: int, background: str = "constant"):
    """``f(x, c[, slope], A1, mu1, w1, A2, mu2, w2, …)``."""
    profile = _profile(shape)
    n_background = _N_BACKGROUND[background]

    def model(x, *params):
        x = np.asarray(x, dtype=float)
        out = np.full_like(x, float(params[0]))
        if n_background == 2:
            out = out + float(params[1]) * (x - x[0])
        for peak in range(n_peaks):
            start = n_background + 3 * peak
            amplitude, centre, width = params[start: start + 3]
            out = out + amplitude * profile(x, centre, max(abs(width), 1e-12))
        return out

    return model


def _initial_guess(x: np.ndarray, y: np.ndarray, n_peaks: int,
                   background: str = "constant") -> List[float]:
    """Baseline plus the *n* strongest, well-separated maxima.

    Separation is enforced at a tenth of the axis span, so two peaks are not
    both started on the same bump — the commonest way a multi-peak fit ends up
    with two identical components and a meaningless width.
    """
    baseline = float(np.percentile(y, 5))
    span = float(x[-1] - x[0]) or 1.0
    minimum_gap = span / max(10.0, 2.0 * n_peaks)

    order = np.argsort(y)[::-1]
    chosen: List[int] = []
    for index in order:
        if all(abs(x[index] - x[other]) >= minimum_gap for other in chosen):
            chosen.append(int(index))
        if len(chosen) == n_peaks:
            break
    while len(chosen) < n_peaks:                     # degenerate, but finite
        chosen.append(int(order[len(chosen) % len(order)]))

    guess: List[float] = [baseline]
    if _N_BACKGROUND[background] == 2:
        # Slope from the two ends of the window, which is where the background
        # is least contaminated by the peak.
        edge = max(3, x.size // 20)
        rise = float(y[-edge:].mean() - y[:edge].mean())
        run = float(x[-edge:].mean() - x[:edge].mean()) or 1.0
        guess = [float(y[:edge].mean()), rise / run]
    for index in sorted(chosen, key=lambda i: x[i]):
        guess.extend([max(float(y[index]) - baseline, 1e-9),
                      float(x[index]), span / (4.0 * n_peaks)])
    return guess


def _bounds(x: np.ndarray, y: np.ndarray, n_peaks: int,
            override: Optional[Dict[str, tuple]],
            background: str = "constant"):
    """Physical bounds: peaks live inside the axis and have positive width."""
    span = float(x[-1] - x[0]) or 1.0
    height = float(np.nanmax(y) - np.nanmin(y)) or 1.0

    lower = [float(np.nanmin(y)) - height]
    upper = [float(np.nanmax(y)) + height]
    if _N_BACKGROUND[background] == 2:
        # A background steep enough to cross the whole data range twice over
        # the window is not a background any more.
        lower.append(-2.0 * height / span)
        upper.append(2.0 * height / span)
    for _ in range(n_peaks):
        lower.extend([0.0, float(x[0]), span * 1e-4])
        upper.extend([10.0 * height, float(x[-1]), span])

    if override:
        for name, (low, high) in override.items():
            if name == "baseline":
                lower[0], upper[0] = float(low), float(high)
    return lower, upper


def _axis_unit(spec) -> str:
    """Unit for a modality's x axis, parsed out of its label."""
    if spec is None:
        return ""
    label = spec.x_label
    if "(" in label and ")" in label:
        return label[label.rindex("(") + 1: label.rindex(")")]
    return {"wavelength": "nm", "wavenumber": "cm^-1", "energy": "eV",
            "q": "1/A", "two_theta": "deg", "size": "nm",
            "time": "s", "lag_time": "s"}.get(spec.domain, "")


def _as_error(value) -> Optional[float]:
    """A finite uncertainty, or None — never a fabricated zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


__all__ = [
    # kernel
    "fit_peaks", "PeakFitResult",
    # adapter
    "peak_fit", "load_curve",
    "SHAPES", "BACKGROUNDS",
]
