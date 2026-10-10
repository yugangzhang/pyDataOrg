#!/usr/bin/env python3
"""
The physical model behind the multimodal demo: a Cu–Au alloy nanocatalyst library.

Everything the showcase project contains is derived from **one hidden control
variable**, the gold atomic fraction ``x`` of the alloy.  Fifteen techniques
then see fifteen different shadows of that one number, which is the point of
the demo: a framework is only worth having if measurements taken on different
instruments can be brought back together and shown to agree.

Why Cu–Au
---------
Cu and Au form a continuous fcc solid solution at every composition, so a
composition series is a real material rather than a thought experiment, and the
textbook consequences are all available at once:

* the lattice parameter follows **Vegard's law**, so a diffraction peak
  position measures composition;
* the particles keep **one** plasmon band that moves smoothly from ~580 nm
  (Cu) to ~520 nm (Au) — the classic evidence that an alloy formed rather than
  a mixture of two kinds of particle, which would show two bands;
* gold segregates to the surface, so XPS (surface-sensitive) and EDS (bulk)
  disagree in a way that is informative rather than an error;
* CO₂ reduction selectivity switches from hydrocarbons on Cu to CO on Au, and
  the CO *partial current* peaks at an intermediate composition — a Sabatier
  volcano, with the DFT CO binding energy as its descriptor.

The numbers below are plausible literature values, rounded.  They are good
enough to be instructive and are **not** a substitute for real measurement.

All functions here take ``x`` (the gold atomic fraction, 0–1) and are the
ground truth: :func:`showcase_truth` tabulates them so a notebook can check
what the pipeline recovered against what the generator actually used.
"""

from __future__ import annotations

from typing import Dict, Sequence

import numpy as np

#: Gold atomic fractions of the default library, one sample each.
DEFAULT_FRACTIONS = (0.0, 0.10, 0.25, 0.40, 0.55, 0.70, 0.85, 1.0)

#: Lattice parameters of the pure metals, Å.
A_CU, A_AU = 3.6150, 4.0782

#: Products tracked in the CO₂-reduction Faradaic-efficiency measurement.
PRODUCTS = ("H2", "CO", "HCOO-", "CH4", "C2H4", "EtOH")

#: Potential of the reported performance summary, V vs RHE.
REPORT_POTENTIAL_V = -1.0


def sample_id(index: int) -> str:
    """Stable identifier for the *index*-th sample (1-based)."""
    return f"CuAu{index:02d}"


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def lattice_parameter_A(x: float) -> float:
    """Vegard's law between the two pure fcc metals."""
    return A_CU + x * (A_AU - A_CU)


def particle_diameter_nm(x: float) -> float:
    """Mean projected diameter seen by TEM.

    Gold-rich syntheses nucleate less and grow larger, which is why the size
    and the composition move together — a confound the Compare page is meant
    to help you notice rather than one the demo hides.
    """
    return 8.5 + 5.5 * x


def crystallite_nm(x: float) -> float:
    """Volume-weighted crystallite size from line broadening.

    Smaller than the particle because the particles are polycrystalline.
    """
    return 0.72 * particle_diameter_nm(x)


def hydrodynamic_nm(x: float) -> float:
    """Intensity-weighted hydrodynamic diameter seen by DLS.

    Larger than TEM: the ligand shell, the solvation layer, and the heavy
    weighting DLS gives to the few largest objects all push it up.
    """
    return 1.9 * particle_diameter_nm(x) + 6.0


def aggregate_nm(x: float) -> float:
    """Size of the loose aggregates the ink forms, probed by XPCS."""
    return 180.0 + 40.0 * x


def size_dispersity(x: float) -> float:
    """Log-normal width of the size distribution."""
    return 0.14 + 0.04 * x


# ---------------------------------------------------------------------------
# Optical and electronic structure
# ---------------------------------------------------------------------------

def lspr_nm(x: float) -> float:
    """Plasmon band position, nm.

    Linear between the two metals with a small bowing term, which is what an
    alloy — as opposed to a physical mixture — actually does.
    """
    return 580.0 - 60.0 * x + 12.0 * x * (1.0 - x)


def lspr_fwhm_nm(x: float) -> float:
    """Plasmon width, nm. Widest at 50:50, where alloy damping is strongest."""
    return 70.0 + 55.0 * x * (1.0 - x)


def d_band_centre_eV(x: float) -> float:
    """Surface d-band centre relative to the Fermi level, eV (DFT)."""
    return -2.67 - 0.89 * x


def co_binding_eV(x: float) -> float:
    """*CO adsorption energy on the (211) step, eV. Negative is bound."""
    return -0.62 + 0.26 * x


def h_binding_eV(x: float) -> float:
    """*H adsorption energy, eV. Rising with Au is why Au suppresses HER."""
    return -0.36 + 0.52 * x


