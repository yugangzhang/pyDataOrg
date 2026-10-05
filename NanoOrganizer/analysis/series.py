#!/usr/bin/env python3
"""
FrameSeries — n frames measured over time on one shared axis.

This is the in-memory shape of a time-resolved 1D measurement, whatever the
technique: absorbance against wavelength over a reaction, intensity against q
over an anneal, counts against energy over a dose. The axis is called ``x`` and
the data ``values``, because the class has no business knowing which.

``wavelength`` and ``absorbance`` exist as aliases, since spectroscopy code
reads far better with them and a great deal of such code is already written
that way.

Slicing returns new instances rather than mutating, so an analysis cannot
quietly narrow the series its caller still holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np


def _per_frame(value: Any, n: int) -> bool:
    """True if *value* looks like one entry per frame, and so must be sliced."""
    return (isinstance(value, (list, tuple, np.ndarray))
            and len(value) == n and not isinstance(value, str))


@dataclass
class FrameSeries:
    """``n_frames`` measurements on a shared x axis.

    Attributes
    ----------
    x : (n_x,) float array
        The shared axis — wavelength, q, energy, lag time. Ascending.
    values : (n_frames, n_x) float array
        The measured quantity.
    t_s : (n_frames,) float array
        Seconds on whatever clock ``t_zero`` names.
    t_zero : str
        What ``t_s == 0`` means. ``load_series`` sets ``"file"``.
    names : tuple of str
        Per-frame source filenames, if known.
    T_c : (n_frames,) float array or None
        Per-frame temperature, when the filenames carried one.
    meta : dict
        Free-form. Per-frame entries are sliced along with the frames.
    """

    x: np.ndarray
    values: np.ndarray
    t_s: np.ndarray
    t_zero: str = "file"
    names: Tuple[str, ...] = ()
    T_c: Optional[np.ndarray] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.x = np.asarray(self.x, dtype=float)
        self.values = np.atleast_2d(np.asarray(self.values, dtype=float))
        self.t_s = np.asarray(self.t_s, dtype=float)
        if self.values.shape != (self.t_s.size, self.x.size):
            raise ValueError(
                f"values {self.values.shape} does not match "
                f"({self.t_s.size} frames, {self.x.size} axis points)"
            )

    # -- spectroscopy-friendly aliases ----------------------------------

    @property
    def wavelength(self) -> np.ndarray:
        """Alias for :attr:`x`."""
        return self.x

    @property
    def absorbance(self) -> np.ndarray:
        """Alias for :attr:`values`."""
        return self.values

    # -- basics ---------------------------------------------------------

    def __len__(self) -> int:
        return int(self.t_s.size)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (f"<FrameSeries {len(self)} frames x {self.x.size} points, "
                f"x={self.x[0]:.4g}..{self.x[-1]:.4g}, "
                f"t={self.t_s[0]:.0f}..{self.t_s[-1]:.0f} s from {self.t_zero}>")

    @property
    def t_min(self) -> np.ndarray:
        """The time axis in minutes."""
        return self.t_s / 60.0

    @property
    def cadence_s(self) -> float:
        """Median spacing of the time axis — the cadence actually delivered.

        Not the requested one: an unattended run gives up frames, and this
        reports what arrived.
        """
        if len(self) < 2:
            return float("nan")
        return float(np.median(np.diff(self.t_s)))

    # -- slicing --------------------------------------------------------

    def crop(self, lo: float, hi: float) -> "FrameSeries":
        """Restrict the x axis to ``[lo, hi]``."""
        keep = (self.x >= lo) & (self.x <= hi)
        if not keep.any():
            raise ValueError(f"no axis points in [{lo}, {hi}]")
        return replace(self, x=self.x[keep], values=self.values[:, keep])

    def select(self, mask: Sequence[bool]) -> "FrameSeries":
        """Keep the frames where *mask* is true, preserving order."""
        mask = np.asarray(mask, dtype=bool)
        if mask.size != len(self):
            raise ValueError(
                f"mask has {mask.size} entries, series has {len(self)} frames")

        n = len(self)
        out = replace(
            self,
            values=self.values[mask],
            t_s=self.t_s[mask],
            names=tuple(name for name, keep in zip(self.names, mask) if keep)
            if self.names else (),
            T_c=None if self.T_c is None else np.asarray(self.T_c)[mask],
        )
        # Per-frame metadata has to be cut the same way or it silently goes out
        # of step with the frames it describes.
        out.meta = {
            key: (np.asarray(value)[mask] if _per_frame(value, n) else value)
            for key, value in self.meta.items()
        }
        return out

    def between(self, t_lo: float, t_hi: float) -> "FrameSeries":
        """Keep frames with ``t_lo <= t_s <= t_hi``."""
        return self.select((self.t_s >= t_lo) & (self.t_s <= t_hi))

    def with_values(self, values: np.ndarray, **meta) -> "FrameSeries":
        """Same axes, new data — how a correction returns its result."""
        out = replace(self, values=np.asarray(values, dtype=float))
        out.meta = {**self.meta, **meta}
        return out

    # -- lookups --------------------------------------------------------

    def index_of(self, x: float) -> int:
        """Index of the axis point nearest *x*."""
        return int(np.argmin(np.abs(self.x - float(x))))

    def index_at(self, t: float) -> int:
        """Index of the frame nearest time *t*."""
        return int(np.argmin(np.abs(self.t_s - float(t))))

    def trace(self, x: float, width: float = 4.0) -> np.ndarray:
        """Value against time, averaged over ``x ± width/2``.

        Averaging a narrow band rather than taking one pixel: a single detector
        pixel is noisy, and the band is usually flat across a few units.
        """
        band = np.abs(self.x - float(x)) <= float(width) / 2.0
        if not band.any():
            band = np.zeros(self.x.size, dtype=bool)
            band[self.index_of(x)] = True
        return self.values[:, band].mean(axis=1)

    def frame_at(self, t: float) -> np.ndarray:
        """The single frame nearest time *t*."""
        return self.values[self.index_at(t)]

    def mean_between(self, t_lo: float, t_hi: float) -> np.ndarray:
        """Average frame over a time window.

        The usual way to take an endpoint without trusting one frame, which may
        have caught a bubble or the start of a wash.
        """
        keep = (self.t_s >= t_lo) & (self.t_s <= t_hi)
        if not keep.any():
            return self.frame_at(t_hi)
        return self.values[keep].mean(axis=0)


__all__ = ["FrameSeries"]
