#!/usr/bin/env python3
"""
Sample-centric schema: Sample → Stages + Measurements + Derived.

The organising principle is that a *sample* is the thing that persists.  One
sample is synthesised once, may be used in several reactions, and is
characterised repeatedly over weeks by different instruments.  Keying on a
stable ``SampleNNNNNN`` therefore survives re-measurement, while keying on a
run does not.

Each execution that produced or consumed the sample is a :class:`Stage` – it
keeps its own ``run_id``, batch provenance, status and the full parameter dict
exactly as it was authored, so nothing is lost in translation.  Every file or
glob the sample owns is a :class:`Measurement`, tagged with a modality from
:mod:`NanoOrganizer.core.modality` and the stage it belongs to.

Values computed later (peak position, rate constant, mean particle diameter)
are written back into :attr:`Sample.derived` as :class:`DerivedValue` records,
which is what makes them filterable alongside the authored parameters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from NanoOrganizer.core import modality as _modality

# Conventional stage kinds.  Not an enum: a project may invent its own.
STAGE_SYNTHESIS = "synthesis"
STAGE_REACTION = "reaction"
STAGE_CHARACTERIZATION = "characterization"

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def _slug(text: object, fallback: str = "x") -> str:
    """Lowercase, hyphen-separated slug suitable for an identifier."""
    out = _SLUG_RE.sub("-", str(text or "")).strip("-").lower()
    return out or fallback


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

@dataclass
class Measurement:
    """One body of data belonging to a sample.

    A measurement references files without reading them.  It may hold explicit
    ``paths``, a ``pattern`` glob, or both; ``aux`` carries companion files
    that are not data frames themselves (a wavelength axis, a mask, a
    calibration).  Paths are stored exactly as recorded and resolved at read
    time by :class:`~NanoOrganizer.core.pathmap.PathResolver`.

    Attributes
    ----------
    modality : str
        Key into :data:`~NanoOrganizer.core.modality.MODALITY_REGISTRY`.
    stage : str
        Which stage produced it, e.g. ``"synthesis"`` or ``"catalysis"``.
    role : str
        Free-form sub-label within a stage, e.g. ``"kinetic"``, ``"static"``.
    meta : dict
        Instrument and acquisition metadata, kept verbatim.
    """

    sample_id: str
    modality: str
    stage: str = ""
    role: str = ""
    label: str = ""
    paths: List[str] = field(default_factory=list)
    pattern: str = ""
    aux: Dict[str, str] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None
    measurement_id: str = ""

    def __post_init__(self):
        self.modality = _modality.resolve_key(self.modality) or str(self.modality)
        if not self.measurement_id:
            self.measurement_id = self.make_id(
                self.sample_id, self.modality, self.stage, self.role
            )
        if not self.label:
            spec = _modality.get(self.modality)
            base = spec.label if spec else self.modality
            parts = [p for p in (self.stage, self.role) if p]
            self.label = f"{base} ({', '.join(parts)})" if parts else base

    # -- identity -------------------------------------------------------

    @staticmethod
    def make_id(sample_id: str, modality: str, stage: str = "", role: str = "") -> str:
        """Build a stable, readable measurement id."""
        tail = "-".join(_slug(p) for p in (stage, role) if p)
        return f"{sample_id}:{_slug(modality)}" + (f":{tail}" if tail else "")

    # -- modality -------------------------------------------------------

    @property
    def spec(self) -> Optional[_modality.Modality]:
        """The :class:`Modality` describing this measurement, if registered."""
        return _modality.get(self.modality)

    @property
    def group(self) -> str:
        """Visualisation group: curve / image / volume / correlation."""
        spec = self.spec
        return spec.group if spec else "curve"

    # -- files ----------------------------------------------------------

    def recorded_paths(self) -> List[str]:
        """Every recorded path, explicit files first then the pattern."""
        out = list(self.paths)
        if self.pattern:
            out.append(self.pattern)
        return out

    def resolve(self, resolver) -> List:
        """Return local paths for this measurement via *resolver*.

        Explicit paths are resolved individually; the pattern is expanded as a
        glob.  Missing entries are skipped – use :meth:`availability` to find
        out what could not be found.
        """
        found = []
        for path in self.paths:
            hit = resolver.resolve(path)
            if hit is not None:
                found.append(hit)
        if self.pattern:
            found.extend(resolver.resolve_glob(self.pattern))
        # Preserve order while removing duplicates.
        return list(dict.fromkeys(found))

    def resolve_aux(self, resolver) -> Dict[str, Any]:
        """Resolve the companion files in :attr:`aux`, dropping missing ones."""
        out = {}
        for name, path in self.aux.items():
            hit = resolver.resolve(path)
            if hit is not None:
                out[name] = hit
        return out

    def availability(self, resolver) -> Dict[str, Any]:
        """Report how much of this measurement is readable on this machine."""
        files = self.resolve(resolver)
        missing = [p for p in self.paths if resolver.resolve(p) is None]
        if self.pattern and not resolver.resolve_glob(self.pattern):
            missing.append(self.pattern)
        return {
            "measurement_id": self.measurement_id,
            "n_files": len(files),
            "missing": missing,
            "available": bool(files),
        }

    # -- serialisation --------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Measurement":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------

@dataclass
class Stage:
    """One execution in a sample's history (a synthesis, a reaction, a session).

    The authored parameter dictionary is kept whole in :attr:`params`; the
    named fields are a promoted subset used for sorting and filtering, so that
    a project with an unusual schema still round-trips without loss.
    """

    stage_id: str
    kind: str = ""
    run_id: str = ""
    batch_tag: str = ""
    campaign: str = ""
    status: str = ""
    error: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    run_time_s: Optional[float] = None
    params: Dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def __post_init__(self):
        if not self.kind:
            self.kind = self.stage_id

    @property
    def ok(self) -> bool:
        """True unless the stage recorded a failure."""
        return self.status not in {"error", "aborted", "failed"} and not self.error

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Stage":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------

@dataclass
class DerivedValue:
    """A quantity computed from data, stored so it can be filtered and plotted.

    Keeping ``analysis``, ``source`` and ``computed_at`` alongside the value is
    what separates a reproducible derived column from a stray number: it says
    which routine produced it and from which measurement.
    """

    name: str
    value: Any
    unit: str = ""
    error: Optional[float] = None
    analysis: str = ""
    source: str = ""           # measurement_id it came from
    params: Dict[str, Any] = field(default_factory=dict)
    computed_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DerivedValue":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Sample
# ---------------------------------------------------------------------------

@dataclass
class Sample:
    """The primary record: one physical sample and everything known about it."""

    sample_id: str
    stages: Dict[str, Stage] = field(default_factory=dict)
    measurements: List[Measurement] = field(default_factory=list)
    derived: Dict[str, DerivedValue] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=_now)

    # -- stages ---------------------------------------------------------

    def add_stage(self, stage: Stage, merge: bool = True) -> Stage:
        """Attach *stage*; merging into an existing one of the same id by default."""
        existing = self.stages.get(stage.stage_id)
        if existing is not None and merge:
            merged = dict(existing.params)
            merged.update(stage.params)
            stage.params = merged
        self.stages[stage.stage_id] = stage
        return stage

    def stage(self, stage_id: str) -> Optional[Stage]:
        return self.stages.get(stage_id)

    # -- measurements ---------------------------------------------------

    def add_measurement(self, measurement: Measurement,
                        replace_existing: bool = True) -> Measurement:
        """Attach *measurement*, replacing any with the same id by default."""
        if measurement.sample_id and measurement.sample_id != self.sample_id:
            raise ValueError(
                f"Measurement belongs to {measurement.sample_id!r}, "
                f"not {self.sample_id!r}"
            )
        measurement.sample_id = self.sample_id
        for index, existing in enumerate(self.measurements):
            if existing.measurement_id == measurement.measurement_id:
                if not replace_existing:
                    return existing
                self.measurements[index] = measurement
                return measurement
        self.measurements.append(measurement)
        return measurement

    def get_measurements(self, modality: str = "", stage: str = "",
                         group: str = "", role: str = "") -> List[Measurement]:
        """Filter this sample's measurements on any combination of fields."""
        wanted = _modality.resolve_key(modality) if modality else ""
        out = []
        for m in self.measurements:
            if wanted and m.modality != wanted:
                continue
            if stage and m.stage != stage:
                continue
            if role and m.role != role:
                continue
            if group and m.group != group:
                continue
            out.append(m)
        return out

    def get_measurement(self, measurement_id: str) -> Optional[Measurement]:
        for m in self.measurements:
            if m.measurement_id == measurement_id:
                return m
        return None

    @property
    def modalities(self) -> List[str]:
        """Distinct modality keys present, in first-seen order."""
        return list(dict.fromkeys(m.modality for m in self.measurements))

    # -- derived --------------------------------------------------------

    def set_derived(self, name: str, value: Any, **kwargs) -> DerivedValue:
        """Record a computed quantity under *name*."""
        entry = DerivedValue(name=name, value=value, **kwargs)
        self.derived[name] = entry
        return entry

    def get_derived(self, name: str, default: Any = None) -> Any:
        """Return the stored *value* for *name* (not the wrapper)."""
        entry = self.derived.get(name)
        return entry.value if entry is not None else default

    # -- availability ---------------------------------------------------

    def availability(self, resolver) -> Dict[str, Any]:
        """Summarise which of this sample's measurements are readable."""
        reports = [m.availability(resolver) for m in self.measurements]
        return {
            "sample_id": self.sample_id,
            "n_measurements": len(reports),
            "n_available": sum(1 for r in reports if r["available"]),
            "measurements": reports,
        }

    # -- serialisation --------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "measurements": [m.to_dict() for m in self.measurements],
            "derived": {k: v.to_dict() for k, v in self.derived.items()},
            "tags": list(self.tags),
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Sample":
        return cls(
            sample_id=data["sample_id"],
            stages={k: Stage.from_dict(v) for k, v in data.get("stages", {}).items()},
            measurements=[Measurement.from_dict(m)
                          for m in data.get("measurements", [])],
            derived={k: DerivedValue.from_dict(v)
                     for k, v in data.get("derived", {}).items()},
            tags=list(data.get("tags", [])),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", _now()),
        )

    # -- flattening -----------------------------------------------------

    def flatten(self, max_depth: int = 6) -> Dict[str, Any]:
        """Return one flat ``{column: value}`` row describing this sample.

        Nested stage parameters become dotted columns such as
        ``synthesis.conditions.temperature_C``.  This is
        the row the Explore & Filter table is built from.
        """
        row: Dict[str, Any] = {"sample_id": self.sample_id}

        for stage_id, stage in self.stages.items():
            row[f"{stage_id}.run_id"] = stage.run_id
            row[f"{stage_id}.batch_tag"] = stage.batch_tag
            row[f"{stage_id}.campaign"] = stage.campaign
            row[f"{stage_id}.status"] = stage.status
            row[f"{stage_id}.started_at"] = stage.started_at
            row[f"{stage_id}.run_time_s"] = stage.run_time_s
            row[f"{stage_id}.ok"] = stage.ok
            row.update(flatten_dict(stage.params, prefix=stage_id,
                                    max_depth=max_depth))

        for name, entry in self.derived.items():
            row[f"derived.{name}"] = entry.value
            if entry.error is not None:
                row[f"derived.{name}.error"] = entry.error

        row["n_measurements"] = len(self.measurements)
        for key in self.modalities:
            row[f"has.{key}"] = True
            row[f"n_files.{key}"] = sum(
                len(m.paths) for m in self.get_measurements(modality=key)
            )
        row["modalities"] = ", ".join(self.modalities)
        row["tags"] = ", ".join(self.tags)
        if self.notes:
            row["notes"] = self.notes
        return row