def co_stretch_cm1(x: float) -> float:
    """Atop-bound C–O stretching frequency seen by surface-enhanced IR."""
    return 2092.0 + 20.0 * x


def sers_enhancement(x: float) -> float:
    """Raman enhancement factor relative to Cu, from the Au plasmon."""
    return 1.0 + 4.0 * x


# ---------------------------------------------------------------------------
# Surface chemistry
# ---------------------------------------------------------------------------

def surface_au_fraction(x: float) -> float:
    """Gold fraction of the outermost layers, as XPS sees it.

    Gold has the lower surface energy and segregates outwards, so the surface
    is always richer in Au than the bulk.  XPS and EDS *should* disagree here.
    """
    return float(np.clip(x + 0.18 * np.sin(np.pi * x), 0.0, 1.0))


def oxide_fraction(x: float) -> float:
    """Fraction of the copper that is oxidised in the as-made sample.

    Gold passivates the surface against air oxidation, so this falls as x
    rises; with no copper left there is nothing to oxidise.
    """
    return float(np.clip(0.42 * (1.0 - x) ** 1.4, 0.0, 1.0))


def cu_edge_eV(x: float) -> float:
    """Cu K-edge position of the as-made sample, eV.

    The metallic edge is at 8979 eV; oxidation pushes it up.
    """
    return 8979.0 + 3.2 * oxide_fraction(x)


# ---------------------------------------------------------------------------
# Electrochemical performance
# ---------------------------------------------------------------------------

#: Potential at which each carbon product is most efficient, V vs RHE, and the
#: width of that window.  CO needs only one electron and comes off early;
#: coupling two carbons needs a crowded surface and so needs to be driven
#: harder.
_PRODUCT_WINDOW = {
    "CO": (-0.85, 0.30),
    "HCOO-": (-0.95, 0.30),
    "CH4": (-1.15, 0.22),
    "C2H4": (-1.05, 0.22),
    "EtOH": (-1.05, 0.22),
}


def faradaic_efficiency(x: float,
                        potential_V: float = REPORT_POTENTIAL_V,
                        ) -> Dict[str, float]:
    """Product distribution at *potential_V*, in percent.

    Composition sets *what* the catalyst can make; potential sets *whether it
    is driven hard enough* to make it.  Copper makes hydrocarbons and alcohols
    because it binds *CO just strongly enough to couple it; gold releases CO
    before anything else can happen to it.  Hydrogen takes whatever charge is
    left, so the values sum to 100 by construction — as a real Faradaic
    efficiency must.
    """
    composition = {
        "CO": 88.0 / (1.0 + np.exp(-(x - 0.40) / 0.11)),
        "HCOO-": 13.0 * np.exp(-((x - 0.30) / 0.26) ** 2),
        "CH4": 16.0 * np.exp(-(x / 0.13) ** 2),
        "C2H4": 28.0 * np.exp(-((x - 0.02) / 0.17) ** 2),
        "EtOH": 8.0 * np.exp(-((x - 0.08) / 0.15) ** 2),
    }

    carbon = {}
    for name, amount in composition.items():
        centre, width = _PRODUCT_WINDOW[name]
        drive = np.exp(-0.5 * ((potential_V - centre) / width) ** 2)
        reference = np.exp(-0.5 * ((REPORT_POTENTIAL_V - centre) / width) ** 2)
        carbon[name] = amount * drive / reference

    hydrogen = max(100.0 - sum(carbon.values()), 2.0)
    total = sum(carbon.values()) + hydrogen

    out = {"H2": 100.0 * hydrogen / total}
    out.update({k: 100.0 * v / total for k, v in carbon.items()})
    return {k: float(out[k]) for k in PRODUCTS}


def current_density(x: float) -> float:
    """Total geometric current density at the reporting potential, mA cm⁻²."""
    return 34.0 - 24.0 * x


def co_partial_current(x: float) -> float:
    """CO partial current density, mA cm⁻².

    This is the volcano: copper is active but unselective, gold is selective
    but less active, and the product of the two peaks in between.  Plotting it
    against :func:`co_binding_eV` is the Sabatier principle in one chart.
    """
    return current_density(x) * faradaic_efficiency(x)["CO"] / 100.0


def her_tafel_mV(x: float) -> float:
    """Tafel slope of hydrogen evolution in Ar-saturated electrolyte, mV/dec."""
    return 112.0 + 38.0 * x


def oer_overpotential_mV(x: float) -> float:
    """Overpotential at 10 mA cm⁻² for oxygen evolution on the oxidised film.

    Included because not every measurement in a campaign supports the story:
    the trend here is weak and the material is a mediocre OER catalyst either
    way.  A demo in which every technique shows a clean trend teaches a
    falsehood about real data.
    """
    return 410.0 + 60.0 * x


# ---------------------------------------------------------------------------
# Inverses — from a measured number back to composition
#
# Kernels: plain numbers or arrays (a pandas column works too) in, numbers
# out. The notebooks, the Demo page and the README all recover composition
# with these, so the arithmetic exists once and is tested once.
# ---------------------------------------------------------------------------

