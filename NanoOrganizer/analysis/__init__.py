#!/usr/bin/env python3
"""
Analysis registry – run an analysis over one measurement, or a whole basket.

Three general analyses ship here: 1D peak fitting, model-free curve metrics,
and particle sizing from micrographs. Technique- or chemistry-specific
analyses belong in a package of their own and register themselves on import,
which is why this is a registry rather than a fixed list.

An analysis is a callable ``f(measurement, resolver, **options) -> AnalysisResult``
declared with the modalities and stages it applies to.  The registry is what
lets both the notebook and the GUI offer "what can I run on this?" without
either of them hard-coding a list.

:func:`batch` is the loop that matters in practice: filter the project to a set
of samples, run one analysis over every matching measurement, write the scalars
back as derived values, and return a table of what happened — including the
rows that failed and why.  A batch that silently skips its failures is worse
than no batch at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from NanoOrganizer.analysis.result import AnalysisResult


@dataclass
class Analysis:
    """One registered analysis and what it applies to."""

    key: str
    func: Callable[..., AnalysisResult]
    label: str = ""
    modalities: Tuple[str, ...] = ()     # empty = any
    stages: Tuple[str, ...] = ()         # empty = any
    groups: Tuple[str, ...] = ()         # empty = any
    description: str = ""
    prefix: str = ""                     # prepended to derived names
    results_of: Tuple[str, ...] = ()     # runs on these analyses' stored results
    kernel: Optional[Callable[..., AnalysisResult]] = None   # the same, on arrays

    def settings_for(self, options: Optional[Dict[str, Any]] = None, *,
                     strict: bool = False) -> Dict[str, Any]:
        """Every setting a run with *options* uses: the defaults, overridden.

        Settings are what a person chooses and keeps the same for every
        sample — a width, a window, a method. With a :attr:`kernel` they are
        its keyword-only parameters (the positional ones are the inputs: the
        arrays, a trigger time); without one, the adapter's keyword
        parameters. *strict* refuses a name that is not a setting, which
        catches the typo that would otherwise run with the default.
        """
        import inspect

        options = dict(options or {})
        if self.kernel is not None:
            params = [p for p in inspect.signature(self.kernel).parameters.values()
                      if p.kind is p.KEYWORD_ONLY]
        else:
            params = [p for p in list(inspect.signature(self.func).parameters.values())[2:]
                      if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
        known = {p.name: (None if p.default is p.empty else p.default)
                 for p in params}
        unknown = sorted(set(options) - set(known))
        if unknown and strict:
            raise TypeError(
                f"{self.key} has no setting {', '.join(map(repr, unknown))}; "
                f"its settings are: {', '.join(known) or 'none'}")
        return jsonable({**known, **options})

    def prefix_for(self, measurement) -> str:
        """Prefix for the derived names this analysis writes on *measurement*.

        An analysis that applies to more than one modality is in danger of
        overwriting itself: peak fitting a UV-Vis band and then a diffraction
        peak would otherwise put both centres in one ``derived.peak1_center``
        column, and the second would win silently. So those analyses name
        their columns after the modality they ran on —
        ``derived.uvvis_peak1_center``, ``derived.waxs1d_peak1_center`` — and
        only an analysis that can mean exactly one thing writes a bare name.

        An explicit :attr:`prefix` on the registration always wins.
        """
        if self.prefix:
            return self.prefix
        if len(self.modalities) == 1:
            return ""
        return f"{measurement.modality}_"

    def applies_to(self, measurement) -> bool:
        """True if this analysis is meaningful for *measurement*.

        An analysis with :attr:`results_of` takes the output of another one:
        it applies to a stored result (a ``fit`` linked by
        :meth:`Workbench.link_result`) of one of those analyses, and to
        nothing else — not even to a stored result of its own.
        """
        if self.results_of and (measurement.meta or {}).get("analysis") \
                not in self.results_of:
            return False
        if self.modalities and measurement.modality not in self.modalities:
            return False
        if self.stages and measurement.stage not in self.stages:
            return False
        if self.groups and measurement.group not in self.groups:
            return False
        return True

    def __call__(self, measurement, resolver, **options) -> AnalysisResult:
        return self.func(measurement, resolver, **options)


ANALYSIS_REGISTRY: Dict[str, Analysis] = {}


def register_analysis(analysis: Analysis, overwrite: bool = False) -> Analysis:
    if analysis.key in ANALYSIS_REGISTRY and not overwrite:
        raise ValueError(f"Analysis {analysis.key!r} is already registered")
    ANALYSIS_REGISTRY[analysis.key] = analysis
    return analysis


def get_analysis(key: str) -> Analysis:
    analysis = ANALYSIS_REGISTRY.get(key)
    if analysis is None:
        raise KeyError(
            f"Unknown analysis {key!r}; "
            f"available: {', '.join(sorted(ANALYSIS_REGISTRY))}"
        )
    return analysis


def list_analyses() -> List[Analysis]:
    return sorted(ANALYSIS_REGISTRY.values(), key=lambda a: a.key)


def analyses_for(measurement) -> List[Analysis]:
    """Every registered analysis that applies to *measurement*."""
    return [a for a in list_analyses() if a.applies_to(measurement)]


def jsonable(value):
    """*value* as it reads back from a result file: tuples as lists, numpy
    numbers as Python ones — so two sets of settings compare equal exactly
    when they would run the same."""
    import json

    def default(obj):
        return obj.tolist() if hasattr(obj, "tolist") else str(obj)

    return json.loads(json.dumps(value, default=default))


def run(key: str, measurement, resolver, **options) -> AnalysisResult:
    """Run one analysis on one measurement.

    The result records the settings it ran with and the measurement it ran
    on (``diagnostics["ran_on"]``); one that runs on another analysis'
    stored result also records that result's settings
    (``diagnostics["of_settings"]``), so it can tell when its input changed.
    """
    analysis = get_analysis(key)
    result = analysis(measurement, resolver, **options)
    result.settings = result.settings or analysis.settings_for(options)
    result.diagnostics.setdefault("ran_on", measurement.measurement_id)
    if analysis.results_of:
        from NanoOrganizer.analysis import store as _store

        paths = measurement.resolve(resolver)
        if paths:
            result.diagnostics.setdefault(
                "of_settings", _store.peek(paths[0]).get("settings", {}))
    return result


def run_method(key: str, *inputs, settings: Optional[Dict[str, Any]] = None,
               **options) -> AnalysisResult:
    """An analysis on arrays you are holding: no project, no files.

    *inputs* are what its :attr:`~Analysis.kernel` takes positionally — for
    a series of spectra, the wavelength, the frames and the clock. The
    settings are the ones :func:`run` and :func:`batch` take, so the dict
    settled here is the dict used on every sample. A name that is not a
    setting is refused.
    """
    analysis = get_analysis(key)
    if analysis.kernel is None:
        raise TypeError(f"{key} has no method on arrays; run it on a sample "
                        f"with run()")
    options = {**(settings or {}), **options}
    used = analysis.settings_for(options, strict=True)
    result = analysis.kernel(*inputs, **options)
    result.analysis = result.analysis or key
    result.settings = used
    if analysis.results_of and inputs and hasattr(inputs[0], "settings"):
        result.diagnostics.setdefault("of_settings", inputs[0].settings)
    return result


def targets(project, key: str, *, sample_ids: Sequence[str] = (),
            modality: str = "", stage: str = "", role: str = "") -> list:
    """The measurements *key* would run on: its own declaration, narrowed."""
    analysis = get_analysis(key)
    wanted_modality = modality or (analysis.modalities[0]
                                   if len(analysis.modalities) == 1 else "")
    wanted_stage = stage or (analysis.stages[0]
                             if len(analysis.stages) == 1 else "")
    return [
        m for m in project.measurements(modality=wanted_modality,
                                        stage=wanted_stage, role=role,
                                        sample_ids=sample_ids)
        if analysis.applies_to(m)
    ]


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def batch(project, key: str, *, sample_ids: Sequence[str] = (),
          modality: str = "", stage: str = "", role: str = "",
          write: bool = True,
          keep_results: bool = False, progress: Optional[Callable] = None,
          prefix: Optional[str] = None, **options):
    """Run one analysis over every matching measurement in *project*.

    Parameters
    ----------
    sample_ids : sequence of str, optional
        Restrict to these samples — this is where a filtered basket goes.
    modality, stage, role : str, optional
        Narrow further.  *role* separates measurements of the same technique
        on the same sample — the as-made and the post-reaction scan, say.  Defaults come from the analysis' own declaration, so
        ``batch(project, "uvvis_kinetics")`` already only touches catalysis
        UV-Vis without being told.
    write : bool
        Store the scalars on each sample as derived values.  The project is
        *not* saved; call ``project.save()`` when you are happy with the table.
    keep_results : bool
        Also return the :class:`AnalysisResult` objects, which carry the curves
        for plotting.  Off by default because holding every spectrum of a
        ten-sample batch in memory is rarely what you want.
    progress : callable, optional
        Called as ``progress(index, total, measurement)`` before each run.
    prefix : str, optional
        Override the derived-name prefix.  By default it comes from
        :meth:`Analysis.prefix_for`, which keeps two modalities' results in
        two columns; pass ``""`` to write bare names, knowing that a second
        modality will then overwrite the first.

    Returns
    -------
    DataFrame, or (DataFrame, list)
        One row per measurement, failures included with ``ok == False`` and a
        ``message`` saying why.
    """
    import pandas as pd

    analysis = get_analysis(key)
    found = targets(project, key, sample_ids=sample_ids, modality=modality,
                    stage=stage, role=role)

    rows: List[Dict[str, Any]] = []
    results: List[AnalysisResult] = []

    for index, measurement in enumerate(found):
        if progress is not None:
            progress(index, len(found), measurement)
        try:
            result = run(key, measurement, project.resolver, **options)
        except Exception as exc:  # one bad run must not end the batch
            result = AnalysisResult.failure(
                key, f"{type(exc).__name__}: {exc}",
                sample_id=measurement.sample_id,
                measurement_id=measurement.measurement_id,
            )

        if write and result.ok:
            sample = project.get_sample(measurement.sample_id)
            if sample is not None:
                result.write_to(sample, prefix=(analysis.prefix_for(measurement)
                                                if prefix is None else prefix))

        rows.append(result.to_row())
        if keep_results:
            results.append(result)

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.set_index("measurement_id", drop=False)
    return (frame, results) if keep_results else frame


def batch_report(frame) -> str:
    """One-line summary of a batch table, for printing after a run."""
    if frame is None or len(frame) == 0:
        return "no measurements matched"
    ok = int(frame["ok"].sum()) if "ok" in frame else len(frame)
    total = len(frame)
    out = f"{ok}/{total} succeeded"
    if "status" in frame:
        counts = frame["status"].value_counts()
        out += (f" ({int(counts.get('ran', 0))} ran, "
                f"{int(counts.get('loaded', 0))} done before)")
    if ok < total and "message" in frame:
        reasons = frame.loc[~frame["ok"], "message"].dropna().unique()
        if len(reasons):
            out += "; failures: " + "; ".join(str(r) for r in reasons[:3])
    return out


# ---------------------------------------------------------------------------
# Built-in analyses
# ---------------------------------------------------------------------------

from NanoOrganizer.analysis import curves as _curves    # noqa: E402
from NanoOrganizer.analysis import imaging as _imaging  # noqa: E402
from NanoOrganizer.analysis import peaks as _peaks      # noqa: E402

register_analysis(Analysis(
    key="particle_sizing",
    func=_imaging.particle_sizing,
    label="Particle sizing from micrographs",
    modalities=("tem", "sem", "optical"),
    description="Otsu threshold plus watershed separation, calibrated to nm.",
))

register_analysis(Analysis(
    key="peak_fit",
    func=_peaks.peak_fit,
    label="1D peak fitting",
    groups=("curve",),
    description="Fit one or more peaks on any 1D curve, with a background.",
))

register_analysis(Analysis(
    key="curve_metrics",
    func=_curves.curve_metrics,
    label="Curve metrics in a window",
    groups=("curve", "correlation"),
    description="Height, position, area, centroid and threshold crossing — "
                "no model fitted.",
))

# Kernels, re-exported so the numeric half of every analysis is one import
# away without having to know which module it lives in. See
# ``docs/kernel_adapter_rule.md`` for why the split exists at all.
from NanoOrganizer.analysis.curves import CurveMetrics, measure_curve  # noqa: E402
from NanoOrganizer.analysis.imaging import (                           # noqa: E402
    Segmentation, measure_particles, segment_micrograph, segment_particles,
    size_from_image, size_statistics,
)
from NanoOrganizer.analysis.peaks import PeakFitResult, fit_peaks      # noqa: E402
from NanoOrganizer.analysis.profiles import (                          # noqa: E402
    azimuthal_average, radius_to_q, radius_to_two_theta, weighted_mean,
)

__all__ = [
    "Analysis", "ANALYSIS_REGISTRY", "AnalysisResult",
    "register_analysis", "get_analysis", "list_analyses", "analyses_for",
    "run", "run_method", "targets", "batch", "batch_report", "jsonable",
    # kernels: arrays in, result out — no files, no project
    "fit_peaks", "PeakFitResult", "measure_curve", "CurveMetrics",
    "segment_particles", "measure_particles", "size_from_image",
    "size_statistics", "azimuthal_average", "radius_to_q",
    "radius_to_two_theta", "weighted_mean",
    # the one-frame segmentation adapter, for checking before sizing
    "segment_micrograph", "Segmentation",
]
