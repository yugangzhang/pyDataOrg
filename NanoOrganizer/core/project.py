#!/usr/bin/env python3
"""
Project – a directory of samples, their metadata sources, and path aliases.

A project owns:

* **samples** – the canonical store, written to ``.nanoorganizer/samples.json``;
* **config** – project name, path aliases, metadata sources and modality
  folder conventions, in ``.nanoorganizer/project.json``;
* a **resolver** built from those aliases.

The authored metadata (a ``*_dict.py`` at the instrument, a CSV, a notebook)
stays the source of truth and is never edited in place.  :meth:`Project.ingest`
reads it into the canonical store; re-ingesting is idempotent, so the authored
file can keep growing and the project simply re-reads it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Union

from NanoOrganizer.core import modality as _modality
from NanoOrganizer.core.pathmap import PathAlias, PathResolver
from NanoOrganizer.core.schema import Measurement, Sample, Stage

CONFIG_DIR = ".nanoorganizer"
CONFIG_NAME = "project.json"
STORE_NAME = "samples.json"

# ``<Modality>Data/<SampleID>/`` is the convention these projects already use
# on disk; the left-hand side is matched case-insensitively against folder
# names, with the trailing "Data" optional.
DEFAULT_MODALITY_DIRS = {
    "TEMData": "tem",
    "SEMData": "sem",
    "DLSData": "dls",
    "ECData": "ec",
    "LabUV_Vis": "uvvis",
    "UVVisData": "uvvis",
    "RamanData": "raman",
    "IRData": "ir",
    "XPSData": "xps",
    "XRDData": "xrd",
    "SAXSData": "saxs1d",
    "WAXSData": "waxs1d",
    "XPCSData": "xpcs_g2",
    "OpticalData": "optical",
    "TomoData": "tomo",
    "EDSData": "eds",
    "XASData": "xas",
    "DFTData": "dos",
}


@dataclass
class ProjectConfig:
    """Everything about a project that is machine- or site-specific."""

    name: str = ""
    description: str = ""
    path_aliases: List[PathAlias] = field(default_factory=list)
    extra_roots: List[str] = field(default_factory=list)
    metadata_sources: List[Dict[str, Any]] = field(default_factory=list)
    modality_dirs: Dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_MODALITY_DIRS)
    )
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "path_aliases": [a.to_dict() for a in self.path_aliases],
            "extra_roots": list(self.extra_roots),
            "metadata_sources": list(self.metadata_sources),
            "modality_dirs": dict(self.modality_dirs),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectConfig":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            path_aliases=[PathAlias.from_dict(a)
                          for a in data.get("path_aliases", [])],
            extra_roots=list(data.get("extra_roots", [])),
            metadata_sources=list(data.get("metadata_sources", [])),
            modality_dirs=dict(data.get("modality_dirs") or DEFAULT_MODALITY_DIRS),
            updated_at=data.get("updated_at", ""),
        )


class Project:
    """A sample collection on disk, with metadata ingest and path resolution.

    Parameters
    ----------
    root : str or Path
        Project directory.  Created if absent.
    name : str, optional
        Display name; defaults to the directory name.
    create : bool
        If False, raise when *root* does not already exist.

    Examples
    --------
    >>> project = Project("/data/MyProject")                  # doctest: +SKIP
    >>> project.add_alias("/instrument/share",            # doctest: +SKIP
    ...                   ["/mnt/instrument"])
    >>> project.ingest("MetaData/Synthesis_dict.py")        # doctest: +SKIP
    >>> project.attach_folders()                                  # doctest: +SKIP
    >>> project.save()                                            # doctest: +SKIP
    >>> table = project.to_dataframe()                            # doctest: +SKIP
    """

    def __init__(self, root: Union[str, Path], name: str = "", create: bool = True):
        self.root = Path(root).expanduser()
        if not self.root.exists():
            if not create:
                raise FileNotFoundError(f"Project root does not exist: {self.root}")
            self.root.mkdir(parents=True, exist_ok=True)

        self.config_dir = self.root / CONFIG_DIR
        self.config_path = self.config_dir / CONFIG_NAME
        self.store_path = self.config_dir / STORE_NAME

        self.samples: Dict[str, Sample] = {}
        self.config = ProjectConfig(name=name or self.root.name)

        self._load_config()
        self._load_store()
        self._resolver: Optional[PathResolver] = None

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, root: Union[str, Path]) -> "Project":
        """Open an existing project directory."""
        return cls(root, create=False)

    def _load_config(self):
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as handle:
                self.config = ProjectConfig.from_dict(json.load(handle))
            if not self.config.name:
                self.config.name = self.root.name

    def _load_store(self):
        if not self.store_path.exists():
            return
        with open(self.store_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        for record in data.get("samples", []):
            sample = Sample.from_dict(record)
            self.samples[sample.sample_id] = sample

    def save(self) -> Path:
        """Write config and sample store; returns the store path."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config.updated_at = datetime.now().isoformat(timespec="seconds")

        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(self.config.to_dict(), handle, indent=2)

        payload = {
            "project": self.config.name,
            "updated_at": self.config.updated_at,
            "samples": [s.to_dict() for s in self.sorted_samples()],
        }
        with open(self.store_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
        return self.store_path

    # ------------------------------------------------------------------
    # path resolution
    # ------------------------------------------------------------------

    @property
    def resolver(self) -> PathResolver:
        """Path resolver built from the project's aliases (cached)."""
        if self._resolver is None:
            self._resolver = PathResolver(
                aliases=list(self.config.path_aliases),
                extra_roots=tuple(self.config.extra_roots),
            )
        return self._resolver

    def add_alias(self, prefix: str, candidates, label: str = "") -> PathAlias:
        """Map a recorded path *prefix* onto local *candidates*."""
        if isinstance(candidates, (str, Path)):
            candidates = [candidates]
        alias = PathAlias(prefix=prefix, candidates=tuple(str(c) for c in candidates),
                          label=label)
        # Replace an alias with the same prefix rather than shadowing it.
        self.config.path_aliases = [
            a for a in self.config.path_aliases if a.prefix != alias.prefix
        ]
        self.config.path_aliases.append(alias)
        self._resolver = None
        return alias

    # ------------------------------------------------------------------
    # samples
    # ------------------------------------------------------------------

    def add_sample(self, sample: Union[Sample, str]) -> Sample:
        """Add a sample (or create an empty one from an id) and return it."""
        if isinstance(sample, str):
            sample = Sample(sample_id=sample)
        existing = self.samples.get(sample.sample_id)
        if existing is None:
            self.samples[sample.sample_id] = sample
            return sample
        return self.merge_sample(sample)

    def merge_sample(self, incoming: Sample) -> Sample:
        """Fold *incoming* into the stored sample with the same id."""
        current = self.samples.get(incoming.sample_id)
        if current is None:
            self.samples[incoming.sample_id] = incoming
            return incoming

        for stage in incoming.stages.values():
            current.add_stage(stage)
        for measurement in incoming.measurements:
            current.add_measurement(measurement)
        for name, entry in incoming.derived.items():
            current.derived[name] = entry
        for tag in incoming.tags:
            if tag not in current.tags:
                current.tags.append(tag)
        if incoming.notes and incoming.notes not in current.notes:
            current.notes = "\n".join(filter(None, [current.notes, incoming.notes]))
        return current

    def get_sample(self, sample_id: str) -> Optional[Sample]:
        return self.samples.get(sample_id)

    def sample_ids(self) -> List[str]:
        return [s.sample_id for s in self.sorted_samples()]

    def sorted_samples(self) -> List[Sample]:
        """Samples in natural id order."""
        return sorted(self.samples.values(), key=lambda s: s.sample_id)

    def __len__(self) -> int:
        return len(self.samples)

    def __iter__(self):
        return iter(self.sorted_samples())

    def __contains__(self, sample_id: object) -> bool:
        return str(sample_id) in self.samples

    # ------------------------------------------------------------------
    # ingest
    # ------------------------------------------------------------------

    def ingest(self, source: Union[str, Path], adapter: str = "auto",
               record: bool = True, **kwargs) -> List[str]:
        """Read an authored metadata file into the sample store.

        Parameters
        ----------
        source : str or Path
            Metadata file, absolute or relative to the project root.
        adapter : str
            Adapter key from :mod:`NanoOrganizer.ingest`, or ``"auto"`` to let
            the registry choose by inspecting the file.
        record : bool
            Remember the source in the project config so it can be re-ingested
            later with :meth:`reingest`.

        Returns
        -------
        list of str
            Ids of the samples that were created or updated.
        """
        from NanoOrganizer.ingest import run_adapter, choose_adapter

        path = Path(source)
        if not path.is_absolute():
            path = self.root / path
        if not path.exists():
            raise FileNotFoundError(f"Metadata source not found: {path}")

        key = adapter if adapter != "auto" else choose_adapter(path)
        samples = run_adapter(key, path, project=self, **kwargs)

        touched = []
        for sample in samples:
            self.merge_sample(sample)
            touched.append(sample.sample_id)

        if record:
            entry = {"path": str(path), "adapter": key, "kwargs": dict(kwargs)}
            self.config.metadata_sources = [
                s for s in self.config.metadata_sources
                if s.get("path") != entry["path"]
            ]
            self.config.metadata_sources.append(entry)
        return touched

    def reingest(self) -> Dict[str, List[str]]:
        """Re-read every recorded metadata source. Returns ``{path: ids}``."""
        out = {}
        for entry in list(self.config.metadata_sources):
            path = entry.get("path", "")
            if not path or not Path(path).exists():
                out[path] = []
                continue
            out[path] = self.ingest(path, adapter=entry.get("adapter", "auto"),
                                    record=False, **entry.get("kwargs", {}))
        return out

    # ------------------------------------------------------------------
    # folder attachment
    # ------------------------------------------------------------------

    def attach_folders(self, base: Union[str, Path, None] = None,
                       create_missing_samples: bool = True,
                       stage: str = "characterization") -> List[Measurement]:
        """Link ``<Modality>Data/<SampleID>/`` folders found under *base*.

        This is how data that was never written into a metadata dict – a folder
        of TEM micrographs dropped in by whoever ran the microscope – joins the
        project without anyone hand-editing a record.

        Parameters
        ----------
        base : path, optional
            Directory holding the modality folders; defaults to the project root.
        create_missing_samples : bool
            Create a bare :class:`Sample` when a folder names an unknown id.
        stage : str
            Stage label applied to the measurements created here.

        Returns
        -------
        list of Measurement
            The measurements that were created or refreshed.
        """
        root = Path(base) if base is not None else self.root
        if not root.is_dir():
            return []

        lookup = {k.lower(): v for k, v in self.config.modality_dirs.items()}
        created: List[Measurement] = []

        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            key = lookup.get(folder.name.lower())
            if key is None:
                key = self._guess_modality(folder.name)
            if key is None:
                continue
            spec = _modality.get(key)
            if spec is None:
                continue

            for sample_dir in sorted(p for p in folder.iterdir() if p.is_dir()):
                sample_id = sample_dir.name
                sample = self.samples.get(sample_id)
                if sample is None:
                    if not create_missing_samples:
                        continue
                    sample = self.add_sample(sample_id)

                files = sorted(
                    str(p) for p in sample_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in spec.extensions
                )
                if not files:
                    continue

                measurement = Measurement(
                    sample_id=sample_id, modality=key, stage=stage,
                    paths=files,
                    meta=self._folder_meta(sample_dir),
                )
                sample.add_measurement(measurement)
                created.append(measurement)

        return created

    # ------------------------------------------------------------------
    # linking data that lives elsewhere
    # ------------------------------------------------------------------

    def link(self, sample_id: str, modality: str, source, **kwargs):
        """Attach data to a sample wherever it lives.

        See :func:`NanoOrganizer.core.linking.link`.  *source* may be a glob
        (kept live), a directory (listed now) or explicit paths; the mount it
        sits on is registered as an alias so the store stays portable.
        """
        from NanoOrganizer.core import linking

        return linking.link(self, sample_id, modality, source, **kwargs)

    def link_folder(self, sample_id: str, modality: str, folder, **kwargs):
        """Link a folder as a live glob. See :func:`linking.link_folder`."""
        from NanoOrganizer.core import linking

        return linking.link_folder(self, sample_id, modality, folder, **kwargs)

    def link_many(self, mapping, **defaults) -> List[Measurement]:
        """Link ``{sample_id: {modality: source}}``. See :func:`linking.link_many`."""
        from NanoOrganizer.core import linking

        return linking.link_many(self, mapping, **defaults)

    def link_table(self, rows, **defaults) -> List[Measurement]:
        """Link from a DataFrame, CSV or list of dicts. See :func:`linking.link_table`."""
        from NanoOrganizer.core import linking

        return linking.link_table(self, rows, **defaults)

    def links_table(self, sample_ids: Sequence[str] = ()) -> List[Dict[str, Any]]:
        """Every link as a row :meth:`link_table` reads back unchanged."""
        from NanoOrganizer.core import linking

        return linking.links_table(self, sample_ids=sample_ids)

    def unlink(self, sample_id: str, modality: str = "", stage: str = "",
               role: str = "") -> List[str]:
        """Drop matching measurements from a sample; returns the ids removed."""
        from NanoOrganizer.core import linking

        return linking.unlink(self, sample_id, modality=modality, stage=stage,
                              role=role)

    def remove_sample(self, sample_id: str) -> bool:
        """Forget a sample entirely. Returns False if it was not there.

        Only the record goes — no file is touched.
        """
        return self.samples.pop(str(sample_id), None) is not None

    def set_params(self, sample_id: str, stage: str = "synthesis",
                   params: Optional[Dict[str, Any]] = None,
                   **fields) -> Stage:
        """Record the conditions a sample was made or measured under.

        Without this an organiser built by linking has files but nothing to
        filter on.  The parameters land in a :class:`Stage` and flatten into
        dotted columns — ``set_params("CuAu05", temperature_C=90)`` becomes
        ``synthesis.temperature_C`` in :meth:`to_dataframe`.

        Promoted stage fields (``run_id``, ``batch_tag``, ``campaign``,
        ``status``, ``started_at``, ``ended_at``, ``run_time_s``, ``error``,
        ``source``) are set on the stage itself; everything else is a
        parameter.  Calling it twice merges rather than replaces.
        """
        sample = self.get_sample(sample_id) or self.add_sample(sample_id)

        promoted = {"run_id", "batch_tag", "campaign", "status", "error",
                    "started_at", "ended_at", "run_time_s", "source"}
        head = {k: v for k, v in fields.items() if k in promoted}
        body = dict(params or {})
        body.update({k: v for k, v in fields.items() if k not in promoted})

        existing = sample.stage(stage)
        if existing is not None:
            for key, value in head.items():
                setattr(existing, key, value)
            existing.params.update(body)
            return existing

        return sample.add_stage(Stage(stage_id=stage, kind=stage,
                                      params=body, **head))

    def _guess_modality(self, folder_name: str) -> Optional[str]:
        """Resolve a folder name like ``RamanData`` to a modality key."""
        name = folder_name.lower()
        for suffix in ("data", "_data", "-data"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        return _modality.resolve_key(name)

    @staticmethod
    def _folder_meta(sample_dir: Path) -> Dict[str, Any]:
        """Collect side-car notes sitting beside a folder of data files."""
        meta: Dict[str, Any] = {"folder": str(sample_dir)}
        for note_name in ("note.txt", "notes.txt", "README.txt", "readme.txt"):
            note = sample_dir / note_name
            if note.exists():
                try:
                    meta["note"] = note.read_text(encoding="utf-8").strip()
                except OSError:
                    pass
                break
        return meta

    # ------------------------------------------------------------------
    # querying
    # ------------------------------------------------------------------

    def measurements(self, modality: str = "", stage: str = "",
                     group: str = "", role: str = "",
                     sample_ids: Sequence[str] = ()) -> List[Measurement]:
        """Every matching measurement across the selected samples."""
        wanted = set(sample_ids) if sample_ids else None
        out = []
        for sample in self.sorted_samples():
            if wanted is not None and sample.sample_id not in wanted:
                continue
            out.extend(sample.get_measurements(modality=modality, stage=stage,
                                               group=group, role=role))
        return out

    def modalities(self) -> List[str]:
        """Distinct modality keys present anywhere in the project."""
        keys: List[str] = []
        for sample in self.sorted_samples():
            for key in sample.modalities:
                if key not in keys:
                    keys.append(key)
        return keys

    def groups(self) -> List[str]:
        """Visualisation groups present in the project, in canonical order."""
        return _modality.groups_present(self.modalities())

    def to_dataframe(self, level: str = "sample", sample_ids: Sequence[str] = ()):
        """Build the flat table the Explore & Filter page is driven from.

        Parameters
        ----------
        level : {"sample", "measurement"}
            One row per sample (authored parameters plus derived values), or
            one row per measurement (modality, stage, file counts).
        sample_ids : sequence of str, optional
            Restrict to these samples.
        """
        import pandas as pd

        chosen = [s for s in self.sorted_samples()
                  if not sample_ids or s.sample_id in set(sample_ids)]

        if level == "sample":
            rows = [s.flatten() for s in chosen]
            frame = pd.DataFrame(rows)
            # A sample with no TEM has ``has.tem == False``, not NaN: the
            # filter widgets need a real boolean to offer a checkbox on.
            for column in frame.columns:
                if column.startswith("has."):
                    frame[column] = frame[column].fillna(False).astype(bool)
                elif column.startswith("n_files."):
                    frame[column] = frame[column].fillna(0).astype(int)
            if "sample_id" in frame.columns:
                frame = frame.set_index("sample_id", drop=False)
            return frame

        if level == "measurement":
            rows = []
            for sample in chosen:
                for m in sample.measurements:
                    spec = m.spec
                    rows.append({
                        "sample_id": sample.sample_id,
                        "measurement_id": m.measurement_id,
                        "modality": m.modality,
                        "modality_label": spec.label if spec else m.modality,
                        "group": m.group,
                        "stage": m.stage,
                        "role": m.role,
                        "label": m.label,
                        "n_paths": len(m.paths),
                        "pattern": m.pattern,
                        "timestamp": m.timestamp,
                    })
            return pd.DataFrame(rows)

        raise ValueError(f"level must be 'sample' or 'measurement', got {level!r}")

    def filter(self, predicate: Optional[Callable[[Sample], bool]] = None,
               **equals) -> List[str]:
        """Return sample ids matching *predicate* and/or flat column equality.

        ``project.filter(**{"synthesis.conditions.temperature_C": 6.0})``
        selects on an authored parameter without building a dataframe first.
        """
        out = []
        for sample in self.sorted_samples():
            if predicate is not None and not predicate(sample):
                continue
            if equals:
                row = sample.flatten()
                if any(row.get(key) != value for key, value in equals.items()):
                    continue
            out.append(sample.sample_id)
        return out

    # ------------------------------------------------------------------
    # reporting
    # ------------------------------------------------------------------

    def availability(self) -> Dict[str, Any]:
        """Summarise what fraction of the project's data is readable here."""
        resolver = self.resolver
        per_sample = [s.availability(resolver) for s in self.sorted_samples()]
        total = sum(r["n_measurements"] for r in per_sample)
        found = sum(r["n_available"] for r in per_sample)
        return {
            "project": self.config.name,
            "n_samples": len(self.samples),
            "n_measurements": total,
            "n_available": found,
            "n_unresolved": total - found,
            "samples": per_sample,
        }

    def summary(self) -> str:
        """One-paragraph human summary, handy in a notebook."""
        report = self.availability()
        modalities = ", ".join(self.modalities()) or "none"
        return (
            f"{self.config.name}: {report['n_samples']} samples, "
            f"{report['n_measurements']} measurements "
            f"({report['n_available']} readable here, "
            f"{report['n_unresolved']} not mounted).\n"
            f"Modalities: {modalities}\n"
            f"Root: {self.root}"
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Project({self.config.name!r}, {len(self.samples)} samples)"


__all__ = ["Project", "ProjectConfig", "DEFAULT_MODALITY_DIRS"]