def lattice_from_q(q_invA, hkl=(1, 1, 1)):
    """Cubic lattice parameter (Å) from one reflection's position. **Kernel.**

    ``a = 2π √(h² + k² + l²) / q`` — the (111) by default, the strongest fcc
    reflection and the first one a WAXS fit finds.
    """
    if np.any(np.asarray(q_invA, dtype=float) <= 0):
        raise ValueError("q must be positive")
    h, k, l = hkl
    return 2.0 * np.pi * np.sqrt(h * h + k * k + l * l) / q_invA


def fraction_from_lattice(a_A):
    """Gold fraction from a lattice parameter — Vegard's law run backwards.

    **Kernel**, the inverse of :func:`lattice_parameter_A`. Not clipped to
    0–1: a value outside it is information about the measurement, not
    something to hide.
    """
    return (a_A - A_CU) / (A_AU - A_CU)


def fraction_from_signals(gold, copper, gold_factor: float = 1.0,
                          copper_factor: float = 1.0):
    """Gold fraction from a gold and a copper line intensity. **Kernel.**

    Each intensity is divided by its sensitivity factor first — the
    Cliff–Lorimer k-factor for EDS (``signals.EDS_K_FACTOR_AU_CU`` on the
    gold line), the relative sensitivity factors for XPS
    (``signals.XPS_RSF``) — then ``x = Au / (Au + Cu)``.
    """
    au = gold / gold_factor
    cu = copper / copper_factor
    return au / (au + cu)


# ---------------------------------------------------------------------------
# Which samples got which technique
# ---------------------------------------------------------------------------

#: Techniques that are expensive or beamtime-limited, and the 1-based sample
#: indices that actually received them.  A real campaign never has a full
#: matrix, and ``Project.availability()`` exists to show exactly this.
SPARSE_COVERAGE = {
    # The Cu K-edge needs copper to absorb at, so the pure-gold sample is not
    # on the list — a technique that cannot apply is not the same as one that
    # was skipped.
    "xas": (1, 3, 5, 7),
    "tomo": (1, 6),
    "xpcs": (1, 4, 8),
    "saxs2d": (1, 4, 8),
}


def measured(technique: str, index: int) -> bool:
    """True if the 1-based *index*-th sample has *technique*."""
    allowed = SPARSE_COVERAGE.get(technique)
    return True if allowed is None else index in allowed


# ---------------------------------------------------------------------------
# Truth table
# ---------------------------------------------------------------------------

def showcase_truth(fractions: Sequence[float] = DEFAULT_FRACTIONS):
    """What the generator used, as a dataframe — the answer key.

    Every column here is something a technique in the project is supposed to
    be able to recover.  Comparing a fitted column against the matching
    ``true_*`` column is how the notebooks show the pipeline found something
    real rather than merely producing numbers.
    """
    import pandas as pd

    rows = []
    for index, x in enumerate(fractions, start=1):
        fe = faradaic_efficiency(x)
        rows.append({
            "sample_id": sample_id(index),
            "x_Au": float(x),
            "true_lattice_A": lattice_parameter_A(x),
            "true_lspr_nm": lspr_nm(x),
            "true_diameter_nm": particle_diameter_nm(x),
            "true_crystallite_nm": crystallite_nm(x),
            "true_hydrodynamic_nm": hydrodynamic_nm(x),
            "true_surface_x_Au": surface_au_fraction(x),
            "true_oxide_fraction": oxide_fraction(x),
            "true_d_band_eV": d_band_centre_eV(x),
            "true_co_binding_eV": co_binding_eV(x),
            "true_co_stretch_cm1": co_stretch_cm1(x),
            "true_FE_CO_pct": fe["CO"],
            "true_FE_C2H4_pct": fe["C2H4"],
            "true_j_CO_mA_cm2": co_partial_current(x),
        })
    return pd.DataFrame(rows)


__all__ = [
    "DEFAULT_FRACTIONS", "PRODUCTS", "REPORT_POTENTIAL_V", "SPARSE_COVERAGE",
    "A_CU", "A_AU", "sample_id", "measured", "showcase_truth",
    # inverses — kernels from a measurement back to composition
    "lattice_from_q", "fraction_from_lattice", "fraction_from_signals",
    "lattice_parameter_A", "particle_diameter_nm", "crystallite_nm",
    "hydrodynamic_nm", "aggregate_nm", "size_dispersity", "lspr_nm",
    "lspr_fwhm_nm", "d_band_centre_eV", "co_binding_eV", "h_binding_eV",
    "co_stretch_cm1", "sers_enhancement", "surface_au_fraction",
    "oxide_fraction", "cu_edge_eV", "faradaic_efficiency", "current_density",
    "co_partial_current", "her_tafel_mV", "oer_overpotential_mV",
]
