#!/usr/bin/env python3
"""
Small-angle scattering of spheres: the polydisperse form factor, and fitting it.

A dilute suspension of compact particles scatters as their form factor: a
plateau at low q, a knee near q ≈ 1/R, then the oscillations of a sphere's
edge, smeared by the spread of radii. Fitting that curve gives the radius and
its spread from the whole ensemble the beam passes through — not the few
hundred particles a micrograph counts.

Kernels only: arrays in, numbers out (``docs/kernel_adapter_rule.md``). No
unit is assumed: a radius comes back in the inverse unit of ``q`` (Å for q
in 1/Å).

=================================  ==========================================
``sphere_amplitude(x)``            F(x) = 3 (sin x − x cos x) / x³
``sphere_intensity(q, R, s)``      ⟨V² F²(qR)⟩ / ⟨V²⟩ over Gaussian radii of
                                   mean *R* and relative spread *s*; 1 at q = 0
``fit_spheres(q, y, background)``  *R* and *s*, with the measured background
                                   scaled in and a low-q power law (aggregates)
=================================  ==========================================

The fit runs on the logarithm of the intensity, binned evenly in log q, so
each decade of q counts alike and the steep low-q end does not outweigh the
oscillations that pin the radius down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

#: How far out the Gaussian of radii is integrated, in standard deviations.
_TAILS = 3.5


def sphere_amplitude(x) -> np.ndarray:
    """The scattering amplitude of a uniform sphere, ``3 (sin x − x cos x) / x³``
    with ``x = qR``; 1 at ``x = 0``."""
    x = np.asarray(x, dtype=float)
    small = np.abs(x) < 1e-3
    safe = np.where(small, 1.0, x)
    out = 3.0 * (np.sin(safe) - safe * np.cos(safe)) / safe ** 3
    return np.where(small, 1.0 - x ** 2 / 10.0, out)


def sphere_intensity(q, radius: float, rel_sigma: float = 0.0, *,
                     n_points: int = 41) -> np.ndarray:
    """The form factor of spheres whose radii are Gaussian (number-weighted)
    with mean *radius* and standard deviation ``rel_sigma × radius``, cut at
    zero: ``Σ n V² F²(qR) / Σ n V²``, so 1 at q = 0. *radius* is in the
    inverse unit of *q*."""
    q = np.asarray(q, dtype=float)
    if radius <= 0:
        raise ValueError(f"radius must be positive, got {radius}")
    if rel_sigma <= 0:
        return sphere_amplitude(q * radius) ** 2
    lo = max(radius * (1.0 - _TAILS * rel_sigma), radius * 1e-3)
    radii = np.linspace(lo, radius * (1.0 + _TAILS * rel_sigma), int(n_points))
    weight = np.exp(-0.5 * ((radii - radius) / (rel_sigma * radius)) ** 2) * radii ** 6
    f2 = sphere_amplitude(np.outer(q, radii)) ** 2
    return f2 @ weight / weight.sum()


# ---------------------------------------------------------------------------
# The fit
# ---------------------------------------------------------------------------

@dataclass
class SphereFit:
    """What :func:`fit_spheres` found.

    ``model = scale · sphere_intensity(q, radius, rel_sigma)
    + power_amplitude · (q / q[0])^−power_exponent
    + background_scale · background + constant``, on the binned ``q`` the fit
    ran on. ``rms`` is the root-mean-square of the log residual — a relative
    misfit (0.02 ≈ 2 %). ``power_share`` is the power law's part of the
    sample's intensity (spheres + power law) at the window's low end;
    ``contrast`` the most the sample scatters over its background, as a
    multiple of it (NaN with no background).
    """

    radius: float
    radius_err: float
    rel_sigma: float
    rel_sigma_err: float
    scale: float
    background_scale: float
    power_amplitude: float
    power_exponent: float
    constant: float
    rms: float
    power_share: float
    contrast: float
    q: np.ndarray = field(repr=False)
    y: np.ndarray = field(repr=False)
    model: np.ndarray = field(repr=False)
    spheres: np.ndarray = field(repr=False)
    power: np.ndarray = field(repr=False)
    background: np.ndarray = field(repr=False)
    at_bound: Tuple[str, ...] = ()
    notes: List[str] = field(default_factory=list)

    @property
    def diameter(self) -> float:
        return 2.0 * self.radius

    @property
    def diameter_err(self) -> float:
        return 2.0 * self.radius_err


def _binned(q: np.ndarray, y: np.ndarray, b: Optional[np.ndarray], n_bins: int):
    """The points in *n_bins* bins even in log q, each bin's median; bins with
    no point are dropped. Fewer points than bins are kept as they are."""
    if len(q) <= n_bins:
        return q, y, b
    edges = np.geomspace(q[0], q[-1] * (1 + 1e-9), n_bins + 1)
    which = np.digitize(q, edges) - 1
    keep = [i for i in range(n_bins) if np.any(which == i)]
    qq = np.array([np.exp(np.mean(np.log(q[which == i]))) for i in keep])
    yy = np.array([np.median(y[which == i]) for i in keep])
    bb = None if b is None else np.array([np.median(b[which == i]) for i in keep])
    return qq, yy, bb


def fit_spheres(q, y, background=None, *,
                q_min: Optional[float] = None, q_max: Optional[float] = None,
                radius_bounds: Tuple[float, float] = (5.0, 1000.0),
                max_rel_sigma: float = 0.5,
                power_law: bool = True,
                background_bounds: Tuple[float, float] = (0.7, 1.3),
                constant: bool = False,
                n_starts: int = 8, radius_start: Optional[float] = None,
                n_bins: int = 160, n_points: int = 41) -> SphereFit:
    """Fit polydisperse spheres to the curve ``(q, y)``.

    Parameters
    ----------
    background : array, optional
        The measured background on the same *q* (the solvent, the empty
        cell). Its scale is fitted inside *background_bounds* — the sample
        holds a little less solvent and absorbs a little more; pass
        ``(1, 1)`` to take it as measured. None: no background term (pass
        ``constant=True`` for a flat one).
    q_min, q_max
        The window fitted (default: all of *q*).
    radius_bounds, max_rel_sigma
        Where the radius (inverse unit of *q*) and its relative spread may
        go. A result at a bound is named in ``at_bound`` and in ``notes``.
    power_law
        Add ``A (q/q_min)^−p`` (1 ≤ p ≤ 4.5): the low-q rise of aggregates
        or larger particles, which would otherwise pull the radius up.
    n_starts
        Radii, spread evenly in log over *radius_bounds*, the fit starts
        from; the best is kept. A sphere's form factor has a minimum at
        every multiple of its size, so one start can stall in the wrong one.
        *radius_start* starts from that radius alone — for a curve like one
        already fitted (another spot of the same sample).

    Raises ``ValueError`` when the window holds too few usable points.
    """
    from scipy.optimize import least_squares

    q, y = np.asarray(q, dtype=float), np.asarray(y, dtype=float)
    b = None if background is None else np.asarray(background, dtype=float)
    if b is not None and b.shape != q.shape:
        raise ValueError(f"background has {b.shape[0]} points, q {q.shape[0]}")
    lo = q_min if q_min is not None else np.nanmin(q)
    hi = q_max if q_max is not None else np.nanmax(q)
    usable = (q >= lo) & (q <= hi) & np.isfinite(y) & (y > 0) & (q > 0)
    if b is not None:
        usable &= np.isfinite(b) & (b >= 0)
    order = np.argsort(q[usable])
    qq, yy = q[usable][order], y[usable][order]
    bb = None if b is None else b[usable][order]
    qq, yy, bb = _binned(qq, yy, bb, n_bins)
    if len(qq) < 12:
        raise ValueError(f"only {len(qq)} usable points in q {lo:g}–{hi:g}")

    fit_bg = bb is not None and background_bounds[0] < background_bounds[1]
    names = ["scale", "radius", "rel_sigma"]
    if power_law:
        names += ["power_amplitude", "power_exponent"]
    if fit_bg:
        names += ["background_scale"]
    if constant:
        names += ["constant"]
    log_y = np.log(yy)

    def unpack(p):
        values = dict(zip(names, p))
        values.setdefault("power_amplitude", 0.0)
        values.setdefault("power_exponent", 0.0)
        values.setdefault("background_scale",
                          background_bounds[0] if bb is not None else 0.0)
        values.setdefault("constant", 0.0)
        return values

    def parts(p):
        v = unpack(p)
        spheres = v["scale"] * sphere_intensity(qq, v["radius"], v["rel_sigma"],
                                                n_points=n_points)
        power = (v["power_amplitude"] * (qq / qq[0]) ** -v["power_exponent"]
                 if power_law else np.zeros_like(qq))
        back = (v["background_scale"] * bb if bb is not None
                else np.zeros_like(qq)) + v["constant"]
        return spheres, power, back

    def residual(p):
        return np.log(np.clip(sum(parts(p)), 1e-300, None)) - log_y

    # Starting values from the data: what is left over the background at the
    # low end is the spheres' (and aggregates') forward scattering.
    excess = yy - (bb if bb is not None else 0.0)
    head = max(float(np.median(excess[:5])), 1e-12 * float(np.max(yy)))
    tail = float(np.median(yy[-5:]))
    lower = {"scale": 0.0, "radius": radius_bounds[0], "rel_sigma": 0.01,
             "power_amplitude": 0.0, "power_exponent": 1.0,
             "background_scale": background_bounds[0], "constant": -abs(tail)}
    upper = {"scale": np.inf, "radius": radius_bounds[1],
             "rel_sigma": max_rel_sigma, "power_amplitude": np.inf,
             "power_exponent": 4.5, "background_scale": background_bounds[1],
             "constant": abs(tail)}
    best = None
    starts = ([float(np.clip(radius_start, *radius_bounds))] if radius_start
              else np.geomspace(*radius_bounds, int(n_starts) + 2)[1:-1])
    for radius in starts:
        start = {"scale": head, "radius": radius, "rel_sigma": 0.15,
                 "power_amplitude": 0.05 * head, "power_exponent": 3.0,
                 "background_scale": float(np.clip(1.0, *background_bounds)),
                 "constant": 0.0}
        x0 = [start[n] for n in names]
        found = least_squares(residual, x0, x_scale="jac",
                              bounds=([lower[n] for n in names],
                                      [upper[n] for n in names]))
        if best is None or found.cost < best.cost:
            best = found

    values = unpack(best.x)
    spheres, power, back = parts(best.x)
    n, k = len(qq), len(names)
    errors = dict.fromkeys(names, np.nan)
    try:
        jac = best.jac
        cov = np.linalg.pinv(jac.T @ jac) * (2.0 * best.cost / max(n - k, 1))
        errors = dict(zip(names, np.sqrt(np.clip(np.diag(cov), 0.0, None))))
    except np.linalg.LinAlgError:          # pragma: no cover - degenerate
        pass

    at_bound = tuple(
        name for name, value in zip(names, best.x)
        if name in ("radius", "rel_sigma", "background_scale", "power_exponent")
        and (np.isclose(value, lower[name], rtol=1e-3)
             or np.isclose(value, upper[name], rtol=1e-3)))
    sample = spheres + power
    power_share = float(power[0] / sample[0]) if sample[0] > 0 else float("nan")
    contrast = (float(np.max(sample / np.where(back > 0, back, np.inf)))
                if np.any(back > 0) else float("nan"))
    notes = []
    if "rel_sigma" in at_bound and np.isclose(values["rel_sigma"], max_rel_sigma,
                                              rtol=1e-3):
        notes.append(f"the spread of radii is at its bound ({values['rel_sigma']:.2f}): "
                     "one population of spheres does not describe this curve")
    if "radius" in at_bound:
        notes.append(f"the radius is at its bound ({values['radius']:.4g})")
    if "background_scale" in at_bound:
        notes.append(f"the background scale is at its bound "
                     f"({values['background_scale']:.2f})")
    if bb is not None and contrast < 1.0:
        notes.append(f"the sample scatters at most {contrast:.2f}× its background")
    return SphereFit(
        radius=float(values["radius"]), radius_err=float(errors["radius"]),
        rel_sigma=float(values["rel_sigma"]),
        rel_sigma_err=float(errors["rel_sigma"]),
        scale=float(values["scale"]),
        background_scale=float(values["background_scale"]),
        power_amplitude=float(values["power_amplitude"]),
        power_exponent=float(values["power_exponent"]),
        constant=float(values["constant"]),
        rms=float(np.sqrt(np.mean(best.fun ** 2))), power_share=power_share,
        contrast=contrast, q=qq, y=yy, model=spheres + power + back,
        spheres=spheres, power=power, background=back, at_bound=at_bound,
        notes=notes)


__all__ = ["sphere_amplitude", "sphere_intensity", "SphereFit", "fit_spheres"]
