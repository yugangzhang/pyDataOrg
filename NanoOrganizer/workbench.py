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
from NanoOrganizer.core import modality as _modality
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

    Notes
    -----
    A path to a ``.json`` file opens that file as an :class:`Organizer`
    instead, so one call handles both shapes a project can take — a directory
    with a hidden store, or a single document naming data that lives
    elsewhere.
    """
    target = Path(root).expanduser()
    if target.suffix.lower() == ".json":
        organizer = Organizer(target, aliases=aliases)
        if save:
            organizer.save()
        return organizer

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


def new_organizer(root: Union[str, Path], name: str = "", *,
                  aliases: Optional[Dict[str, Union[str, Sequence[str]]]] = None,
                  ) -> "Workbench":
    """Start an empty organiser at *root*, to be filled by linking.

    :func:`open_project` is for a project that already exists on disk — a
    ``MetaData/`` folder to ingest, data laid out underneath it to attach.
    This is for the other case, which is at least as common: the data is
    already somewhere, scattered across mounts that are not going to change,
    and what is missing is the thing that knows where it all is.

    *root* is only where the store is written (``.nanoorganizer/``); none of
    the data has to live there, or anywhere near it.

    >>> wb = new_organizer("~/Repos/OrgDemo/CuAuStudy")                     # doctest: +SKIP
    >>> wb.link("CuAu05", "uvvis", "/mnt/specs/CuAu05/*.csv")  # doctest: +SKIP
    >>> wb.link("CuAu05", "tem", "/mnt/scope/session17/")      # doctest: +SKIP
    >>> wb.set_params("CuAu05", au_fraction=0.55)              # doctest: +SKIP
    >>> wb.plot("CuAu05", "uvvis")                             # doctest: +SKIP
    >>> wb.save()                                              # doctest: +SKIP
    """
    project = Project(root, name=name)
    for prefix, candidates in (aliases or {}).items():
        project.add_alias(prefix, candidates)
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

    def ids(self, query: str = "", **equals) -> List[str]:
        """The sample ids in play, without changing the selection.

        ``wb.ids()`` is the basket (or everything, if none is set);
        ``wb.ids("`synthesis.temperature_C` > 90")`` answers a question
        without committing to it, which :meth:`filter` would.
        """
        if not query and not equals:
            return list(self.active)

        frame = self.project.to_dataframe()
        if query:
            frame = frame.query(query)
        for column, value in equals.items():
            frame = frame[frame[column] == value]
        chosen = [str(s) for s in frame["sample_id"]]
        if self._basket:
            keep = set(self._basket)
            chosen = [s for s in chosen if s in keep]
        return chosen

    def table(self, level: str = "sample", all_samples: bool = False,
              sample_ids: Sequence[str] = ()):
        """The flat table, restricted to the basket unless told otherwise.

        *sample_ids* overrides both, which is how a comparison over an
        explicit list is built without disturbing the current selection.
        """
        ids = tuple(sample_ids) if sample_ids else (
            () if all_samples else self._basket)
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

    def __getitem__(self, sample_id: str) -> Sample:
        """``wb["CuAu05"]`` — the sample record itself."""
        sample = self.project.get_sample(str(sample_id))
        if sample is None:
            raise KeyError(f"unknown sample {sample_id!r}")
        return sample

    # ------------------------------------------------------------------
    # building: linking data in, wherever it lives
    # ------------------------------------------------------------------

    def link(self, sample_id: str, modality: str, source, **kwargs) -> Measurement:
        """Attach data to a sample wherever it lives.

        *source* is a glob (kept live and re-expanded at read time), a
        directory (listed now), or a path or list of paths. The mount it sits
        on is recorded as a project alias, so the store moves to another
        machine by editing one line rather than every record.

        >>> wb.link("CuAu05", "uvvis", "/mnt/specs/CuAu05/*.csv",
        ...         stage="synthesis", instrument="HR4000")   # doctest: +SKIP

        See :func:`NanoOrganizer.core.linking.link` for every option.
        """
        return self.project.link(sample_id, modality, source, **kwargs)

    def link_folder(self, sample_id: str, modality: str, folder,
                    **kwargs) -> Measurement:
        """Link a folder as a **live** glob rather than a snapshot listing.

        The right choice while an experiment is still running: frames written
        after the link appear the next time the measurement is read.
        """
        return self.project.link_folder(sample_id, modality, folder, **kwargs)

    def link_many(self, mapping, **defaults) -> List[Measurement]:
        """Link a whole campaign from ``{sample_id: {modality: source}}``."""
        return self.project.link_many(mapping, **defaults)

    def link_table(self, rows, **defaults) -> List[Measurement]:
        """Link from a DataFrame, a CSV, or a list of dicts.

        A spreadsheet kept by whoever ran the instrument is an ingest format,
        with no adapter to write for it.
        """
        return self.project.link_table(rows, **defaults)

    def links_table(self, all_samples: bool = False):
        """Every link as a table — the export half of ``link_table``.

        A spreadsheet is a better editor than a form: export the links, fix
        the forty rows where the instrument wrote the sample id with a
        different separator, and feed the file back to :meth:`link_table`.
        """
        import pandas as pd

        ids = () if all_samples else self._basket
        return pd.DataFrame(self.project.links_table(sample_ids=ids))

    def unlink(self, sample_id: str, modality: str = "", stage: str = "",
               role: str = "") -> List[str]:
        """Drop matching measurements; returns the ids removed."""
        return self.project.unlink(sample_id, modality=modality, stage=stage,
                                   role=role)

    def add_sample(self, sample_id: str, **params) -> Sample:
        """Create a sample, with or without any data yet.

        A synthesis that failed has no files and is still a result: leaving it
        out biases every comparison drawn afterwards.
        """
        sample = self.project.add_sample(str(sample_id))
        if params:
            self.set_params(sample_id, **params)
        return sample

    def remove_sample(self, sample_id: str) -> bool:
        """Forget a sample and its links. No file is touched."""
        removed = self.project.remove_sample(sample_id)
        self._basket = [s for s in self._basket if s != sample_id]
        return removed

    def set_params(self, sample_id: str, stage: str = "synthesis", **fields):
        """Record the conditions a sample was made or measured under.

        Linking gives an organiser files; this gives it something to filter
        on. ``wb.set_params("CuAu05", au_fraction=0.55)`` becomes the column
        ``synthesis.au_fraction``.
        """
        return self.project.set_params(sample_id, stage=stage, **fields)

    # ------------------------------------------------------------------
    # looking at the organiser itself
    # ------------------------------------------------------------------

    def tree(self, depth: int = 2, limit: int = 8, address: str = "") -> str:
        """Walk the organiser one layer at a time — structure, not data.

        ``wb.tree()`` describes what is in the session **now**, not what was
        last saved. That distinction matters more than it sounds: walking the
        file on disk would quietly show the state before your last twenty
        links and look entirely correct.

        Pass *address* to descend inside it (``"samples/0"``), or to point
        somewhere else entirely — a data folder, an HDF5 group, a metadata
        module — in which case that address is walked as given.
        """
        import json
        import tempfile

        from NanoOrganizer import structure

        if address and "::" in address:
            return structure.tree(address, depth=depth, limit=limit)

        payload = {
            "project": self.project.config.to_dict(),
            "samples": [s.to_dict() for s in self.project.sorted_samples()],
        }
        # Serialising to a scratch file is what lets the same walker handle a
        # live organiser and a saved one; the user's own store is untouched.
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=f"-{Path(self.project.store_path).name}",
            delete=False, encoding="utf-8")
        try:
            json.dump(payload, handle, indent=2, default=str)
            handle.close()
            target = f"{handle.name}::{address}" if address else handle.name
            text = structure.tree(target, depth=depth, limit=limit)
        finally:
            Path(handle.name).unlink(missing_ok=True)

        # The scratch name is an implementation detail; show the real one.
        return text.replace(Path(handle.name).name,
                            Path(self.project.store_path).name, 1)

    def overview(self) -> Dict[str, Any]:
        """What this organiser contains, in one dict.

        Four questions a session opens with — how many samples, what was done
        to them, which techniques are present, and what has been analysed —
        answered without touching the data. :meth:`describe` prints it.
        """
        samples = self.project.sorted_samples()
        stages: Dict[str, int] = {}
        for sample in samples:
            for stage_id in sample.stages:
                stages[stage_id] = stages.get(stage_id, 0) + 1

        by_group: Dict[str, List[str]] = {}
        for key in self.project.modalities():
            spec = _modality.get(key)
            if key == "fit":
                continue
            by_group.setdefault(spec.group if spec else "curve", []).append(key)

        analyses: Dict[str, int] = {}
        for measurement in self.project.measurements(modality="fit"):
            name = measurement.meta.get("analysis") or measurement.role or "?"
            source = measurement.meta.get("source_modality", "")
            label = f"{name} ({source})" if source else name
            analyses[label] = analyses.get(label, 0) + 1

        derived = sorted({name for s in samples for name in s.derived})
        report = self.project.availability()

        return {
            "name": self.project.config.name,
            "store": str(self.project.store_path),
            "n_samples": len(samples),
            "sample_ids": [s.sample_id for s in samples],
            "stages": stages,
            "modalities": by_group,
            "n_measurements": report["n_measurements"],
            "n_readable": report["n_available"],
            "n_unresolved": report["n_unresolved"],
            "analyses": analyses,
            "derived_columns": derived,
            "selected": list(self._basket),
        }

    def describe(self) -> str:
        """A printable :meth:`overview` — the first cell of a session."""
        info = self.overview()
        lines = [f"{info['name']}  ({info['store']})",
                 f"  samples       {info['n_samples']}"]

        shown = info["sample_ids"][:8]
        tail = ("  … +%d more" % (info["n_samples"] - len(shown))
                if info["n_samples"] > len(shown) else "")
        lines.append(f"                {', '.join(shown)}{tail}")

        if info["stages"]:
            lines.append("  stages        " + ", ".join(
                f"{k} ({v})" for k, v in sorted(info["stages"].items())))

        for group, keys in info["modalities"].items():
            label = _modality.GROUP_LABELS.get(group, group)
            lines.append(f"  {label:<13} {', '.join(keys)}")

        lines.append(f"  measurements  {info['n_measurements']} "
                     f"({info['n_readable']} readable here, "
                     f"{info['n_unresolved']} not mounted)")
        if info["analyses"]:
            lines.append("  stored fits   " + ", ".join(
                f"{k} ({v})" for k, v in sorted(info["analyses"].items())))
        if info["derived_columns"]:
            columns = info["derived_columns"]
            lines.append(f"  derived       {len(columns)}: "
                         + ", ".join(columns[:4])
                         + (" …" if len(columns) > 4 else ""))
        if info["selected"]:
            lines.append(f"  selected      {len(info['selected'])} samples")

        text = "\n".join(lines)
        print(text)
        return text

    def subset(self, sample_ids: Sequence[str] = (), query: str = "",
               name: str = "", path: Union[str, Path, None] = None,
               **equals) -> "Workbench":
        """A new organiser holding only the samples named.

        Takes an explicit list, a query, or both::

            plate = org.subset(["S01", "S03", "S07"], name="plate_A")
            hot   = org.subset(query="`synthesis.temperature_C` >= 100")

        The samples are **deep-copied**, so analysing the subset cannot write
        derived values back into the parent by accident — the one thing a
        shared view would get wrong. Path aliases come along, so the data
        still resolves.

        **Nothing is written** until you call ``save()`` on the result; the
        store path is only where it *would* go.
        """
        import copy

        chosen = list(sample_ids) if sample_ids else []
        if query or equals:
            found = self.ids(query, **equals)
            chosen = [s for s in chosen if s in set(found)] if chosen else found
        if not chosen:
            chosen = list(self.active)

        known = set(self.project.sample_ids())
        missing = [s for s in chosen if s not in known]
        if missing:
            raise KeyError(f"unknown samples: {', '.join(missing)}")

        store = Path(self.project.store_path)
        if path is None:
            tag = name or "subset"
            path = store.with_name(f"{store.stem}__{tag}.json")

        child = Organizer(path, name=name or f"{self.project.config.name}"
                                             f" ({len(chosen)} samples)")
        child.project.config.path_aliases = list(self.project.config.path_aliases)
        child.project.config.extra_roots = list(self.project.config.extra_roots)
        child.project._resolver = None
        for sample_id in chosen:
            child.project.add_sample(
                copy.deepcopy(self.project.get_sample(sample_id)))
        return child

    def catalog(self, counts: bool = False, sample_ids: Sequence[str] = ()):
        """The sample × technique matrix — what exists, and what does not.

        The gaps are the point. A campaign's measurement matrix is always
        sparse (beamtime is finite, a synthesis failed, someone was away that
        week) and a table of ticks is how you see which comparisons are
        actually available before building one.

        With *counts*, each cell is the number of files instead of a tick.
        """
        import pandas as pd

        modalities = self.project.modalities()
        chosen = ([self.project.get_sample(s) for s in sample_ids]
                  if sample_ids else self.samples())
        rows = []
        for sample in chosen:
            if sample is None:
                continue
            row: Dict[str, Any] = {"sample_id": sample.sample_id}
            for key in modalities:
                found = sample.get_measurements(modality=key)
                if counts:
                    row[key] = sum(len(m.resolve(self.resolver)) for m in found)
                else:
                    row[key] = bool(found)
            rows.append(row)

        frame = pd.DataFrame(rows)
        if "sample_id" in frame.columns:
            frame = frame.set_index("sample_id")
        return frame

    # ------------------------------------------------------------------
    # reading and drawing, by sample and technique
    # ------------------------------------------------------------------

    def frames(self, sample_id: str, modality: str = "", *, stage: str = "",
               role: str = ""):
        """The layer below a measurement: one row per file.

        A measurement is rarely one number — it is forty spectra taken while
        the reaction ran. Each row carries the frame's index and whatever its
        filename admitted about when (``t_s``) and how hot (``T_c``) it was
        taken, which is what makes ``plot(..., t=600)`` possible.
        """
        import pandas as pd

        from NanoOrganizer.viz import show as _show

        measurement = self.measurement(sample_id, modality=modality,
                                       stage=stage, role=role)
        return pd.DataFrame(_show.frames(measurement, self.resolver))

    def data(self, sample_id: str, modality: str = "", *, stage: str = "",
             role: str = "", lazy: bool = False, **selection):
        """Read one measurement into arrays — no figure, just the numbers.

        What comes back follows the group, because that is what the data is:

        ===========  ====================================================
        curve        ``(x, Y, info)`` with ``Y`` of shape (n_frames, n_x)
        image        ``(array, info)``
        volume       ``(volume, info)``
        ===========  ====================================================

        Frame selectors (``frame=``, ``t=``, ``T=``, ``file=``) address the
        layer below; ``t`` and ``T`` take the nearest recorded value, since an
        acquisition clock never lands on a round number.

        With ``lazy=True`` nothing is read: you get a
        :class:`~NanoOrganizer.analysis.lazy.LazyFrames` sequence that knows
        how many frames there are and opens one only when it is indexed. That
        is the difference between looking at the third of four hundred
        micrographs and reading twelve gigabytes to do it.

        >>> frames = org.data("S01", "tem", lazy=True)     # doctest: +SKIP
        >>> len(frames)                                    # nothing opened
        >>> array, info = frames[2]                        # one file opened
        >>> stack, info = frames.load()                    # all of them
        """
        from NanoOrganizer.analysis import reading
        from NanoOrganizer.viz import show as _show

        measurement = self.measurement(sample_id, modality=modality,
                                       stage=stage, role=role)
        group = measurement.group

        if lazy:
            from NanoOrganizer.analysis import lazy as _lazy

            if selection:
                raise TypeError(
                    "lazy=True returns every frame, so frame=/t=/T=/file= do "
                    "not apply — index the result instead: "
                    "data(..., lazy=True)[2]")
            return _lazy.frames_for(measurement, self.resolver)

        if group in ("volume", "image"):
            unknown = set(selection) - {"frame", "t", "T", "file"}
            if unknown:
                raise TypeError(
                    f"{group} data takes only frame=, t=, T= and file=; "
                    f"got {', '.join(sorted(unknown))}")
        if group == "volume":
            return reading.load_volume(measurement, self.resolver)
        if group == "image":
            index = _show.select_frame(
                measurement, self.resolver,
                n_available=len(measurement.resolve(self.resolver)),
                **selection)
            return reading.load_image(measurement, self.resolver, index)
        return _show.curve_data(measurement, self.resolver, **selection)

    def plot(self, sample_id: str, modality: str = "", *, stage: str = "",
             role: str = "", engine: str = "static", **options):
        """Draw one measurement, chosen by sample and technique.

        The figure follows what the data *is*, not which instrument made it:
        a curve gets lines (coloured by time when the filenames carry a
        clock), an image gets a percentile-clipped heatmap on calibrated axes
        where the file knew its scale, a volume gets a slab projection — or,
        with ``engine="interactive"``, something you can turn around.

        >>> wb.plot("CuAu05", "uvvis")                        # doctest: +SKIP
        >>> wb.plot("CuAu05", "uvvis", t=600)      # nearest frame to 600 s
        >>> wb.plot("CuAu05", "tem", frame=2)                 # doctest: +SKIP
        >>> wb.plot("CuAu05", "tomo", engine="interactive", mode="volume")

        Returns a matplotlib ``Axes``, or a Plotly ``Figure`` when
        *engine* is ``"interactive"``.
        """
        from NanoOrganizer.viz import show as _show

        measurement = self.measurement(sample_id, modality=modality,
                                       stage=stage, role=role)
        return _show.figure(measurement, self.resolver, engine=engine, **options)

    def overlay(self, modality: str, *, sample_ids: Sequence[str] = (),
                stage: str = "", role: str = "",
                reduce: str = "last", engine: str = "static",
                verbose: bool = True, **options):
        """One curve per sample — the across-samples comparison.

        Draws the basket by default; *sample_ids* overrides it, so a one-off
        comparison needs neither a filter nor a subset::

            org.overlay("waxs1d", sample_ids=["S01", "S04", "S06"])

        Many-frame measurements are collapsed by *reduce* first, because the
        comparison is between samples and forty frames of each would bury it.
        Samples whose files do not resolve are skipped and named, rather than
        taking the figure down.
        """
        from NanoOrganizer.viz import show as _show

        wanted = tuple(sample_ids) if sample_ids else self.active
        measurements = self.project.measurements(modality=modality,
                                                 stage=stage,
                                                 sample_ids=wanted)
        if role:
            measurements = [m for m in measurements if m.role == role]

        skipped: List[str] = []
        figure = _show.overlay(measurements, self.resolver, reduce=reduce,
                               engine=engine, skipped=skipped, **options)
        if skipped and verbose:
            print(f"skipped {len(skipped)}: " + "; ".join(skipped[:3])
                  + (" …" if len(skipped) > 3 else ""))
        return figure

    # ------------------------------------------------------------------
    # results: analysis output, linked back like any other data
    # ------------------------------------------------------------------

    @property
    def results_dir(self) -> Path:
        """Where stored results go: ``results/`` beside the store."""
        from NanoOrganizer.analysis import store as _store

        return Path(self.project.store_path).parent / _store.RESULTS_DIR

    def link_result(self, result, *, folder: Union[str, Path, None] = None,
                    write: bool = True) -> Measurement:
        """Persist an :class:`AnalysisResult` and link it onto its sample.

        The scalars already live in the store as ``derived.*``; what this adds
        is the **curves** — the fitted line, the residuals — written beside the
        organiser and referenced like any other data. A fit is a measurement
        of a measurement, so it needs no second mechanism: it comes back with
        ``result()``, draws with ``plot_result()``, and survives being
        reopened months later without the analysis being run again.

        >>> fit = wb.run("peak_fit", "CuAu05")             # doctest: +SKIP
        >>> wb.link_result(fit)                            # doctest: +SKIP
        """
        from NanoOrganizer.analysis import get_analysis
        from NanoOrganizer.analysis import store as _store

        sample = self.project.get_sample(result.sample_id)
        if sample is None:
            raise KeyError(f"unknown sample {result.sample_id!r}")

        path = _store.save_result(result, folder or self.results_dir)

        source = sample.get_measurement(result.measurement_id)
        if write and result.ok:
            prefix = ""
            try:
                spec = get_analysis(result.analysis)
                prefix = spec.prefix_for(source) if source is not None else ""
            except KeyError:
                pass
            result.write_to(sample, prefix=prefix)

        # The role carries the modality it was fitted on, for the same reason
        # the derived columns do: peak-fitting a UV-Vis band and then a
        # diffraction peak are two results, and a shared id would make the
        # second quietly replace the first.
        source_modality = source.modality if source is not None else ""
        role = (f"{result.analysis}-{source_modality}" if source_modality
                else result.analysis)

        return self.project.link(
            result.sample_id, "fit", str(path), stage="analysis",
            role=role, alias=False, check=False,
            label=f"{result.analysis} of {result.measurement_id}",
            meta={"analysis": result.analysis,
                  "source_measurement": result.measurement_id,
                  "source_modality": source_modality,
                  "ok": result.ok},
        )

    def _stored_fit(self, sample_id: str, analysis: str = "",
                    modality: str = "") -> Measurement:
        """The one stored fit matching, or an error naming the candidates."""
        sample = self.project.get_sample(sample_id)
        if sample is None:
            raise KeyError(f"unknown sample {sample_id!r}")

        found = sample.get_measurements(modality="fit")
        if analysis:
            found = [m for m in found
                     if m.meta.get("analysis") == analysis
                     or m.role in (analysis, f"{analysis}-{modality}")]
        if modality:
            found = [m for m in found
                     if m.meta.get("source_modality") == modality]

        if len(found) == 1:
            return found[0]

        catalogue = ", ".join(
            f"{m.meta.get('analysis', m.role)} of "
            f"{m.meta.get('source_modality', '?')}"
            for m in sample.get_measurements(modality="fit"))
        if not found:
            raise KeyError(
                f"{sample_id} has no stored {analysis or 'fit'} result"
                + (f"; it has: {catalogue}" if catalogue else
                   ". Run an analysis with link=True first."))
        raise KeyError(
            f"{sample_id} has {len(found)} stored results matching: "
            f"{catalogue}. Narrow with modality=.")

    def result(self, sample_id: str, analysis: str = "", *,
               modality: str = ""):
        """Load a stored result back. Returns an :class:`AnalysisResult`.

        ``modality=`` picks between two fits of the same analysis on one
        sample — a peak fit of the spectrum and one of the diffraction
        pattern are two results, not one.
        """
        from NanoOrganizer.analysis import store as _store

        measurement = self._stored_fit(sample_id, analysis, modality)
        paths = measurement.resolve(self.resolver)
        if not paths:
            raise FileNotFoundError(
                f"{measurement.measurement_id} does not resolve: the result "
                f"file was moved or never written here.")
        return _store.load_result(paths[0])

    def results(self, all_samples: bool = False):
        """Every stored result as a table — what has been analysed, and how."""
        import pandas as pd

        from NanoOrganizer.analysis import store as _store

        rows = []
        samples = (self.project.sorted_samples() if all_samples
                   else [self.project.get_sample(s) for s in self.active])
        for sample in samples:
            if sample is None:
                continue
            for measurement in sample.get_measurements(modality="fit"):
                paths = measurement.resolve(self.resolver)
                row = {
                    "sample_id": sample.sample_id,
                    "analysis": measurement.meta.get("analysis",
                                                     measurement.role),
                    "modality": measurement.meta.get("source_modality", ""),
                    "of": measurement.meta.get("source_measurement", ""),
                    "ok": measurement.meta.get("ok", True),
                    "file": paths[0].name if paths else "",
                    "readable": bool(paths),
                }
                if paths:
                    meta = _store.peek(paths[0])
                    row.update({k: v for k, v in meta.get("values", {}).items()
                                if isinstance(v, (int, float, str, bool))})
                rows.append(row)
        return pd.DataFrame(rows)

    def plot_result(self, sample_id: str, analysis: str = "", *,
                    modality: str = "", engine: str = "static", **options):
        """Redraw a stored fit over its data — no analysis is run."""
        from NanoOrganizer.viz import show as _show

        return _show.result_figure(
            self.result(sample_id, analysis, modality=modality),
            engine=engine, **options)

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

    def fit(self, sample_id: str, modality: str = "", *,
            analysis: str = "peak_fit", stage: str = "", role: str = "",
            show: bool = False, **params):
        """Try one fit on one sample and hand back the result — nothing stored.

        The deliberate first step of an analysis: settle the parameters on a
        sample you can look at, *then* spend them on the whole set. Running
        the batch first and reading its R² column afterwards is the same work
        in the order that hides the mistake.

        >>> params = dict(x_range=(2.3, 3.0), n_peaks=1, background="linear")
        >>> result = org.fit("S01", "waxs1d", show=True, **params)  # +SKIP
        >>> org.batch("peak_fit", modality="waxs1d", link=True, **params)

        Returns the :class:`AnalysisResult`; with *show*, returns
        ``(result, axes)`` so the check is one call.
        """
        where = {k: v for k, v in (("modality", modality), ("stage", stage),
                                   ("role", role)) if v}
        measurement = self._target(analysis, sample_id, **where)
        result = _analysis.run(analysis, measurement, self.resolver, **params)
        if not show:
            return result
        if not result.ok:
            raise ValueError(f"{analysis} failed on {sample_id}: "
                             f"{result.message}")
        return result, self.plot_fit(result)

    def plot_fit(self, result, *, engine: str = "static", **options):
        """Draw a result you are holding — no store, no file, no round trip."""
        from NanoOrganizer.viz import show as _show

        return _show.result_figure(result, engine=engine, **options)

    def batch(self, key: str, *, write: bool = True, verbose: bool = True,
              link: bool = False, **options):
        """Run an analysis over the basket and write the derived values back.

        With *link*, each result's curves are also saved beside the organiser
        and linked onto its sample, so the fits can be redrawn later without
        being recomputed. Off by default: a batch over a large selection
        writes one file per sample, which should be asked for.
        """
        outcome = _analysis.batch(self.project, key, sample_ids=self.active,
                                  write=write, keep_results=link, **options)
        frame, results = outcome if link else (outcome, [])

        linked = 0
        for result in results:
            if not result.ok:
                continue
            self.link_result(result, write=False)
            linked += 1

        if verbose:
            note = f", linked {linked}" if link else ""
            print(f"{key}: {_analysis.batch_report(frame)}{note}")
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


class Organizer(Workbench):
    """One named file that knows where a campaign's data is.

    ``Project``/``open_project`` assume a project *directory*: metadata in
    ``MetaData/``, data underneath, a store in a hidden ``.nanoorganizer/``.
    That is right when the directory is the project.  It is the wrong shape
    when the data is scattered across mounts that are not going to move and
    what you actually want is a single document naming all of it::

        org = Organizer("~/Repos/OrgDemo/cuau.json")      # empty if new

        org.ingest(synthesis=Synthesis_dict)        # a live dict, not a path
        org.link("CuAu05", "tem", "/mnt/scope/session17/")
        org.save()

    Reopening is the same call, and everything is back — links, parameters,
    derived values, and the results linked by :meth:`link_result`:

        org = Organizer("~/Repos/OrgDemo/cuau.json")
        org.filter("`synthesis.temperature_C` > 90")
        org.plot("CuAu05", "uvvis")
        org.plot_result("CuAu05", "peak_fit")

    Parameters
    ----------
    store : path
        The JSON document.  A directory is accepted and gets
        ``organizer.json`` inside it.  Its parent is the project root, which
        is only used to resolve relative paths — the data can be anywhere.
    name : str, optional
        Display name.  Defaults to the file's stem.
    aliases : dict, optional
        ``{recorded_prefix: local_path_or_list}``, applied before anything
        else so an availability report means something straight away.
    """

    def __init__(self, store: Union[str, Path], name: str = "", *,
                 aliases: Optional[Dict[str, Union[str, Sequence[str]]]] = None,
                 basket: Sequence[str] = ()):
        path = Path(store).expanduser()
        if path.is_dir() or not path.suffix:
            path = path / "organizer.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        project = Project(path.parent, name=name, store_file=path)
        for prefix, candidates in (aliases or {}).items():
            project.add_alias(prefix, candidates)

        super().__init__(project, basket=basket)

    @property
    def path(self) -> Path:
        """The document this organizer reads and writes."""
        return Path(self.project.store_path)

    def ingest(self, source=None, **kwargs) -> List[str]:
        """Read metadata in — a live dict, or an authored file.

        >>> org.ingest(synthesis=Synthesis_dict)              # doctest: +SKIP
        >>> org.ingest(Synthesis_dict, stage="synthesis")     # doctest: +SKIP
        >>> org.ingest("MetaData/Synthesis_dict.py")          # doctest: +SKIP

        Pass ``replace=True`` to treat the dict as the whole truth for its
        stage, so that editing a record and re-ingesting removes what was
        popped instead of leaving it behind.
        """
        return self.project.ingest(source, **kwargs)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        chosen = f"{len(self._basket)} selected" if self._basket else "all"
        return (f"<Organizer {self.project.config.name!r}: "
                f"{len(self.project)} samples, {chosen} — {self.path}>")


__all__ = ["Workbench", "Organizer", "open_project", "new_organizer"]
