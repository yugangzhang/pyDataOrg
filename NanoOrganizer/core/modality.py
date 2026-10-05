#!/usr/bin/env python3
"""
Modality registry – what a measurement technique *is*, declaratively.

The visualisation layer must not grow a new code path every time a new
technique arrives.  It therefore dispatches on two technique-independent
axes:

``domain``
    What the independent variable is: ``wavelength``, ``wavenumber``, ``q``,
    ``energy``, ``two_theta``, ``size``, ``time``, ``lag_time``, ``space``,
    ``potential``.

``shape``
    How the values are arranged: ``curve`` (1D), ``series`` (1D repeated over
    time), ``image`` (2D), ``map`` (2D non-image), ``volume`` (3D),
    ``stack`` (3D as frames), ``corr`` (correlation function).

A *modality* (uvvis, raman, tem, …) is then only a label plus defaults:
axis captions, units, the plot to draw first, and which analyses apply.
Adding a technique is one :func:`register` call – no new GUI page.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

GROUPS = ("curve", "image", "volume", "correlation")

SHAPE_GROUP = {
    "curve": "curve",
    "series": "curve",
    "image": "image",
    "map": "image",
    "volume": "volume",
    "stack": "volume",
    "corr": "correlation",
    "twotime": "correlation",
}

GROUP_LABELS = {
    "curve": "Curves (1D)",
    "image": "Images & Maps (2D)",
    "volume": "Volumes (3D)",
    "correlation": "Correlation",
}


@dataclass(frozen=True)
class Modality:
    """Declarative description of one measurement technique.

    Attributes
    ----------
    key : str
        Registry key, also the value stored in ``Measurement.modality``.
    label : str
        Human-readable name shown in the GUI.
    domain, shape : str
        The two dispatch axes described in the module docstring.
    x_label, y_label : str
        Default axis captions (already include units where useful).
    log_x, log_y : bool
        Default axis scaling.
    extensions : tuple of str
        File suffixes that plausibly belong to this modality, used by
        folder auto-attachment.
    analyses : tuple of str
        Keys of analyses that may be run on this modality.
    category : str
        Free-form grouping for the GUI sub-selector ("spectroscopy",
        "scattering", "microscopy", "sizing", "electrochemistry").
    """

    key: str
    label: str
    domain: str
    shape: str
    x_label: str = ""
    y_label: str = ""
    log_x: bool = False
    log_y: bool = False
    extensions: Tuple[str, ...] = ()
    analyses: Tuple[str, ...] = ()
    category: str = "other"
    aliases: Tuple[str, ...] = field(default=())

    @property
    def group(self) -> str:
        """Visualisation group implied by :attr:`shape`."""
        return SHAPE_GROUP.get(self.shape, "curve")

    @property
    def is_1d(self) -> bool:
        return self.group == "curve"

    def to_dict(self) -> dict:
        data = {
            "key": self.key,
            "label": self.label,
            "domain": self.domain,
            "shape": self.shape,
            "group": self.group,
            "category": self.category,
        }
        return data


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MODALITY_REGISTRY: Dict[str, Modality] = {}
_ALIASES: Dict[str, str] = {}


def register(modality: Modality, overwrite: bool = False) -> Modality:
    """Add *modality* to the registry and return it.

    Raises
    ------
    ValueError
        If the key already exists and *overwrite* is False, or if the
        declared ``shape`` is unknown.
    """
    if modality.shape not in SHAPE_GROUP:
        raise ValueError(
            f"Unknown shape {modality.shape!r} for modality {modality.key!r}; "
            f"expected one of {sorted(SHAPE_GROUP)}"
        )
    if modality.key in MODALITY_REGISTRY and not overwrite:
        raise ValueError(f"Modality {modality.key!r} is already registered")

    MODALITY_REGISTRY[modality.key] = modality
    _ALIASES[modality.key.lower()] = modality.key
    for alias in modality.aliases:
        _ALIASES[alias.lower()] = modality.key
    return modality


def get(key: str, default: Optional[Modality] = None) -> Optional[Modality]:
    """Look up a modality by key or alias (case-insensitive)."""
    if not key:
        return default
    resolved = _ALIASES.get(str(key).strip().lower())
    if resolved is None:
        return default
    return MODALITY_REGISTRY[resolved]


def resolve_key(key: str) -> Optional[str]:
    """Return the canonical registry key for *key*, or None."""
    modality = get(key)
    return modality.key if modality else None


def list_modalities(group: str = "", category: str = "") -> List[Modality]:
    """Return registered modalities, optionally filtered by group/category."""
    items = sorted(MODALITY_REGISTRY.values(), key=lambda m: (m.category, m.label))
    if group:
        items = [m for m in items if m.group == group]
    if category:
        items = [m for m in items if m.category == category]
    return items


def groups_present(keys: Iterable[str]) -> List[str]:
    """Return the visualisation groups spanned by *keys*, in GROUPS order."""
    found = set()
    for key in keys:
        modality = get(key)
        if modality:
            found.add(modality.group)
    return [g for g in GROUPS if g in found]


def variant(key: str, new_key: str, **changes) -> Modality:
    """Register a copy of *key* under *new_key* with fields overridden.

    Useful for a technique that differs from an existing one only in its
    axis captions, e.g. a second Raman laser line.
    """
    base = get(key)
    if base is None:
        raise KeyError(f"Unknown modality {key!r}")
    return register(replace(base, key=new_key, aliases=(), **changes))


# ---------------------------------------------------------------------------
# Built-in modalities
# ---------------------------------------------------------------------------

_BUILTINS = [
    # --- spectroscopy (1D) -------------------------------------------------
    Modality(
        key="uvvis", label="UV-Vis", domain="wavelength", shape="series",
        x_label="Wavelength (nm)", y_label="Absorbance",
        extensions=(".npy", ".csv", ".txt", ".dat"),
        analyses=("peak_fit", "uvvis_kinetics"),
        category="spectroscopy", aliases=("uv", "uv_vis", "uv-vis", "labuv_vis"),
    ),
    Modality(
        key="raman", label="Raman", domain="wavenumber", shape="curve",
        x_label="Raman shift (cm$^{-1}$)", y_label="Intensity (a.u.)",
        extensions=(".txt", ".csv", ".dat", ".spc"),
        analyses=("peak_fit",), category="spectroscopy",
    ),
    Modality(
        key="ir", label="IR / FTIR", domain="wavenumber", shape="curve",
        x_label="Wavenumber (cm$^{-1}$)", y_label="Absorbance",
        extensions=(".txt", ".csv", ".dat", ".dpt"),
        analyses=("peak_fit",), category="spectroscopy", aliases=("ftir",),
    ),
    Modality(
        key="xps", label="XPS", domain="energy", shape="curve",
        x_label="Binding energy (eV)", y_label="Counts (a.u.)",
        extensions=(".txt", ".csv", ".vms"),
        analyses=("peak_fit",), category="spectroscopy",
    ),
    Modality(
        key="xas", label="XAS", domain="energy", shape="series",
        x_label="Energy (eV)", y_label="Normalised absorption",
        extensions=(".txt", ".csv", ".dat"),
        analyses=("peak_fit", "curve_metrics"), category="spectroscopy",
        aliases=("xanes", "exafs"),
    ),
    Modality(
        key="eds", label="EDS / EDX", domain="energy", shape="curve",
        x_label="Energy (keV)", y_label="Counts",
        extensions=(".txt", ".csv", ".dat", ".msa", ".emsa", ".spc"),
        analyses=("peak_fit", "curve_metrics"), category="spectroscopy",
        aliases=("edx", "edxs", "eds_spectrum"),
    ),
    # --- scattering --------------------------------------------------------
    Modality(
        key="saxs1d", label="SAXS 1D", domain="q", shape="series",
        x_label="q (Å$^{-1}$)", y_label="I(q) (a.u.)", log_x=True, log_y=True,
        extensions=(".dat", ".txt", ".csv", ".npz"),
        analyses=("peak_fit",), category="scattering", aliases=("saxs",),
    ),
    Modality(
        key="waxs1d", label="WAXS 1D", domain="q", shape="series",
        x_label="q (Å$^{-1}$)", y_label="I(q) (a.u.)", log_y=True,
        extensions=(".dat", ".txt", ".csv", ".npz"),
        analyses=("peak_fit",), category="scattering", aliases=("waxs",),
    ),
    Modality(
        key="xrd", label="XRD", domain="two_theta", shape="curve",
        x_label="2θ (deg)", y_label="Intensity (a.u.)",
        extensions=(".xy", ".txt", ".csv", ".dat"),
        analyses=("peak_fit",), category="scattering",
    ),
    Modality(
        key="saxs2d", label="SAXS 2D", domain="q", shape="image",
        x_label="q$_x$ (Å$^{-1}$)", y_label="q$_y$ (Å$^{-1}$)", log_y=False,
        extensions=(".tif", ".tiff", ".npy", ".npz", ".h5"),
        category="scattering",
    ),
    Modality(
        key="waxs2d", label="WAXS 2D", domain="q", shape="image",
        x_label="q$_x$ (Å$^{-1}$)", y_label="q$_y$ (Å$^{-1}$)",
        extensions=(".tif", ".tiff", ".npy", ".npz", ".h5"),
        category="scattering",
    ),
    Modality(
        key="giwaxs", label="GISAXS / GIWAXS", domain="q", shape="image",
        x_label="q$_r$ (Å$^{-1}$)", y_label="q$_z$ (Å$^{-1}$)",
        extensions=(".tif", ".tiff", ".npy", ".npz", ".h5"),
        category="scattering", aliases=("gisaxs", "gi"),
    ),
    # --- correlation -------------------------------------------------------
    Modality(
        key="xpcs_g2", label="XPCS g₂", domain="lag_time", shape="corr",
        x_label="Lag time τ (s)", y_label="g$_2$(τ)", log_x=True,
        extensions=(".csv", ".h5", ".npy"),
        analyses=("peak_fit",), category="correlation", aliases=("xpcs", "g2"),
    ),
    Modality(
        key="xpcs_twotime", label="XPCS two-time", domain="time", shape="twotime",
        x_label="t$_1$ (s)", y_label="t$_2$ (s)",
        extensions=(".h5", ".npy", ".npz"),
        category="correlation", aliases=("twotime", "two_time"),
    ),
    # --- sizing / electro --------------------------------------------------
    Modality(
        key="dls", label="DLS", domain="size", shape="curve",
        x_label="Hydrodynamic diameter (nm)", y_label="Intensity (%)",
        log_x=True, extensions=(".csv", ".txt", ".dat"),
        analyses=("peak_fit",), category="sizing",
    ),
    Modality(
        key="ec", label="Electrochemistry", domain="potential", shape="curve",
        x_label="Potential (V vs RHE)", y_label="j (mA cm$^{-2}$)",
        extensions=(".csv", ".txt", ".dat", ".dta"),
        analyses=("curve_metrics",), category="electrochemistry",
        aliases=("echem", "cv", "lsv"),
    ),
    # --- computation -------------------------------------------------------
    Modality(
        key="dos", label="DFT DOS / PDOS", domain="energy", shape="curve",
        x_label="E − E$_F$ (eV)", y_label="States eV$^{-1}$ atom$^{-1}$",
        extensions=(".dat", ".txt", ".csv"),
        analyses=("curve_metrics", "peak_fit"), category="computation",
        aliases=("pdos", "ldos", "dft", "dft_dos"),
    ),
    # --- microscopy (2D) ---------------------------------------------------
    Modality(
        key="tem", label="TEM", domain="space", shape="image",
        x_label="x (px)", y_label="y (px)",
        extensions=(".tif", ".tiff", ".dm3", ".dm4", ".png", ".jpg"),
        analyses=("particle_sizing",), category="microscopy",
    ),
    Modality(
        key="sem", label="SEM", domain="space", shape="image",
        x_label="x (px)", y_label="y (px)",
        extensions=(".tif", ".tiff", ".png", ".jpg"),
        analyses=("particle_sizing",), category="microscopy",
    ),
    Modality(
        key="optical", label="Optical microscopy", domain="space", shape="image",
        x_label="x (px)", y_label="y (px)",
        extensions=(".tif", ".tiff", ".png", ".jpg", ".jpeg"),
        analyses=("particle_sizing",), category="microscopy",
    ),
    Modality(
        key="cell", label="Cell imaging", domain="space", shape="image",
        x_label="x (px)", y_label="y (px)",
        extensions=(".tif", ".tiff", ".png", ".nd2", ".lif"),
        analyses=("particle_sizing",), category="microscopy",
    ),
    # --- microscopy (3D) ---------------------------------------------------
    Modality(
        key="tomo", label="Tomography", domain="space", shape="volume",
        x_label="x (px)", y_label="y (px)",
        extensions=(".h5", ".npy", ".npz", ".tif", ".tiff", ".mrc"),
        category="microscopy", aliases=("tomography", "ct"),
    ),
    Modality(
        key="zstack", label="Z-stack", domain="space", shape="stack",
        x_label="x (px)", y_label="y (px)",
        extensions=(".tif", ".tiff", ".h5", ".npy"),
        category="microscopy",
    ),
]

for _modality in _BUILTINS:
    register(_modality)


def modality_for_extension(suffix: str, category: str = "") -> List[Modality]:
    """Return modalities that claim the file *suffix* (e.g. ``".tif"``)."""
    suffix = suffix.lower()
    if not suffix.startswith("."):
        suffix = "." + suffix
    return [
        m for m in list_modalities(category=category)
        if suffix in m.extensions
    ]


__all__ = [
    "Modality", "MODALITY_REGISTRY", "GROUPS", "GROUP_LABELS", "SHAPE_GROUP",
    "register", "get", "resolve_key", "list_modalities", "groups_present",
    "variant", "modality_for_extension",
]
