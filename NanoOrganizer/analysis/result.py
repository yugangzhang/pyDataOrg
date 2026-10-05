#!/usr/bin/env python3
"""
AnalysisResult – what every analysis returns, and how it reaches the table.

An analysis produces three different kinds of thing and they must not be
confused:

``values``
    Scalars worth filtering and plotting against synthesis parameters — a rate
    constant, a peak position, a mean diameter.  These are written back onto
    the sample as :class:`~NanoOrganizer.core.schema.DerivedValue` records and
    become ``derived.*`` columns.

``curves``
    Arrays the caller may want to plot — the fitted line, the residuals, the
    extracted A(t) trace.  Never written to the sample store; a store that
    accumulates arrays stops being readable.

``diagnostics``
    Everything needed to judge whether ``values`` can be trusted: the fit
    window, R², how many points survived, what was excluded and why.

Keeping them apart is what stops a results table from quietly mixing a
well-determined rate constant with one fitted to four noisy points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class AnalysisResult:
    """The outcome of one analysis on one measurement.

    Attributes
    ----------
    analysis : str
        Registry key of the analysis that produced this.
    sample_id, measurement_id : str
        What it was computed from.
    values : dict
        ``{name: scalar}`` – the derived quantities.
    errors : dict
        ``{name: uncertainty}`` for any entry in ``values``.
    units : dict
        ``{name: unit string}``.
    curves : dict
        ``{name: ndarray}`` – for plotting, not for storage.
    diagnostics : dict
        Provenance and quality: fit window, R², counts, settings used.
    ok : bool
        False when the analysis could not produce trustworthy values.
    message : str
        Why it failed, or a warning worth surfacing when it did not.
    """

    analysis: str
    sample_id: str = ""
    measurement_id: str = ""
    values: Dict[str, Any] = field(default_factory=dict)
    errors: Dict[str, float] = field(default_factory=dict)
    units: Dict[str, str] = field(default_factory=dict)
    curves: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    message: str = ""

    # ------------------------------------------------------------------

    @classmethod
    def failure(cls, analysis: str, message: str, **kwargs) -> "AnalysisResult":
        """A result that carries no values, only the reason there are none."""
        return cls(analysis=analysis, ok=False, message=message, **kwargs)

    def set(self, name: str, value: Any, unit: str = "",
            error: Optional[float] = None) -> "AnalysisResult":
        """Record one derived value, with its unit and uncertainty."""
        self.values[name] = value
        if unit:
            self.units[name] = unit
        if error is not None:
            self.errors[name] = error
        return self

    # ------------------------------------------------------------------

    def write_to(self, sample, prefix: str = "") -> List[str]:
        """Store ``values`` on *sample* as derived records.

        Returns the derived names written.  Non-finite values are skipped: a
        NaN rate constant is the absence of a measurement, and storing it as
        one makes the table lie.
        """
        written: List[str] = []
        if not self.ok:
            return written

        for name, value in self.values.items():
            if isinstance(value, float) and not np.isfinite(value):
                continue
            key = f"{prefix}{name}" if prefix else name
            sample.set_derived(
                key, value,
                unit=self.units.get(name, ""),
                error=self.errors.get(name),
                analysis=self.analysis,
                source=self.measurement_id,
                params=dict(self.diagnostics),
            )
            written.append(key)
        return written

    def to_row(self) -> Dict[str, Any]:
        """Flat dict for a results table: values, errors, and key diagnostics."""
        row: Dict[str, Any] = {
            "sample_id": self.sample_id,
            "measurement_id": self.measurement_id,
            "analysis": self.analysis,
            "ok": self.ok,
        }
        row.update(self.values)
        row.update({f"{k}_err": v for k, v in self.errors.items()})
        for key, value in self.diagnostics.items():
            if isinstance(value, (int, float, str, bool, type(None))):
                row[key] = value
            elif isinstance(value, tuple) and len(value) == 2:
                row[f"{key}_lo"], row[f"{key}_hi"] = value
        if self.message:
            row["message"] = self.message
        return row

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        if not self.ok:
            return f"<AnalysisResult {self.analysis} FAILED: {self.message}>"
        shown = ", ".join(
            f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}"
            for k, v in list(self.values.items())[:3]
        )
        return f"<AnalysisResult {self.analysis} {self.sample_id}: {shown}>"


__all__ = ["AnalysisResult"]
