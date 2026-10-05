#!/usr/bin/env python3
"""
Workbench – the one object a notebook (or a GUI page) needs.

The library underneath is deliberately explicit: a :class:`Project` holds
samples, a :class:`PathResolver` maps recorded paths onto this machine, and an
analysis takes a measurement plus a resolver. That is the right shape for code
that has to be composed, and the wrong shape to type forty times in a notebook.

:class:`Workbench` binds them together and adds the one piece of state an
interactive session always grows anyway — the **basket**, the current selection
of samples that every subsequent call defaults to:

>>> wb = open_project("/data/MyProject")               # doctest: +SKIP
>>> wb.filter("`synthesis.conditions.temperature_C` >= 5")
>>> wb.batch("uvvis_kinetics")          # only the basket            # doctest: +SKIP
>>> wb.plot_kinetics("Sample000001")                                 # doctest: +SKIP

Nothing here is required: every method is a thin call onto the library objects,
which stay reachable as ``wb.project`` and ``wb.resolver``. The GUI uses the
same class, so a page and a notebook cannot drift apart in behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from NanoOrganizer import analysis as _analysis
from NanoOrganizer.core.project import Project
from NanoOrganizer.core.schema import Measurement, Sample


def open_project(root: Union[str, Path], *,
                 aliases: Optional[Dict[str, Union[str, Sequence[str]]]] = None,
                 ingest: Union[bool, Sequence[Union[str, Path]]] = True,
                 attach: bool = True,
                 metadata_dir: str = "MetaData",
                 save: bool = False) -> "Workbench":
    """Open a project and get it ready to use in one call.

    Parameters
    ----------
    root : path
        Project directory.
    aliases : dict, optional
        ``{recorded_prefix: local_path_or_list}``. Added before ingest so the
        availability report is meaningful straight away.
    ingest : bool or sequence
        True ingests every ``*.py`` in *metadata_dir*; pass an explicit list of
        files to control the order; False skips ingest (an already-saved
        project reloads from its own store).
    attach : bool
        Also link ``<Modality>Data/<SampleID>/`` folders.
    save : bool
        Write the store afterwards. Off by default — a first look should not
        leave files behind in someone's data directory.
    """
    project = Project(root)

    for prefix, candidates in (aliases or {}).items():
        project.add_alias(prefix, candidates)

    if ingest is True:
        folder = project.root / metadata_dir
        sources = sorted(folder.glob("*.py")) if folder.is_dir() else []
    elif ingest:
        sources = [Path(s) for s in ingest]
    else:
        sources = []

    for source in sources:
        project.ingest(source)

    if attach:
        project.attach_folders()
    if save:
        project.save()

    return Workbench(project)


class Workbench:
    """A project, a selection, and the analyses that run over them."""

    def __init__(self, project: Project, basket: Sequence[str] = ()):
        self.project = project
        self._basket: List[str] = list(basket)

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------

    @property
    def resolver(self):
        return self.project.resolver

    @property
    def basket(self) -> List[str]:
        """The current selection; empty means "every sample"."""
        return list(self._basket)

    @property
    def active(self) -> List[str]:
        """Sample ids the next call will act on."""
        return self._basket or self.project.sample_ids()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        chosen = f"{len(self._basket)} selected" if self._basket else "all"
        return (f"<Workbench {self.project.config.name!r}: "
                f"{len(self.project)} samples, {chosen}>")

    def summary(self) -> str:
        return self.project.summary()

    def save(self) -> Path:
        return self.project.save()

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------

    def table(self, level: str = "sample", all_samples: bool = False):
        """The flat table, restricted to the basket unless *all_samples*."""
        ids = () if all_samples else self._basket
        return self.project.to_dataframe(level=level, sample_ids=ids)

    def columns(self, contains: str = "") -> List[str]:
        """Column names of the sample table, optionally filtered.

        The table is wide — a few hundred columns for a campaign with rich
        metadata — so this is how you find the one you want.
        """
        frame = self.project.to_dataframe()
        names = list(frame.columns)
        if contains:
            needle = contains.lower()
            names = [c for c in names if needle in c.lower()]
        return names

    def filter(self, query: str = "", **equals) -> List[str]:
        """Select samples and make them the basket.

        *query* is a pandas expression over the flat table; column names with
        dots need backticks::

            wb.filter("`synthesis.conditions.temperature_C` >= 5")
            wb.filter("`catalysis.status` == 'done' and `has.tem`")

        Keyword arguments are exact matches, which is easier for one column.
        """
        frame = self.project.to_dataframe()
        if query:
            frame = frame.query(query)
        for column, value in equals.items():
            frame = frame[frame[column] == value]

        self._basket = [str(s) for s in frame["sample_id"]]
        return self.basket

    def select(self, sample_ids: Iterable[str]) -> List[str]:
        """Set the basket explicitly."""
        known = set(self.project.sample_ids())
        chosen = [str(s) for s in sample_ids]
        missing = [s for s in chosen if s not in known]
        if missing:
            raise KeyError(f"unknown samples: {', '.join(missing)}")
        self._basket = chosen
        return self.basket

    def clear(self) -> "Workbench":
        """Drop the selection; subsequent calls act on every sample."""
        self._basket = []
        return self

    # ------------------------------------------------------------------
    # measurements
    # ------------------------------------------------------------------

    def samples(self) -> List[Sample]:
        return [self.project.get_sample(s) for s in self.active]

    def measurements(self, modality: str = "", stage: str = "",
                     group: str = "") -> List[Measurement]:
        return self.project.measurements(modality=modality, stage=stage,
                                         group=group, sample_ids=self.active)

    def measurement(self, sample_id: str, modality: str = "", stage: str = "",
                    role: str = "") -> Measurement:
        """Exactly one measurement, or an error naming the candidates."""
        sample = self.project.get_sample(sample_id)
        if sample is None:
            raise KeyError(f"unknown sample {sample_id!r}")

        found = sample.get_measurements(modality=modality, stage=stage,
                                        role=role)
        if not found:
            available = ", ".join(m.measurement_id for m in sample.measurements)
            raise KeyError(
                f"{sample_id} has no measurement matching "
                f"modality={modality!r} stage={stage!r}; it has: {available}"
            )
        if len(found) > 1:
            raise KeyError(
                f"{sample_id} has {len(found)} matching measurements: "
                f"{', '.join(m.measurement_id for m in found)}. "
                f"Narrow with stage= or role=."
            )
        return found[0]

    def available(self) -> Dict[str, Any]:
        """How much of the selection's data is readable on this machine."""
        return self.project.availability()

    # ------------------------------------------------------------------
    # analysis
    # ------------------------------------------------------------------

    def analyses(self, sample_id: str = "", **kwargs) -> List[str]:
        """Analyses that apply — to one measurement, or to anything selected."""
        if sample_id:
            return [a.key for a in
                    _analysis.analyses_for(self.measurement(sample_id, **kwargs))]
        keys: List[str] = []
        for measurement in self.measurements():
            for item in _analysis.analyses_for(measurement):
                if item.key not in keys:
                    keys.append(item.key)
        return keys

    def _target(self, key: str, sample_id: str, **kwargs) -> Measurement:
        """Resolve the measurement an analysis should run on.

        The analysis' own ``applies_to`` does the narrowing, rather than
        copying its first declared modality: ``particle_sizing`` accepts TEM,
        SEM and optical, and a sample that has exactly one of them is not
        ambiguous even though the analysis names three.
        """
        spec = _analysis.get_analysis(key)
        sample = self.project.get_sample(sample_id)
        if sample is None:
            raise KeyError(f"unknown sample {sample_id!r}")

        found = [m for m in sample.get_measurements(**kwargs)
                 if spec.applies_to(m)]
        if len(found) == 1:
            return found[0]

        if not found:
            available = ", ".join(m.measurement_id for m in sample.measurements)
            raise KeyError(
                f"{sample_id} has nothing {key!r} can run on"
                + (f"; it has: {available}" if available else "")
            )
        raise KeyError(
            f"{sample_id} has {len(found)} measurements {key!r} could use: "
            f"{', '.join(m.measurement_id for m in found)}. "
            f"Narrow with modality=, stage= or role=."
        )

    def run(self, key: str, sample_id: str, *, modality: str = "",
            stage: str = "", role: str = "", write: bool = False, **options):
        """Run one analysis on one sample.

        The measurement is found from the analysis' own declaration, so
        ``wb.run("uvvis_kinetics", "Sample000001")`` needs no further hints.
        ``write`` is off here on purpose: a single exploratory run should not
        silently change the results table — use :meth:`batch` for that.
        """
        where = {k: v for k, v in
                 (("modality", modality), ("stage", stage), ("role", role))
                 if v}
        measurement = self._target(key, sample_id, **where)
        result = _analysis.run(key, measurement, self.resolver, **options)
        if write and result.ok:
            result.write_to(
                self.project.get_sample(sample_id),
                prefix=_analysis.get_analysis(key).prefix_for(measurement))
        return result

    def batch(self, key: str, *, write: bool = True, verbose: bool = True,
              **options):
        """Run an analysis over the basket and write the derived values back."""
        frame = _analysis.batch(self.project, key, sample_ids=self.active,
                                write=write, **options)
        if verbose:
            print(f"{key}: {_analysis.batch_report(frame)}")
        return frame

    def run_all(self, keys: Sequence[str] = (), *, write: bool = True,
                verbose: bool = True, **options) -> Dict[str, Any]:
        """Run several analyses over the basket; returns ``{key: table}``."""
        keys = keys or self.analyses()
        return {key: self.batch(key, write=write, verbose=verbose, **options)
                for key in keys}

    # ------------------------------------------------------------------
    # plots
    # ------------------------------------------------------------------

    def plot_kinetics(self, sample_id: str, axes=None, **options):
        """Run the kinetics analysis on one sample and plot it."""
        from NanoOrganizer.viz import plots

        return plots.plot_kinetics(
            self.run("uvvis_kinetics", sample_id, **options), axes=axes)

    def plot_spectra(self, sample_id: str, stage: str = "synthesis", ax=None,
                     **options):
        """Spectra over a run, coloured by time."""
        from NanoOrganizer.viz import plots

        key = "uvvis_spectra" if stage == "synthesis" else "uvvis_kinetics"
        return plots.plot_spectra(self.run(key, sample_id, **options), ax=ax)

    def plot_endpoint(self, sample_id: str, ax=None, **options):
        """The grown sol's plasmon band, with peak and width marked."""
        from NanoOrganizer.viz import plots

        return plots.plot_endpoint_spectrum(
            self.run("uvvis_spectra", sample_id, **options), ax=ax)

    def plot_sizes(self, sample_id: str, ax=None, **options):
        """Pooled particle-size histogram."""
        from NanoOrganizer.viz import plots

        return plots.plot_size_distribution(
            self.run("particle_sizing", sample_id, **options), ax=ax)

    def plot_segmentation(self, sample_id: str, modality: str = "tem",
                          ax=None, **options):
        """Particle outlines over the raw micrograph — always check this."""
        from NanoOrganizer.viz import plots

        return plots.plot_segmentation(
            self.measurement(sample_id, modality=modality), self.resolver,
            ax=ax, **options)

    def plot_compare(self, x: str, y: str, color_by: str = "", ax=None,
                     **options):
        """Scatter a derived quantity against a synthesis parameter."""
        from NanoOrganizer.viz import plots

        return plots.plot_compare(self.table(all_samples=not self._basket),
                                  x, y, color_by=color_by, ax=ax, **options)

    def plot_overlay(self, modality: str = "uvvis", stage: str = "catalysis",
                     wavelength: Optional[float] = None, ax=None, **options):
        """Overlay one curve per selected sample — the batch comparison plot.

        With *wavelength* given, the curve is that band's A(t); otherwise it is
        each sample's endpoint spectrum.
        """
        import numpy as np

        from NanoOrganizer.analysis import frames as _frames
        from NanoOrganizer.viz import plots

        curves: List[Tuple[str, Any, Any]] = []
        for measurement in self.measurements(modality=modality, stage=stage):
            try:
                series = _frames.load_series(measurement, self.resolver,
                                             **options)
            except (FileNotFoundError, ValueError):
                continue
            if wavelength is None:
                curves.append((measurement.sample_id,
                               series.wavelength, series.absorbance[-1]))
            else:
                curves.append((measurement.sample_id,
                               np.asarray(series.t_s) / 60.0,
                               series.trace(wavelength)))

        if not curves:
            raise ValueError(
                f"no readable {modality}/{stage} measurements in the selection")

        if wavelength is None:
            return plots.plot_curves(curves, ax=ax, xlabel="wavelength (nm)",
                                     ylabel="absorbance",
                                     title="endpoint spectra")
        return plots.plot_curves(curves, ax=ax, xlabel="time (min)",
                                 ylabel=f"A({wavelength:.0f} nm)",
                                 title=f"A({wavelength:.0f} nm) over time")


__all__ = ["Workbench", "open_project"]