# ---------------------------------------------------------------------------
# Flattening helper
# ---------------------------------------------------------------------------

def flatten_dict(data: Any, prefix: str = "", sep: str = ".",
                 max_depth: int = 6, _depth: int = 0) -> Dict[str, Any]:
    """Flatten nested dicts into dotted keys, leaving scalars untouched.

    Lists of scalars are joined into a string so they survive a dataframe
    round-trip; lists of dicts are indexed (``key.0.field``).  Recursion stops
    at *max_depth* and stores whatever remains as a repr, so a pathological
    structure cannot blow up the table.
    """
    out: Dict[str, Any] = {}
    if not isinstance(data, dict):
        if prefix:
            out[prefix] = data
        return out

    for key, value in data.items():
        column = f"{prefix}{sep}{key}" if prefix else str(key)
        if isinstance(value, dict):
            if _depth >= max_depth:
                out[column] = repr(value)
            else:
                out.update(flatten_dict(value, column, sep, max_depth, _depth + 1))
        elif isinstance(value, (list, tuple)):
            if value and all(isinstance(v, dict) for v in value):
                for index, item in enumerate(value):
                    out.update(flatten_dict(item, f"{column}{sep}{index}",
                                            sep, max_depth, _depth + 1))
            else:
                out[column] = ", ".join(str(v) for v in value)
        else:
            out[column] = value
    return out


__all__ = [
    "Sample", "Stage", "Measurement", "DerivedValue", "flatten_dict",
    "STAGE_SYNTHESIS", "STAGE_REACTION", "STAGE_CHARACTERIZATION",
]
