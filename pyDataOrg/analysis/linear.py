#!/usr/bin/env python3
"""
Finding the straight part of a curve, and fitting it honestly.

A pseudo-first-order rate constant is the slope of ``ln(A/A0)`` against time —
but only over the stretch where that plot is actually straight.  Fitting the
whole trace folds the induction period and the plateau into the slope and
reports a rate constant that is neither.

The detector here deliberately does **not** assume the reaction finishes.  A
run stopped at 40 % conversion has no plateau, and a method that brackets the
fit between "left the baseline" and "reached the plateau" returns nothing at
all for it.  Instead the active region is bracketed by where the *local slope*
is a meaningful fraction of its own maximum, which degrades gracefully to "the
tail of the data" when the reaction is still going.

Every function reports the window it used.  A slope without its window is not
a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np


@dataclass
class LinearFit:
    """A straight-line fit over a named window of the data."""

    slope: float
    intercept: float
    slope_err: float
    r2: float
    n: int
    i0: int
    i1: int
    t0: float
    t1: float
    note: str = ""

    @property
    def window_s(self) -> Tuple[float, float]:
        return (self.t0, self.t1)

    def predict(self, t) -> np.ndarray:
        return self.slope * np.asarray(t, dtype=float) + self.intercept

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slope": self.slope, "intercept": self.intercept,
            "slope_err": self.slope_err, "r2": self.r2, "n": self.n,
            "fit_window_s": (self.t0, self.t1), "note": self.note,
        }


def linear_fit(t, y, i0: int = 0, i1: Optional[int] = None,
               note: str = "") -> LinearFit:
    """Ordinary least squares on ``y[i0:i1]`` against ``t[i0:i1]``.

    ``slope_err`` is the standard error of the slope, which needs at least
    three points; with two it is reported as NaN rather than zero, because a
    line through two points has no residual and pretending otherwise invents
    a precision that is not there.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    i1 = len(t) if i1 is None else i1

    ts, ys = t[i0:i1], y[i0:i1]
    good = np.isfinite(ts) & np.isfinite(ys)
    ts, ys = ts[good], ys[good]
    n = ts.size
    if n < 2:
        return LinearFit(np.nan, np.nan, np.nan, np.nan, n, i0, i1,
                         float(t[i0]) if t.size else np.nan,
                         float(t[min(i1, len(t)) - 1]) if t.size else np.nan,
                         note or "fewer than two finite points")

    t_mean, y_mean = ts.mean(), ys.mean()
    dt = ts - t_mean
    ss_tt = float((dt * dt).sum())
    if ss_tt <= 0:
        return LinearFit(np.nan, np.nan, np.nan, np.nan, n, i0, i1,
                         float(ts[0]), float(ts[-1]), note or "zero time span")

    slope = float((dt * (ys - y_mean)).sum() / ss_tt)
    intercept = float(y_mean - slope * t_mean)

    residual = ys - (slope * ts + intercept)
    ss_res = float((residual * residual).sum())
    ss_tot = float(((ys - y_mean) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

    if n > 2:
        slope_err = float(np.sqrt(ss_res / (n - 2) / ss_tt))
    else:
        slope_err = float("nan")

    return LinearFit(slope, intercept, slope_err, r2, n, i0, i1,
                     float(ts[0]), float(ts[-1]), note)


def _smooth(y: np.ndarray, window: int) -> np.ndarray:
    """Light Savitzky-Golay smoothing, falling back to a moving average."""
    if window < 5 or y.size < window:
        return y
    if window % 2 == 0:
        window += 1
    try:
        from scipy.signal import savgol_filter
        return savgol_filter(y, window, 2)
    except ImportError:  # pragma: no cover - scipy is a hard dependency
        kernel = np.ones(window) / window
        return np.convolve(y, kernel, mode="same")


def _longest_true_run(flags: np.ndarray) -> Tuple[int, int]:
    """Return ``(start, stop)`` of the longest contiguous True run."""
    best = (0, 0)
    start = None
    for index, value in enumerate(flags):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if index - start > best[1] - best[0]:
                best = (start, index)
            start = None
    if start is not None and len(flags) - start > best[1] - best[0]:
        best = (start, len(flags))
    return best


def _best_window(t: np.ndarray, y: np.ndarray, lo: int, hi: int,
                 min_points: int, min_r2: float) -> Optional[Tuple[int, int]]:
    """Longest sub-window of ``[lo, hi)`` whose linear fit reaches *min_r2*.

    Uses prefix sums so each candidate window costs O(1); the search is then
    O(n²) in the bracket, which is nothing for the few hundred frames a run
    produces.  Longest-wins rather than best-R² — a short window can always
    reach a higher R² by fitting less of the curve, and that is not a better
    measurement of the rate.
    """
    ts, ys = t[lo:hi], y[lo:hi]
    n = ts.size
    if n < min_points:
        return None

    # Prefix sums, padded so sums over [i, j) are differences of entries.
    def prefix(values: np.ndarray) -> np.ndarray:
        return np.concatenate(([0.0], np.cumsum(values)))

    s_t, s_y = prefix(ts), prefix(ys)
    s_tt, s_yy, s_ty = prefix(ts * ts), prefix(ys * ys), prefix(ts * ys)

    for length in range(n, min_points - 1, -1):
        for i in range(0, n - length + 1):
            j = i + length
            count = float(length)
            sum_t, sum_y = s_t[j] - s_t[i], s_y[j] - s_y[i]
            sum_tt = s_tt[j] - s_tt[i]
            sum_yy = s_yy[j] - s_yy[i]
            sum_ty = s_ty[j] - s_ty[i]

            ss_tt = sum_tt - sum_t * sum_t / count
            ss_yy = sum_yy - sum_y * sum_y / count
            ss_ty = sum_ty - sum_t * sum_y / count
            if ss_tt <= 0 or ss_yy <= 0:
                continue
            r2 = (ss_ty * ss_ty) / (ss_tt * ss_yy)
            if r2 >= min_r2:
                return (lo + i, lo + j)
    return None


def linear_region(t, y, *, min_points: int = 8, min_r2: float = 0.98,
                  slope_frac: float = 0.2, smooth_points: int = 9,
                  ) -> LinearFit:
    """Find and fit the straight stretch of ``y(t)``.

    Parameters
    ----------
    min_points : int
        Refuse to call fewer points a measurement.
    min_r2 : float
        Target quality.  If the slope-bracketed window already reaches it, that
        window is used; otherwise the longest sub-window that does is searched
        for.  If nothing reaches it, the bracket is fitted anyway and the
        shortfall is recorded in ``note`` — the caller decides, rather than
        getting a silent NaN.
    slope_frac : float
        A point is "active" when its local slope is at least this fraction of
        the largest local slope.  0.2 keeps the body of the transition and
        drops the flat induction and plateau.
    smooth_points : int
        Window for the Savitzky-Golay pass used *only* to locate the region.
        The fit itself always runs on the unsmoothed data, so smoothing cannot
        bias the slope.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)

    good = np.isfinite(t) & np.isfinite(y)
    if good.sum() < min_points:
        return linear_fit(t, y, 0, len(t),
                          note=f"only {int(good.sum())} finite points")

    smoothed = _smooth(np.where(good, y, np.nan), smooth_points)
    with np.errstate(invalid="ignore"):
        slope_local = np.gradient(smoothed, t)
    magnitude = np.abs(slope_local)
    peak = np.nanmax(magnitude)

    if not np.isfinite(peak) or peak <= 0:
        return linear_fit(t, y, 0, len(t), note="curve is flat")

    active = magnitude >= slope_frac * peak
    lo, hi = _longest_true_run(active)
    if hi - lo < min_points:
        lo, hi = 0, len(t)
        bracket_note = "slope bracket too short; using the full trace"
    else:
        bracket_note = ""

    fit = linear_fit(t, y, lo, hi, note=bracket_note)
    if np.isfinite(fit.r2) and fit.r2 >= min_r2:
        return fit

    window = _best_window(t, y, lo, hi, min_points, min_r2)
    if window is not None:
        return linear_fit(t, y, window[0], window[1],
                          note="narrowed to reach the R² target")

    fit.note = (bracket_note + "; " if bracket_note else "") + (
        f"no window of {min_points}+ points reaches R²={min_r2}"
    )
    return fit


__all__ = ["LinearFit", "linear_fit", "linear_region"]
