#!/usr/bin/env python3
"""
Curve metrics – the handful of numbers worth having from any 1D measurement.

Peak fitting answers "where is the band and how wide is it".  A great deal of
routine analysis does not need a model at all, only a window and a question:

* how big is the signal in this range, and where is its maximum?
* what is the area under it, and where is its centre of mass?
* at what x does it cross this value?

That last one is the same operation as *the potential at 10 mA cm⁻²*, *the
onset of an absorption edge*, and *the lag time at which a correlation
function has half decayed*.  Writing it once, technique-independently, is the
whole argument for a modality registry: the question is about the shape of a
curve, not about which instrument drew it.

The analysis is registered for every ``curve`` modality, so it applies to
UV-Vis, Raman, IR, XPS, XAS, EDS, scattering, electrochemistry, DLS and a DFT
density of states alike.

Kernel/adapter pair (``docs/kernel_adapter_rule.md``):

``measure_curve(x, y, ...)``
    the **kernel** — arrays in, :class:`CurveMetrics` out.
``curve_metrics(measurement, resolver, ...)``
    the **adapter** — finds the curve, calls the kernel, labels and files it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

from NanoOrganizer.analysis.result import AnalysisResult



# ---------------------------------------------------------------------------
# Kernel: the metrics, on arrays
# ---------------------------------------------------------------------------

@dataclass
class CurveMetrics:
    """What :func:`measure_curve` found in a window.

    Attributes
    ----------
    values : dict
        ``y_max``, ``x_at_max``, ``y_at_max_raw``, ``y_min``, ``area``,
        ``x_centroid``, ``y_mean``, and ``x_at_threshold`` when a threshold
        was asked for and reached.
    x, y, baseline, corrected : ndarray
        The windowed curve, the baseline taken off it, and the difference.
    settings : dict
        Window, point count, whether a baseline was subtracted, and how many
        times the threshold was crossed.
    note : str
        A warning worth surfacing — an unreached threshold, several crossings
        — or empty. Not an error: the other metrics are still good.
    """

    values: Dict[str, float] = field(default_factory=dict)
    x: Optional[np.ndarray] = None
    y: Optional[np.ndarray] = None
    baseline: Optional[np.ndarray] = None
    corrected: Optional[np.ndarray] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        shown = ", ".join(f"{k}={v:.4g}" for k, v in
                          list(self.values.items())[:3])
        return f"<CurveMetrics {shown}>"


def measure_curve(x, y, *, x_min: Optional[float] = None,
                  x_max: Optional[float] = None,
                  threshold: Optional[float] = None,
                  subtract_baseline: bool = True) -> CurveMetrics:
    """Summarise ``(x, y)`` in a window, without fitting a model. **Kernel.**

    Takes two arrays and nothing else::

        x, Y, info = org.data("S01", "ec_lsv")
        metrics = measure_curve(x, Y[0], x_min=-1.2, x_max=-0.4,
                                threshold=-10.0)
        metrics.values["x_at_threshold"]      # the potential at 10 mA/cm2

    Parameters
    ----------
    x_min, x_max : float, optional
        The window. Left as None the whole curve is used, which is almost
        never what you want for a real spectrum — the point of the window is
        to say which feature you mean.
    threshold : float, optional
        Report the first x at which the curve crosses this y value. This is
        the overpotential-at-a-current measurement and the edge-onset
        measurement, depending on what the curve is.
    subtract_baseline : bool
        Take a straight line through the ends of the window off first. Area
        and centroid are relative to it; the maximum is reported both ways,
        because "how tall above background" and "what is the reading there"
        are different questions.

    Raises
    ------
    ValueError
        If fewer than three points survive the window.
    """
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if x.shape != y.shape:
        raise ValueError(f"x and y must match: {x.shape} vs {y.shape}")

    order = np.argsort(x)
    x, y = x[order], y[order]
    finite = np.isfinite(x) & np.isfinite(y)
    x, y = x[finite], y[finite]

    x, y = _window(x, y, x_min, x_max)
    if x.size < 3:
        raise ValueError(
            f"only {x.size} points in the window [{x_min}, {x_max}] — "
            f"nothing to summarise")

    baseline = _linear_baseline(x, y) if subtract_baseline else np.zeros_like(y)
    corrected = y - baseline

    peak = int(np.argmax(corrected))
    trough = int(np.argmin(corrected))
    area = float(np.trapezoid(corrected, x)) if hasattr(np, "trapezoid") \
        else float(np.trapz(corrected, x))

    # Centroid over the positive part only: negative lobes of a baseline-
    # subtracted curve would otherwise drag the centre of mass outside the
    # feature entirely.
    weights = np.clip(corrected, 0.0, None)
    total = float(weights.sum())
    centroid = float((x * weights).sum() / total) if total > 0 else float("nan")

    metrics = CurveMetrics(
        values={
            "y_max": float(corrected[peak]),
            "x_at_max": float(x[peak]),
            "y_at_max_raw": float(y[peak]),
            "y_min": float(corrected[trough]),
            "area": area,
            "x_centroid": centroid,
            "y_mean": float(y.mean()),
        },
        x=x, y=y, baseline=baseline, corrected=corrected,
        settings={
            "window": (float(x[0]), float(x[-1])),
            "n_points": int(x.size),
            "baseline_subtracted": bool(subtract_baseline),
        },
    )

    if threshold is not None:
        crossing, n_crossings = _first_crossing(x, y, float(threshold))
        metrics.settings["n_crossings"] = n_crossings
        if crossing is None:
            metrics.note = (
                f"the curve never reaches y = {threshold:g} in this window "
                f"(it spans {y.min():.4g} to {y.max():.4g})")
        else:
            metrics.values["x_at_threshold"] = crossing
            if n_crossings > 1:
                metrics.note = (
                    f"{n_crossings} crossings of y = {threshold:g}; the first "
                    f"is reported — narrow the window if that is the wrong one")
    return metrics


# ---------------------------------------------------------------------------
# Adapter: the same metrics, found and filed
# ---------------------------------------------------------------------------

def _window(x: np.ndarray, y: np.ndarray,
            x_min: Optional[float], x_max: Optional[float]
            ) -> Tuple[np.ndarray, np.ndarray]:
    keep = np.ones(x.size, dtype=bool)
    if x_min is not None:
        keep &= x >= x_min
    if x_max is not None:
        keep &= x <= x_max
    return x[keep], y[keep]


def _linear_baseline(x: np.ndarray, y: np.ndarray, edge: int = 5) -> np.ndarray:
    """A straight line through the mean of each end of the window.

    Not a background model — a way of asking "how much signal is there *above
    the ends of this window*", which is what an area or a centroid usually
    means in practice.  The ends are averaged over a few points so one noisy
    sample cannot tilt it.
    """
    if x.size < 2 * edge:
        return np.zeros_like(y)
    x0, x1 = x[:edge].mean(), x[-edge:].mean()
    y0, y1 = y[:edge].mean(), y[-edge:].mean()
    if x1 == x0:
        return np.full_like(y, y0)
    slope = (y1 - y0) / (x1 - x0)
    return y0 + slope * (x - x0)


def _first_crossing(x: np.ndarray, y: np.ndarray, level: float
                    ) -> Tuple[Optional[float], int]:
    """First x at which *y* crosses *level*, linearly interpolated.

    Returns ``(x, n_crossings)``.  The direction is taken from the data rather
    than assumed, so a cathodic current sweeping negative and an absorbance
    rising through a threshold are handled by the same code.
    """
    offset = y - level
    sign_change = np.signbit(offset[:-1]) != np.signbit(offset[1:])
    indices = np.flatnonzero(sign_change)
    if indices.size == 0:
        return None, 0

    i = int(indices[0])
    y0, y1 = offset[i], offset[i + 1]
    if y1 == y0:
        return float(x[i]), int(indices.size)
    fraction = y0 / (y0 - y1)
    return float(x[i] + fraction * (x[i + 1] - x[i])), int(indices.size)


def curve_metrics(measurement, resolver, *,
                  x_min: Optional[float] = None,
                  x_max: Optional[float] = None,
                  threshold: Optional[float] = None,
                  subtract_baseline: bool = True,
                  reduce: str = "last_decile",
                  index: int = -1,
                  ) -> AnalysisResult:
    """Summarise a measurement's curve. **Adapter over** :func:`measure_curve`.

    Reads the curve (``reduce`` and ``index`` decide which frame, when there
    are several), calls the kernel, takes the axis caption from the modality
    registry, and packages the answer as an :class:`AnalysisResult`.

    Returns values ``y_max``, ``x_at_max``, ``y_min``, ``area``,
    ``x_centroid``, ``y_mean`` and, when a threshold was given and reached,
    ``x_at_threshold``.
    """
    from NanoOrganizer.analysis.peaks import load_curve

    key = "curve_metrics"
    common = {"sample_id": measurement.sample_id,
              "measurement_id": measurement.measurement_id}

    try:
        x, y, info = load_curve(measurement, resolver, reduce=reduce,
                                index=index)
    except Exception as exc:                        # noqa: BLE001
        return AnalysisResult.failure(key, f"{type(exc).__name__}: {exc}",
                                      **common)

    try:
        metrics = measure_curve(x, y, x_min=x_min, x_max=x_max,
                                threshold=threshold,
                                subtract_baseline=subtract_baseline)
    except ValueError as exc:
        return AnalysisResult.failure(key, str(exc), **common)

    spec = measurement.spec
    unit = spec.x_label if spec is not None and spec.x_label else ""
    on_x = {"x_at_max", "x_centroid", "x_at_threshold"}

    result = AnalysisResult(analysis=key, **common)
    for name, value in metrics.values.items():
        result.set(name, value, unit=unit if name in on_x else "")

    result.diagnostics = dict(metrics.settings)
    result.diagnostics["source"] = info.get("source", "")
    result.message = metrics.note
    result.curves = {"x": metrics.x, "y": metrics.y,
                     "baseline": metrics.baseline,
                     "corrected": metrics.corrected}
    return result


__all__ = [
    "measure_curve", "CurveMetrics",   # kernel
    "curve_metrics",                   # adapter
]
