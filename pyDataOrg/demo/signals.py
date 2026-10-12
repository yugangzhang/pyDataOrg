#!/usr/bin/env python3
"""
Synthetic 1D signals for the multimodal demo, one function per technique.

Each function takes the B fraction ``x`` (and a random generator, so a run
is reproducible from a seed) and returns ``(axis, values)``.  The physics is
simplified but not faked: peak positions follow from the line energies and
lattice parameters of the two (fictional) metals, detector broadening follows the usual Fano expression, and
the Faradaic efficiencies sum to 100.  What is left out is everything that
would make the inverse problem hard — self-absorption, multiple scattering,
instrument drift.  That is deliberate: the demo exists so the *pipeline* can
be checked, not so an analysis can be validated on it.

Where a quantity is supposed to be recoverable, the generator and the recovery
share one formula, in :mod:`pyDataOrg.demo.materials`.
"""

from __future__ import annotations

from typing import Dict, Iterator, Tuple

import numpy as np

from pyDataOrg.demo import materials as mat

# ---------------------------------------------------------------------------
# Line shapes
# ---------------------------------------------------------------------------

def gaussian(x: np.ndarray, centre: float, fwhm: float,
             amplitude: float = 1.0) -> np.ndarray:
    sigma = fwhm / 2.3548200450309493
    return amplitude * np.exp(-0.5 * ((x - centre) / sigma) ** 2)


def lorentzian(x: np.ndarray, centre: float, fwhm: float,
               amplitude: float = 1.0) -> np.ndarray:
    half = fwhm / 2.0
    return amplitude * half ** 2 / ((x - centre) ** 2 + half ** 2)


def pseudo_voigt(x: np.ndarray, centre: float, fwhm: float,
                 amplitude: float = 1.0, eta: float = 0.5) -> np.ndarray:
    """The line shape a powder-diffraction peak is conventionally fitted with."""
    return (eta * lorentzian(x, centre, fwhm, amplitude)
            + (1.0 - eta) * gaussian(x, centre, fwhm, amplitude))


# ---------------------------------------------------------------------------
# UV-Vis: an in-situ growth series
# ---------------------------------------------------------------------------

#: Wavelength axis of the demo spectrometer, nm.
UVVIS_AXIS = np.linspace(350.0, 900.0, 551)


def uvvis_frames(x: float, n_frames: int, rng) -> Iterator[Tuple[float, float, np.ndarray]]:
    """Yield ``(time_s, block_temperature_C, absorbance)`` as the particles grow.

    The band grows in and red-shifts as the particles coarsen, settling on
    :func:`materials.lspr_nm` — so fitting the *last* frame recovers the
    hidden composition, and fitting an early one does not.  Reducing a series
    to the right frame is a real decision, and the demo should force it.
    """
    final = mat.lspr_nm(x)
    width = mat.lspr_fwhm_nm(x)
    for index in range(n_frames):
        progress = (index + 1) / n_frames
        grown = 1.0 - np.exp(-3.2 * progress)
        centre = final - 18.0 * (1.0 - grown)
        band = gaussian(UVVIS_AXIS, centre, width, 0.85 * grown)
        # Interband absorption, rising towards the blue. Kept weak and well
        # clear of the band: in a real sol it can sit directly under the
        # plasmon and biases any fit that ignores it, which is a lesson for a
        # real dataset rather than for the one example everybody runs first.
        interband = 0.22 / (1.0 + np.exp((UVVIS_AXIS - 430.0) / 16.0))
        baseline = 0.05 + 0.00008 * (900.0 - UVVIS_AXIS)
        noise = rng.normal(0.0, 0.0018, UVVIS_AXIS.size)
        yield (index * 45.0, 25.0 + 70.0 * progress,
               band + interband * grown + baseline + noise)


# ---------------------------------------------------------------------------
# EDS: bulk composition from characteristic X-ray lines
# ---------------------------------------------------------------------------

#: ``element: (energy_keV, relative line weight)`` for the lines in range.
#: A and B are fictional, and so are their line energies.
EDS_LINES = {
    "C Ka": (0.277, 0.35), "O Ka": (0.525, 0.30),
    "A La": (0.820, 0.55), "B Ma": (2.480, 0.70), "B Mb": (2.560, 0.25),
    "A Ka": (7.250, 1.00), "A Kb": (8.020, 0.14), "B La": (10.350, 0.85),
}

#: Cliff–Lorimer factor relating the B Lα and A Kα intensities to the
#: atomic ratio.  Written into the metadata so the ratio can be undone.
EDS_K_FACTOR_B_A = 0.85


def eds_spectrum(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Energy-dispersive X-ray spectrum, 10 eV channels up to 12 keV."""
    energy = np.arange(0.0, 12.0, 0.010) + 0.005
    counts = np.zeros_like(energy)

    strength = {
        "C Ka": 0.45, "O Ka": 0.12 + 0.5 * mat.oxide_fraction(x),
        "A La": 1.0 - x, "A Ka": 1.0 - x, "A Kb": 1.0 - x,
        "B Ma": x, "B Mb": x, "B La": x * EDS_K_FACTOR_B_A,
    }
    for line, (centre, weight) in EDS_LINES.items():
        amplitude = 9000.0 * weight * strength[line]
        if amplitude <= 0.0:
            continue
        # Fano-limited silicon-drift detector resolution.
        fwhm_keV = 2.3548 * np.sqrt(3.85 * 0.12 * centre * 1000.0 + 278.0) / 1000.0
        counts += gaussian(energy, centre, fwhm_keV, amplitude)

    # Bremsstrahlung: rises from the detector cut-on, falls towards the beam
    # energy (20 keV here), absorbed away at low energy by the window.
    brems = 450.0 * np.clip(20.0 - energy, 0.0, None) / (energy + 0.35) ** 1.4
    counts += brems * np.exp(-0.35 / np.clip(energy, 0.05, None))

    return energy, np.clip(rng.poisson(np.clip(counts, 0.0, None)), 0, None).astype(float)


# ---------------------------------------------------------------------------
# XPS: surface composition, and the A oxidation-state satellite
# ---------------------------------------------------------------------------

def xps_a2p(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """A 2p region.  The shake-up satellite near 914 eV means A(II)."""
    binding = np.linspace(897.0, 942.0, 901)
    surface_a = 1.0 - mat.surface_b_fraction(x)
    oxide = mat.oxide_fraction(x)

    counts = (gaussian(binding, 904.6, 1.6, 10000.0 * surface_a)
              + gaussian(binding, 924.4, 1.9, 5000.0 * surface_a)
              + gaussian(binding, 914.0, 4.2, 2600.0 * surface_a * oxide)
              + gaussian(binding, 934.0, 4.6, 1300.0 * surface_a * oxide))
    counts += 900.0 + 14.0 * (binding - 897.0)          # inelastic background
    return binding, counts + rng.normal(0.0, np.sqrt(np.clip(counts, 1, None)))


def xps_b4f(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """B 4f region: one spin-orbit doublet, split by 3.7 eV."""
    binding = np.linspace(58.0, 75.0, 681)
    surface_b = mat.surface_b_fraction(x)
    counts = (gaussian(binding, 64.0, 1.1, 14000.0 * surface_b)
              + gaussian(binding, 67.7, 1.2, 10500.0 * surface_b))
    counts += 500.0 + 9.0 * (binding - 58.0)
    return binding, counts + rng.normal(0.0, np.sqrt(np.clip(counts, 1, None)))


#: Relative sensitivity factors needed to turn the two peak areas above into a
#: surface atomic ratio.  Recorded in the metadata alongside the files.
XPS_RSF = {"A 2p3/2": 5.32, "B 4f7/2": 6.25}


# ---------------------------------------------------------------------------
# Raman and IR
# ---------------------------------------------------------------------------

def raman_spectrum(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Raman: A-oxide phonons on the A-rich samples, carbon from the support.

    The whole spectrum is multiplied by the B plasmon's surface enhancement,
    so the oxide bands get *weaker* with B for two independent reasons and
    the carbon bands get stronger.  Intensity alone is therefore
    not a composition measurement here — the band positions are.
    """
    shift = np.arange(100.0, 2200.0, 2.0)
    oxide = mat.oxide_fraction(x)
    gain = mat.sers_enhancement(x)

    intensity = np.zeros_like(shift)
    for centre, weight, width in ((172.0, 1.00, 14.0), (246.0, 0.42, 18.0),
                                  (388.0, 0.18, 24.0), (498.0, 0.30, 26.0),
                                  (596.0, 0.55, 30.0)):
        intensity += lorentzian(shift, centre, width, 2800.0 * weight * oxide)

    intensity += gaussian(shift, 1350.0, 120.0, 900.0)      # carbon D
    intensity += gaussian(shift, 1580.0, 70.0, 1150.0)      # carbon G
    intensity *= gain
    intensity += 600.0 + 0.45 * shift                       # fluorescence
    return shift, intensity + rng.normal(0.0, 18.0, shift.size)


def ir_spectrum(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Surface-enhanced IR of the working electrode during the reduction.

    The band near 2000 cm⁻¹ is the intermediate *P on a metal site.  Where it
    sits tracks the composition; how big it is tracks how much *P the surface
    is holding, which is why it follows the P Faradaic efficiency.
    """
    wavenumber = np.arange(1100.0, 2400.0, 1.0)
    coverage = mat.faradaic_efficiency(x)["P"] / 100.0

    absorbance = (
        gaussian(wavenumber, mat.p_stretch_cm1(x), 24.0, 0.055 * coverage)
        + gaussian(wavenumber, 1645.0, 65.0, 0.030)          # water bend
        + gaussian(wavenumber, 1620.0, 40.0, 0.016)          # electrolyte
        + gaussian(wavenumber, 1400.0, 36.0, 0.014)          # electrolyte
        + gaussian(wavenumber, 1360.0, 32.0, 0.011)          # electrolyte
    )
    absorbance += 0.004 + 1.2e-5 * (wavenumber - 1100.0)
    return wavenumber, absorbance + rng.normal(0.0, 3.0e-4, wavenumber.size)


# ---------------------------------------------------------------------------
# XAS: A K-edge
# ---------------------------------------------------------------------------

def xas_spectrum(x: float, state: str, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Normalised A K-edge XANES for *state* ``"as_made"`` or ``"reduced"``.

    Oxidised A has its edge a few eV higher and a much stronger white
    line.  After the catalyst has been held at a reducing potential the edge
    comes back to the metallic position — which is the measurement that tells
    you what the active phase actually was.
    """
    energy = np.linspace(mat.EDGE_A_eV - 29.0, mat.EDGE_A_eV + 121.0, 601)
    oxide = mat.oxide_fraction(x) if state == "as_made" else 0.03
    edge = mat.EDGE_A_eV + 3.2 * oxide

    mu = 0.5 + np.arctan((energy - edge) / 2.2) / np.pi
    mu += gaussian(energy, edge + 5.0, 9.0, 0.30 + 0.85 * oxide)   # white line
    mu += gaussian(energy, mat.EDGE_A_eV - 2.0, 2.0, 0.05 * oxide)  # pre-edge
    above = energy > edge + 18.0
    mu[above] += 0.07 * np.sin(0.62 * np.sqrt(energy[above] - edge)) \
        * np.exp(-(energy[above] - edge) / 140.0)
    return energy, mu + rng.normal(0.0, 0.0025, energy.size)


# ---------------------------------------------------------------------------
# Scattering
# ---------------------------------------------------------------------------

def _sphere_form_factor(q: np.ndarray, radius: np.ndarray) -> np.ndarray:
    qr = np.outer(q, radius)
    qr = np.where(qr < 1e-8, 1e-8, qr)
    return 3.0 * (np.sin(qr) - qr * np.cos(qr)) / qr ** 3


def saxs_curve(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """SAXS from a log-normal population of spheres, plus a flat background.

    The Guinier region at low q gives the radius of gyration and the Porod
    region at high q gives the surface area, so this measures the same size
    the micrographs do — by a completely different route, on ~10⁹ more
    particles.
    """
    q = np.logspace(np.log10(0.004), np.log10(0.6), 320)
    median = 0.5 * mat.particle_diameter_nm(x) * 10.0      # radius in Å
    sigma = mat.size_dispersity(x)

    nodes = np.exp(np.log(median) + sigma * np.linspace(-3.5, 3.5, 41))
    weights = np.exp(-0.5 * ((np.log(nodes / median)) / sigma) ** 2)
    weights /= weights.sum()
    volume = (4.0 / 3.0) * np.pi * nodes ** 3

    form = _sphere_form_factor(q, nodes) ** 2
    intensity = 4.0e-6 * (form * (weights * volume ** 2)).sum(axis=1) + 0.02
    noise = rng.normal(0.0, 0.03, q.size) * np.sqrt(intensity)
    return q, np.clip(intensity + noise, 1e-4, None)


#: fcc reflections used for the powder pattern: ``(h, k, l, relative intensity)``.
FCC_REFLECTIONS = ((1, 1, 1, 100.0), (2, 0, 0, 46.0), (2, 2, 0, 20.0),
                   (3, 1, 1, 17.0), (2, 2, 2, 5.0))


def waxs_curve(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Powder pattern in q.  Peak positions give the lattice parameter.

    ``q_hkl = 2π√(h²+k²+l²)/a`` with ``a`` from Vegard's law, so fitting the
    (111) peak and inverting that expression recovers the composition — the
    structural check on what EDS says the composition is.
    """
    q = np.linspace(1.8, 7.5, 1400)
    a = mat.lattice_parameter_A(x)
    width = 2.0 * np.pi * 0.9 / (mat.crystallite_nm(x) * 10.0)   # Scherrer

    intensity = np.zeros_like(q)
    for h, k, l, weight in FCC_REFLECTIONS:
        centre = 2.0 * np.pi * np.sqrt(h * h + k * k + l * l) / a
        intensity += pseudo_voigt(q, centre, width, 120.0 * weight, eta=0.45)

    intensity += gaussian(q, 2.0, 1.4, 90.0)      # amorphous carbon support
    intensity += gaussian(q, 3.1, 2.2, 45.0)
    intensity += 25.0
    return q, intensity + rng.normal(0.0, 1.6, q.size)


# ---------------------------------------------------------------------------
# Dynamics: DLS and XPCS
# ---------------------------------------------------------------------------

def dls_distribution(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Intensity-weighted size distribution, as a DLS instrument reports it.

    It will read larger than TEM.  That is not a bug in either technique: DLS
    sees the hydrated, ligand-wrapped object, and weights it by scattered
    intensity, which goes as the sixth power of diameter.
    """
    diameter = np.logspace(0.0, 3.0, 220)
    primary = gaussian(np.log(diameter), np.log(mat.hydrodynamic_nm(x)), 0.52, 100.0)
    aggregate = gaussian(np.log(diameter), np.log(mat.aggregate_nm(x)), 0.40, 16.0)
    signal = primary + aggregate
    return diameter, np.clip(signal + rng.normal(0.0, 0.6, diameter.size), 0.0, None)


#: Conditions of the XPCS measurement: the ink is loaded in a glycerol/water
#: mixture so the aggregates move slowly enough to follow.
XPCS_VISCOSITY_Pa_s = 0.60
XPCS_Q_INV_A = 0.010
XPCS_TEMPERATURE_K = 298.0


def xpcs_g2(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Intensity autocorrelation of the aggregates: ``g₂ = 1 + β e^{-2Γτ}``.

    Γ = D q² with D from Stokes–Einstein, so the decay rate here and the DLS
    peak position are two measurements of the same diffusion coefficient.
    """
    lag = np.logspace(-3.0, 2.0, 64)
    k_B = 1.380649e-23
    radius_m = 0.5 * mat.aggregate_nm(x) * 1e-9
    diffusion_m2_s = k_B * XPCS_TEMPERATURE_K / (
        6.0 * np.pi * XPCS_VISCOSITY_Pa_s * radius_m)
    diffusion_A2_s = diffusion_m2_s * 1e20
    rate = diffusion_A2_s * XPCS_Q_INV_A ** 2

    g2 = 1.0 + 0.28 * np.exp(-2.0 * rate * lag)
    # Correlation noise grows with lag: fewer independent pairs out there.
    return lag, g2 + rng.normal(0.0, 0.0025 * (1.0 + 6.0 * lag / lag.max()), lag.size)


# ---------------------------------------------------------------------------
# Electrochemistry
# ---------------------------------------------------------------------------

def her_lsv(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Hydrogen evolution in Ar-saturated electrolyte: the competing reaction.

    Run without the reactant on purpose — it is the control that says how
    much of the current in the reduction was never going to make a product.
    """
    potential = np.linspace(-0.75, 0.05, 321)
    tafel_V = mat.her_tafel_mV(x) / 1000.0
    kinetic = 0.012 * 10.0 ** (-potential / tafel_V)
    current = -1.0 / (1.0 / kinetic + 1.0 / 80.0)
    current = np.where(potential > 0.0, current * 0.0, current)
    return potential, current + rng.normal(0.0, 0.06, potential.size)


def oer_lsv(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Oxygen evolution on the anodically conditioned film.

    Constructed so that the current is exactly 10 mA cm⁻² at
    1.23 V + :func:`materials.oer_overpotential_mV`, which is the number
    everybody quotes.
    """
    potential = np.linspace(1.20, 1.90, 281)
    tafel_V = 0.072
    overpotential = mat.oer_overpotential_mV(x) / 1000.0
    exchange = 10.0 * 10.0 ** (-overpotential / tafel_V)
    current = exchange * 10.0 ** ((potential - 1.23) / tafel_V) + 0.05
    return potential, current + rng.normal(0.0, 0.05, potential.size)


def rr_lsv(x: float, rng) -> Tuple[np.ndarray, np.ndarray]:
    """Total current of the reduction, reactant-saturated electrolyte.

    Scaled so the magnitude at the reporting potential equals
    :func:`materials.current_density`, which is what the Faradaic efficiencies
    are percentages *of*.
    """
    potential = np.linspace(-1.30, -0.20, 441)
    tafel_V = 0.140
    limiting = 120.0
    target = mat.current_density(x)

    shape = 10.0 ** ((-0.35 - potential) / tafel_V)
    reference = 10.0 ** ((-0.35 - mat.REPORT_POTENTIAL_V) / tafel_V)
    # Solve the scale so that kinetic ⊕ limiting lands on the target.
    kinetic_at_report = 1.0 / (1.0 / target - 1.0 / limiting)
    kinetic = kinetic_at_report * shape / reference

    current = -1.0 / (1.0 / kinetic + 1.0 / limiting)
    return potential, current + rng.normal(0.0, 0.08, potential.size)


#: Potentials at which the product gases and liquids were quantified.
FE_POTENTIALS = np.round(np.arange(-1.30, -0.39, 0.10), 2)[::-1]


def rr_faradaic(x: float, rng) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """``{product: (potential, FE%)}`` from product quantification.

    One file per product, which is how a GC/HPLC campaign is actually
    tabulated, and which gives the viewer several curves to overlay.
    """
    out: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for product in mat.PRODUCTS:
        values = np.array([mat.faradaic_efficiency(x, float(e))[product]
                           for e in FE_POTENTIALS])
        noise = rng.normal(0.0, 0.8, values.size)
        out[product] = (FE_POTENTIALS, np.clip(values + noise, 0.0, None))
    return out


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def dft_pdos(x: float) -> Tuple[np.ndarray, np.ndarray]:
    """Projected density of states of the surface layer, states/eV/atom.

    The d-band is the feature that matters: its centroid is the descriptor
    that the *P binding energy, and through it the selectivity, follows.  No
    noise — a calculation is deterministic, and pretending otherwise would be
    a lie about where the number came from.
    """
    energy = np.linspace(-10.0, 4.0, 701)
    target = mat.d_band_centre_eV(x)
    width = 1.15 + 0.55 * x

    def band(centre: float) -> np.ndarray:
        return (gaussian(energy, centre, 2.3548 * width, 1.9)
                + gaussian(energy, centre - 1.3 * width,
                           2.3548 * 0.8 * width, 0.75))

    # The band is asymmetric, so its centroid is not where its main peak sits.
    # Shift it until the centroid *is* the d-band centre: the number the
    # generator advertises has to be the number a measurement of the generated
    # curve returns, or the demo is checking the pipeline against a fiction.
    # Centroid is linear in the shift, so one correction is exact.
    first = band(target)
    centroid = float((energy * first).sum() / first.sum())
    d_band = band(target + (target - centroid))

    sp_band = 0.16 * np.sqrt(np.clip(energy + 10.0, 0.0, None))
    return energy, d_band + sp_band


__all__ = [
    "gaussian", "lorentzian", "pseudo_voigt", "UVVIS_AXIS", "uvvis_frames",
    "EDS_LINES", "EDS_K_FACTOR_B_A", "eds_spectrum", "xps_a2p", "xps_b4f",
    "XPS_RSF", "raman_spectrum", "ir_spectrum", "xas_spectrum", "saxs_curve",
    "FCC_REFLECTIONS", "waxs_curve", "dls_distribution", "xpcs_g2",
    "XPCS_VISCOSITY_Pa_s", "XPCS_Q_INV_A", "her_lsv", "oer_lsv", "rr_lsv",
    "FE_POTENTIALS", "rr_faradaic", "dft_pdos",
]
