#!/usr/bin/env python3
"""
Demo — notebooks 10 → 11 → 12, with buttons, on the Cu–Au campaign.

The three workflow notebooks walk one campaign from raw files to a
structure–property plot: a Cu–Au alloy nanocatalyst library for CO₂
reduction, eight alloys and one failed run, seen by fifteen techniques across
four stages, all following from **one hidden number** — the gold fraction.
This page is the same walk in six tabs, calling the same package functions in
the same order:

1 · Simulate    ``notebook/10`` — ``build_showcase_project`` writes the files
                and the four metadata dicts; the answer key goes beside them
2 · Build       ``notebook/11`` — ``Organizer(cuau.json)``, ingest the four
                dicts, link the four techniques nobody wrote down, save
3 · Look        ``notebook/12`` A/B — describe, tree, ids, frames, data eager
                and lazy
4 · Visualize   ``notebook/12`` C — every group in one gallery, any technique
                static or interactive, an overlay across samples
5 · Analyze     ``notebook/12`` D — the WAXS kernel on arrays, the
                segmentation check, *then* the campaign's batches
6 · Compare     ``notebook/12`` E/F — composition three ways, three sizes,
                the volcano; reload a stored fit without refitting

Every tab ends with **The same in Python**: the calls it just made, so nothing
here is a GUI-only path. Analysing and drawing are always two calls — the page
composes them; no helper on it does both.

The organizer built here is the page's own (``nano_demo_org``), separate from
the workflow pages' workbench until **Use this organizer in the workflow
pages** hands it over.
"""

import contextlib
import io
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from NanoOrganizer import Organizer, structure
from NanoOrganizer.analysis import fit_peaks
from NanoOrganizer.analysis.peaks import BACKGROUNDS, SHAPES
from NanoOrganizer.demo import (
    build_showcase_project, demo_root, materials as mat, showcase_truth,
)
from NanoOrganizer.demo.images import TOMO_NM_PER_VOXEL
from NanoOrganizer.demo.signals import EDS_K_FACTOR_AU_CU, XPS_RSF
from NanoOrganizer.viz import interactive, plots
from NanoOrganizer.web_app.components.security import (
    format_allowed_roots, is_path_allowed,
)
from NanoOrganizer.web_app.state import get_workbench, set_workbench

ORG = "nano_demo_org"
OUTCOMES = "nano_demo_outcomes"

#: The four authored metadata modules, one per stage.
STAGES = ("Synthesis", "Characterization", "Testing", "Computation")

#: Techniques that arrive as a bare folder per sample, with no record at all.
BY_HAND = {"tem": "TEMData", "sem": "SEMData", "dls": "DLSData",
           "tomo": "TomoData"}

#: The WAXS fit: the (111) and (200) reflections on a sloping background.
WAXS_FIT = dict(x_range=(2.5, 3.6), n_peaks=2, shape="pseudo_voigt",
                background="linear")

#: The campaign's analyses, in the order notebook 12 runs them.
BATCHES = [
    ("WAXS (111)/(200) peaks", "peak_fit",
     dict(modality="waxs1d", link=True, **WAXS_FIT)),
    ("Plasmon band", "peak_fit",
     dict(modality="uvvis", x_range=(470.0, 800.0), reduce="last_decile",
          background="linear", link=True)),
    ("EDS Cu Kα area", "curve_metrics",
     dict(modality="eds", prefix="eds_cu_", x_min=7.7, x_max=8.4)),
    ("EDS Au Lα area", "curve_metrics",
     dict(modality="eds", prefix="eds_au_", x_min=9.4, x_max=10.0)),
    ("XPS Cu 2p area", "curve_metrics",
     dict(modality="xps", role="cu2p", prefix="xps_cu_", x_min=929, x_max=937)),
    ("XPS Au 4f area", "curve_metrics",
     dict(modality="xps", role="au4f", prefix="xps_au_", x_min=81.5,
          x_max=86.0)),
    ("TEM particle sizes", "particle_sizing", dict(modality="tem")),
    ("SEM agglomerate sizes", "particle_sizing",
     dict(modality="sem", max_diameter_nm=500, min_circularity=0.5)),
    ("DLS hydrodynamic size", "curve_metrics",
     dict(modality="dls", x_min=5, x_max=120)),
]

#: What tab 6 reads; present once the batches have run.
NEEDED = ("derived.waxs1d_peak1_center", "derived.uvvis_peak1_center",
          "derived.eds_au_area", "derived.eds_cu_area", "derived.xps_au_area",
          "derived.xps_cu_area", "derived.tem_d_mean", "derived.sem_d_mean",
          "derived.dls_x_at_max")

#: The gallery: eight slots, each the first technique the sample has.
GALLERY = [
    [("uvvis", "", {})],
    [("waxs1d", "", {})],
    [("saxs1d", "", {})],
    [("ec", "co2-rr-fe", {"ylabel": "Faradaic efficiency (%)"}),
     ("ec", "co2-rr", {})],
    [("tem", "", {"cmap": "gray"})],
    [("sem", "", {"cmap": "gray"})],
    [("tomo", "", {"slab": 16, "cmap": "bone"}),
     ("saxs2d", "", {"log_intensity": True, "cmap": "inferno"}),
     ("eds", "", {})],
    [("xpcs_g2", "", {}), ("dls", "", {}), ("xps", "au4f", {})],
]


# ---------------------------------------------------------------------------
# Small helpers — each one computes *or* draws, never both
# ---------------------------------------------------------------------------

def show_figure(figure, dpi: int = 110) -> None:
    """Render a matplotlib figure and release it."""
    st.pyplot(figure, width="stretch", dpi=dpi)
    plt.close(figure)


def same_in_python(code: str) -> None:
    """The calls a tab just made, as code to paste into a notebook."""
    with st.expander("The same in Python", expanded=False):
        st.code(code.strip(), language="python")


def call_text(analysis: str, options: dict) -> str:
    """``org.batch(...)`` as it would be typed."""
    arguments = ", ".join(f"{k}={v!r}" for k, v in options.items())
    return f'org.batch("{analysis}", {arguments})'


def samples_with(org, modality: str, role: str = "") -> list:
    """Samples holding a *modality* (and *role*) measurement."""
    if org is None:
        return []
    return [s for s in org.project.sample_ids()
            if org.project.get_sample(s).get_measurements(modality=modality,
                                                          role=role)]


def techniques_of(org, sample_id: str) -> list:
    """``(modality, role)`` pairs a sample has, stored fits left out."""
    found = [(m.modality, m.role)
             for m in org.project.get_sample(sample_id).measurements
             if m.modality != "fit"]
    return list(dict.fromkeys(found))


def physics_curves(n: int = 101) -> dict:
    """The generator's model as arrays, against the gold fraction. Computes."""
    x = np.linspace(0.0, 1.0, n)
    marks = np.asarray(mat.DEFAULT_FRACTIONS)
    model = {
        "lattice": mat.lattice_parameter_A, "lspr": mat.lspr_nm,
        "tem": mat.particle_diameter_nm, "dls": mat.hydrodynamic_nm,
        "sem": mat.aggregate_nm, "surface": mat.surface_au_fraction,
        "d_band": mat.d_band_centre_eV, "co_binding": mat.co_binding_eV,
        "j_co": mat.co_partial_current,
    }
    curves = {"x": x, "marks": marks}
    for name, function in model.items():
        curves[name] = np.array([function(v) for v in x])
        curves[f"{name}_marks"] = np.array([function(v) for v in marks])
    return curves


def draw_physics(c: dict, ax=None):
    """One number, fifteen shadows — six panels of the model. Draws.

    *ax* is a 2×3 grid of Axes (a new figure when None); returns it.
    """
    if ax is None:
        _, ax = plt.subplots(2, 3, figsize=(15.5, 7.6))
    axes = np.asarray(ax).reshape(2, 3)
    blue, orange, aqua = plots.CATEGORICAL[:3]

    def panel(ax, key, colour, label=None):
        ax.plot(c["x"], c[key], color=colour, lw=2, label=label)
        ax.plot(c["marks"], c[f"{key}_marks"], "o", color=colour, ms=6)

    panel(axes[0, 0], "lattice", blue)
    plots.style(axes[0, 0], "gold fraction x", "lattice parameter (Å)",
                "Vegard: WAXS reads composition")
    panel(axes[0, 1], "lspr", orange)
    plots.style(axes[0, 1], "gold fraction x", "plasmon band (nm)",
                "One band that moves — an alloy")
    for key, colour, label in (("sem", aqua, "SEM — agglomerates"),
                               ("dls", orange, "DLS — hydrodynamic"),
                               ("tem", blue, "TEM — primary particles")):
        panel(axes[0, 2], key, colour, label)
    axes[0, 2].set_yscale("log")
    plots.style(axes[0, 2], "gold fraction x", "diameter (nm)",
                "Three sizes, all of them right")
    axes[0, 2].legend(frameon=False, fontsize=8)

    axes[1, 0].plot([0, 1], [0, 1], "--", color="0.6", lw=1.2,
                    label="bulk (EDS)")
    panel(axes[1, 0], "surface", plots.CATEGORICAL[3], "surface (XPS)")
    plots.style(axes[1, 0], "gold fraction x", "gold fraction seen",
                "Gold segregates to the surface")
    axes[1, 0].legend(frameon=False, fontsize=8)
    panel(axes[1, 1], "d_band", blue, "d-band centre")
    panel(axes[1, 1], "co_binding", orange, "CO binding")
    plots.style(axes[1, 1], "gold fraction x", "energy (eV)",
                "DFT: electronic structure sets binding")
    axes[1, 1].legend(frameon=False, fontsize=8)
    order = np.argsort(c["co_binding"])
    axes[1, 2].plot(c["co_binding"][order], c["j_co"][order],
                    color=plots.STATUS["critical"], lw=2)
    axes[1, 2].plot(c["co_binding_marks"], c["j_co_marks"], "o",
                    color=plots.STATUS["critical"], ms=6)
    plots.style(axes[1, 2], "CO binding energy (eV)",
                "CO partial current (mA cm$^{-2}$)", "Sabatier volcano")
    return axes


def coverage_table() -> pd.DataFrame:
    """Which sample received which beamtime-limited technique. Computes."""
    rows = {}
    for index, _ in enumerate(mat.DEFAULT_FRACTIONS, start=1):
        rows[mat.sample_id(index)] = {
            technique: "✓" if mat.measured(technique, index) else ""
            for technique in mat.SPARSE_COVERAGE}
    return pd.DataFrame(rows).T


def composition_check(table: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Every recovered number beside the generator's. Computes, draws nothing."""
    t = table.set_index("sample_id").reindex(truth.index)
    return pd.DataFrame({
        "x_true": truth["x_Au"],
        "x_WAXS": mat.fraction_from_lattice(
            mat.lattice_from_q(t["derived.waxs1d_peak1_center"])),
        "x_EDS": mat.fraction_from_signals(
            t["derived.eds_au_area"], t["derived.eds_cu_area"],
            gold_factor=EDS_K_FACTOR_AU_CU),
        "x_XPS": mat.fraction_from_signals(
            t["derived.xps_au_area"], t["derived.xps_cu_area"],
            gold_factor=XPS_RSF["Au 4f7/2"],
            copper_factor=XPS_RSF["Cu 2p3/2"]),
        "x_surface_true": truth["true_surface_x_Au"],
        "band_nm": t["derived.uvvis_peak1_center"],
        "band_true_nm": truth["true_lspr_nm"],
        "TEM_nm": t["derived.tem_d_mean"],
        "DLS_nm": t["derived.dls_x_at_max"],
        "SEM_nm": t["derived.sem_d_mean"],
    })


def draw_composition(check: pd.DataFrame, ax=None):
    """Composition three ways, and the plasmon band. Draws.

    *ax* is three Axes in a row (a new figure when None); returns them.
    """
    if ax is None:
        _, ax = plt.subplots(1, 3, figsize=(14.0, 4.4))
    axes = np.ravel(ax)
    x = check["x_true"]
    axes[0].plot([0, 1], [0, 1], "--", color="0.6", lw=1.2)
    axes[0].plot(x, check["x_EDS"], "o", ms=9, color=plots.CATEGORICAL[0],
                 label="EDS — X-ray lines")
    axes[0].plot(x, check["x_WAXS"], "s", ms=7, color=plots.CATEGORICAL[1],
                 label="WAXS — Vegard")
    plots.style(axes[0], "x(Au) the generator used", "x(Au) recovered",
                "Two rooms, one answer")
    axes[0].legend(frameon=False, fontsize=9)

    axes[1].plot([0, 1], [0, 1], "--", color="0.6", lw=1.2,
                 label="no segregation")
    axes[1].plot(x, check["x_surface_true"], "-", color=plots.CATEGORICAL[3],
                 lw=1.2, alpha=0.6, label="true surface")
    axes[1].plot(x, check["x_XPS"], "s", ms=8, color=plots.CATEGORICAL[3],
                 label="XPS — surface")
    axes[1].plot(x, check["x_EDS"], "o", ms=7, color=plots.CATEGORICAL[0],
                 label="EDS — bulk")
    plots.style(axes[1], "x(Au) in the bulk", "x(Au) measured",
                "Gold segregates to the surface")
    axes[1].legend(frameon=False, fontsize=9)

    axes[2].plot(x, check["band_true_nm"], "--", color="0.6", lw=1.2,
                 label="truth")
    axes[2].plot(x, check["band_nm"], "o", ms=9, color=plots.CATEGORICAL[2],
                 label="fitted")
    plots.style(axes[2], "x(Au)", "plasmon band (nm)", "One band, not two")
    axes[2].legend(frameon=False, fontsize=9)
    return axes


def draw_sizes(check: pd.DataFrame, ax=None):
    """TEM, DLS and SEM diameters on one log axis. Draws; returns *ax*."""
    if ax is None:
        _, ax = plt.subplots(figsize=(6.5, 4.6))
    x = check["x_true"]
    for column, marker, colour, label in (
            ("SEM_nm", "^", plots.CATEGORICAL[2], "SEM — agglomerates"),
            ("DLS_nm", "s", plots.CATEGORICAL[1], "DLS — hydrodynamic"),
            ("TEM_nm", "o", plots.CATEGORICAL[0], "TEM — primary")):
        ax.plot(x, check[column], marker, ms=9, color=colour, label=label)
    ax.set_yscale("log")
    plots.style(ax, "x(Au)", "diameter (nm)", "Three sizes, all correct")
    ax.legend(frameon=False, fontsize=9)
    return ax


# ---------------------------------------------------------------------------
# Header and where the demo lives
# ---------------------------------------------------------------------------

st.title("🎓 Demo")
st.caption(
    "The three workflow notebooks — **10** simulate, **11** build, **12** use — "
    "as six tabs, on a Cu–Au alloy catalyst library: eight alloys and one "
    "failed run, fifteen techniques, four stages, one hidden number. Same "
    "package calls, same order, same files; each tab shows its code under "
    "*The same in Python*."
)

root_text = st.text_input(
    "Demo folder", value=str(demo_root("CuAu")), key="nano_demo_root",
    help="The campaign is written to Campaign/ inside it, the organizer "
         "saved as cuau.json beside that, and the answer key as truth.csv. "
         "Defaults under demo_root() — ~/Repos/OrgDemo — or "
         "$NANOORGANIZER_DEMO_ROOT.")
ROOT = Path(root_text.strip() or demo_root("CuAu")).expanduser()
CAMPAIGN = ROOT / "Campaign"
META = CAMPAIGN / "MetaData"
STORE = ROOT / "cuau.json"
TRUTH = ROOT / "truth.csv"
RESULTS = ROOT / "results"

if not is_path_allowed(ROOT, allow_nonexistent=True):
    st.error(f"{ROOT} is outside the folders this session may write "
             f"to: {format_allowed_roots()}", icon="🚫")
    st.stop()

org = st.session_state.get(ORG)
if org is not None and org.path != STORE:
    # A different demo folder was typed: the old organizer is not this one.
    st.session_state.pop(ORG, None)
    org = None

simulate, build, look, visualize, analyze, compare = st.tabs([
    "1 · Simulate", "2 · Build", "3 · Look", "4 · Visualize", "5 · Analyze",
    "6 · Compare",
])

# ---------------------------------------------------------------------------
# 1 · Simulate — notebook 10
# ---------------------------------------------------------------------------

with simulate:
    st.caption("Mirrors `notebook/10_simulate_data` — a campaign writing its "
               "files. Nothing here involves an organizer yet.")
    headline = st.columns(4)
    headline[0].metric("Alloys", len(mat.DEFAULT_FRACTIONS), "+1 failed run",
                       delta_color="off")
    headline[1].metric("Techniques", 15)
    headline[2].metric("Stages", len(STAGES))
    headline[3].metric("Hidden numbers", 1, "the gold fraction x",
                       delta_color="off")

    st.markdown(
        "A Cu–Au alloy nanocatalyst library for CO₂ electroreduction. Cu and "
        "Au mix at every composition, so **everything follows from the gold "
        "fraction x**: the lattice parameter (Vegard), the one plasmon band, "
        "the particle size, how much gold sits at the surface, the d-band "
        "centre, how hard CO binds — and so the selectivity. Fifteen "
        "techniques each see one shadow of it; tab 6 checks they agree.")
    figure, axes = plt.subplots(2, 3, figsize=(15.5, 7.6))
    draw_physics(physics_curves(), ax=axes)
    figure.tight_layout()
    show_figure(figure, dpi=100)

    simulated = (META / "Synthesis_dict.py").exists() and TRUTH.exists()
    left, right = st.columns([3, 1])
    left.caption(f"Writes `{CAMPAIGN}` and `{TRUTH.name}` beside it. "
                 f"Re-running rebuilds the same files with the same numbers; "
                 f"an organizer saved in `{ROOT.name}/` is left alone.")
    if right.button("Simulate again" if simulated else "Simulate the campaign",
                    type="secondary" if simulated else "primary",
                    width="stretch", key="nano_demo_simulate"):
        try:
            with st.spinner("Writing fifteen techniques' worth of files…"):
                build_showcase_project(CAMPAIGN)
                showcase_truth().to_csv(TRUTH, index=False)
            simulated = True
            st.success(f"Wrote the campaign under {CAMPAIGN}")
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    if simulated:
        # What the campaign wrote — not the marker, not a __pycache__ that
        # reading a metadata module can leave beside it.
        files = [p for p in CAMPAIGN.rglob("*") if p.is_file()
                 and "__pycache__" not in p.parts
                 and not p.name.startswith(".")]
        size_mb = sum(p.stat().st_size for p in files) / 1e6
        counts = st.columns(4)
        counts[0].metric("Files on disk", len(files))
        counts[1].metric("Size", f"{size_mb:.0f} MB")
        counts[2].metric("Metadata modules", len(list(META.glob("*_dict.py"))))
        counts[3].metric("Folders with no record", len(BY_HAND))

        tree_col, record_col = st.columns(2)
        with tree_col:
            st.markdown("**What landed on disk** — `structure.tree`, which "
                        "reads layout, not data")
            st.code(structure.tree(str(CAMPAIGN), depth=1), language=None)
        with record_col:
            st.markdown("**What the operators wrote down** — one metadata "
                        "module per stage; any block naming files becomes a "
                        "measurement on ingest")
            st.code(structure.tree(
                f"{META}/Characterization_dict.py::Characterization_dict/CuAu05",
                depth=1, limit=14), language=None)

        st.markdown(
            "**What nobody wrote down** — "
            + ", ".join(f"`{folder}/`" for folder in BY_HAND.values())
            + " hold TEM, SEM, DLS and tomography as a folder per sample, "
              "with no record anywhere. Tab 2 links them by hand.")

        sparse_col, truth_col = st.columns([2, 5])
        with sparse_col:
            st.markdown("**A sparse matrix** — beamtime is finite")
            st.dataframe(coverage_table(), width="stretch")
        with truth_col:
            st.markdown("**The answer key** — what the generator used, "
                        "written to `truth.csv` so tab 6 can check")
            truth_view = pd.read_csv(TRUTH)
            st.dataframe(truth_view[["sample_id", "x_Au", "true_lattice_A",
                                     "true_lspr_nm", "true_diameter_nm",
                                     "true_surface_x_Au",
                                     "true_j_CO_mA_cm2"]].round(3),
                         hide_index=True, width="stretch")

    same_in_python(f'''
from pathlib import Path
from NanoOrganizer.demo import build_showcase_project, showcase_truth

ROOT = Path("{ROOT}")
CAMPAIGN = ROOT / "Campaign"

build_showcase_project(CAMPAIGN)                     # files + four metadata dicts
showcase_truth().to_csv(ROOT / "truth.csv", index=False)   # the answer key

from NanoOrganizer import structure
print(structure.tree(CAMPAIGN, depth=1))
''')

# ---------------------------------------------------------------------------
# 2 · Build — notebook 11
# ---------------------------------------------------------------------------

with build:
    st.caption("Mirrors `notebook/11_build_organizer` — one JSON file that "
               "knows where everything is. The data never moves.")

    if not (META / "Synthesis_dict.py").exists():
        st.info("Nothing to organise yet — simulate the data first, in tab "
                "**1 · Simulate**.", icon="👈")
    else:
        st.markdown("**a · The organizer** — `Organizer(cuau.json)` is empty "
                    "if the file is new, and everything is back if it is not.")
        if org is None:
            saved = STORE.exists()
            if st.button("Reopen cuau.json" if saved
                         else "Create Organizer(cuau.json)",
                         type="primary", key="nano_demo_create"):
                try:
                    org = Organizer(STORE, name="Cu-Au CO2RR library")
                    st.session_state[ORG] = org
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
            if saved:
                st.caption(f"`{STORE.name}` already exists here — reopening "
                           f"it brings back its links, parameters and fits.")

    if org is not None:
        st.caption(f"`{org.path}` — {len(org.project)} samples, "
                   f"{len(org.project.measurements())} measurements")

        st.markdown("**b · Ingest what was written down** — four modules, one "
                    "per stage; the stage is read from the dict's name.")
        if st.button("Ingest the four metadata dicts", key="nano_demo_ingest",
                     type="primary" if not len(org.project) else "secondary"):
            try:
                for stage in STAGES:
                    org.ingest(META / f"{stage}_dict.py")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        if len(org.project):
            wanted = ["synthesis.composition.nominal_x_Au", "synthesis.status",
                      "testing.performance.FE_CO_pct",
                      "testing.performance.j_CO_mA_cm2", "n_measurements"]
            table = org.table(all_samples=True)
            st.dataframe(table[[c for c in wanted if c in table.columns]],
                         width="stretch")

        st.markdown("**c · Link what nobody wrote down** — TEM, SEM, DLS and "
                    "tomography, one call per sample and technique. A folder "
                    "is listed now and filtered by the technique's "
                    "extensions, so the `note.txt` beside the micrographs is "
                    "left out.")
        linked = bool(samples_with(org, "tem"))
        if st.button("Link the four folder techniques by hand",
                     key="nano_demo_link", disabled=not len(org.project),
                     type="primary" if len(org.project) and not linked
                     else "secondary"):
            try:
                for sample in org.ids():
                    for modality, folder in BY_HAND.items():
                        source = CAMPAIGN / folder / sample
                        # A link to nothing is a mistake, not a feature: skip
                        # it and let the gap show in the catalog.
                        if not source.is_dir():
                            continue
                        extra = ({"voxel_size_nm": TOMO_NM_PER_VOXEL}
                                 if modality == "tomo" else {})
                        org.link(sample, modality, str(source),
                                 stage="characterization", **extra)
                linked = True
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        if len(org.project):
            st.markdown("The catalog — sample × technique, files per cell. "
                        "`CuAu09` is the failed run: a row with nothing in "
                        "it, kept on purpose.")
            catalog = org.catalog(counts=True)
            st.dataframe(catalog.style.background_gradient(cmap="Blues",
                                                           vmin=0, vmax=4),
                         width="stretch")

        st.markdown("**d · Save** — one file: links, parameters, path aliases "
                    "and, later, derived values.")
        if st.button("Save cuau.json", key="nano_demo_save",
                     disabled=not len(org.project)):
            try:
                written = org.save()
                st.success(f"Saved {written} "
                           f"({written.stat().st_size / 1024:.0f} kB)")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        if org.path.exists():
            with st.expander("Links table — the re-importable export",
                             expanded=False):
                st.dataframe(org.links_table(), hide_index=True,
                             width="stretch")

    if META.exists() and (org is not None or STORE.exists()):
        with st.expander("Start over", expanded=False):
            doomed = [p for p in (STORE, RESULTS) if p.exists()]
            st.caption("Removes only the organizer and the stored fits — the "
                       "simulated campaign stays. Would delete: "
                       + (", ".join(f"`{p}`" for p in doomed) or "nothing"))
            sure = st.checkbox("Yes, delete those", key="nano_demo_sure")
            if st.button("Start over", key="nano_demo_reset",
                         disabled=not sure):
                for target in doomed:
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                st.session_state.pop(ORG, None)
                st.session_state.pop(OUTCOMES, None)
                org = None
                st.success("Removed. Create the organizer again above.")

    same_in_python(f'''
from NanoOrganizer import Organizer

org = Organizer(ROOT / "cuau.json", name="Cu-Au CO2RR library")

for stage in {STAGES}:            # what was written down
    org.ingest(CAMPAIGN / "MetaData" / f"{{stage}}_dict.py")

BY_HAND = {BY_HAND}
for sample in org.ids():                              # what was not
    for modality, folder in BY_HAND.items():
        source = CAMPAIGN / folder / sample
        if source.is_dir():
            org.link(sample, modality, str(source), stage="characterization")

org.catalog(counts=True)
org.save()
org.links_table()
''')

ready = org is not None and len(org.project) > 0

# ---------------------------------------------------------------------------
# 3 · Look — notebook 12, parts A and B
# ---------------------------------------------------------------------------

with look:
    st.caption("Mirrors `notebook/12_use_organizer` parts **A** (look at it) "
               "and **B** (load data). No data is read until B.")
    if not ready:
        st.info("Build the organizer first — tab **2 · Build**.", icon="👈")
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("**`describe()`** — the first cell of a session")
            with contextlib.redirect_stdout(io.StringIO()):
                text = org.describe()
            st.code(text, language=None)
        with right:
            st.markdown("**`tree()`** — structure of the live session, not "
                        "the last save")
            st.code(org.tree(depth=2, limit=5), language=None)

        st.markdown("**`ids(query)`** — answer a question without changing "
                    "the selection")
        query = st.text_input(
            "Query", value="`synthesis.composition.nominal_x_Au` >= 0.5",
            key="nano_demo_query",
            help="A pandas expression over org.table(); dotted names need "
                 "backticks.")
        try:
            found = org.ids(query) if query.strip() else org.ids()
            st.code(repr(found), language="python")
            failed = [s for s in found if s in org.ids(
                "`synthesis.status` != 'done'")]
            if failed:
                st.caption(f"{', '.join(failed)} answers too: a failed run "
                           f"keeps its nominal parameters. Add "
                           f"``and `synthesis.status` == 'done'`` to drop "
                           f"it.")
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        st.divider()
        with_uvvis = samples_with(org, "uvvis")
        if with_uvvis:
            sample = st.selectbox("Sample", with_uvvis,
                                  index=with_uvvis.index("CuAu05")
                                  if "CuAu05" in with_uvvis else 0,
                                  key="nano_demo_look_s")
            st.markdown("**`frames()`** — one row per file, with what its "
                        "name admitted: the time (`t_s`) and the temperature "
                        "(`T_c`) of the growth series. `t=` and `T=` select "
                        "on them by nearest value.")
            frames_table = org.frames(sample, "uvvis")
            st.dataframe(frames_table[[c for c in ("index", "file", "t_s",
                                                   "T_c")
                                       if c in frames_table]].head(6),
                         hide_index=True, width="stretch")

            st.markdown("**`data()`** — the numbers, no figure; "
                        "`lazy=True` opens nothing until it is indexed")
            try:
                x, Y, info = org.data(sample, "uvvis")
                lines = [f'x, Y, info = org.data("{sample}", "uvvis")'
                         f'      # x {x.shape}, Y {Y.shape}']
                _, _, at_t = org.data(sample, "uvvis", t=600)
                lines.append(f'org.data("{sample}", "uvvis", t=600)'
                             f'          # nearest frame: {at_t["labels"][0]}')
                _, _, at_T = org.data(sample, "uvvis", T=60)
                lines.append(f'org.data("{sample}", "uvvis", T=60)'
                             f'           # nearest by temperature: '
                             f'{at_T["labels"][0]}')
                if org.project.get_sample(sample).get_measurements(
                        modality="tem"):
                    frames = org.data(sample, "tem", lazy=True)
                    lines.append(f'frames = org.data("{sample}", "tem", '
                                 f'lazy=True)   # {len(frames)} files, none '
                                 f'read: {", ".join(frames.names)}')
                    image, meta = frames[1]
                    lines.append(f'image, meta = frames[1]'
                                 f'                     # {image.shape}, '
                                 f'{meta.get("nm_per_pixel")} nm/px — one '
                                 f'file opened')
                tomo = samples_with(org, "tomo")
                if tomo:
                    planes = org.data(tomo[0], "tomo", lazy=True)
                    plane, plane_meta = planes[len(planes) // 2]
                    lines.append(f'planes = org.data("{tomo[0]}", "tomo", '
                                 f'lazy=True)  # {len(planes)} planes, '
                                 f'memory-mapped')
                    lines.append(f'plane, meta = planes[{plane_meta["plane"]}]'
                                 f'               # {plane.shape} — one plane '
                                 f'of the volume, not the volume')
                st.code("\n".join(lines), language="python")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    same_in_python('''
from NanoOrganizer import Organizer

org = Organizer(ROOT / "cuau.json")
org.describe()
print(org.tree(depth=2, limit=5))
org.catalog()
org.ids("`synthesis.composition.nominal_x_Au` >= 0.5")   # selection unchanged

org.frames("CuAu05", "uvvis")                  # one row per file: t_s, T_c
x, Y, info = org.data("CuAu05", "uvvis")       # Y: (n_frames, n_points)
x, Y, info = org.data("CuAu05", "uvvis", t=600)
frames = org.data("CuAu05", "tem", lazy=True)  # resolved, not read
image, meta = frames[1]                        # one file opened
planes = org.data("CuAu01", "tomo", lazy=True) # a memory-mapped volume
plane, meta = planes[64]                       # one plane
''')

# ---------------------------------------------------------------------------
# 4 · Visualize — notebook 12, part C
# ---------------------------------------------------------------------------

with visualize:
    st.caption("Mirrors `notebook/12_use_organizer` part **C**. The figure "
               "follows what the data *is* — a curve, an image, a volume, a "
               "correlation — not which instrument made it.")
    if not ready or not samples_with(org, "uvvis"):
        st.info("Build the organizer first — tab **2 · Build**.", icon="👈")
    else:
        candidates = org.project.sample_ids()
        with_data = [s for s in candidates if techniques_of(org, s)]
        sample = st.selectbox(
            "Sample", with_data,
            index=with_data.index("CuAu01") if "CuAu01" in with_data else 0,
            key="nano_demo_vis_s",
            help="CuAu01 has the most: it got the tomogram, XPCS and the 2D "
                 "detector images.")
        have = set(techniques_of(org, sample))

        st.markdown("**Four groups, one call each** — `org.plot(sample, "
                    "technique, ax=ax)` into a figure made here")
        figure, axes = plt.subplots(2, 4, figsize=(16.0, 7.6))
        failed = []
        for ax, slot in zip(axes.ravel(), GALLERY):
            chosen = next(((m, r, kw) for m, r, kw in slot if (m, r) in have),
                          None)
            if chosen is None:
                ax.set_axis_off()
                continue
            modality, role, options = chosen
            try:
                org.plot(sample, modality, role=role, ax=ax, **options)
            except Exception as exc:
                ax.set_axis_off()
                failed.append(f"{modality}: {type(exc).__name__}: {exc}")
        figure.tight_layout()
        show_figure(figure, dpi=90)
        if failed:
            st.warning("Could not draw " + "; ".join(failed), icon="⚠️")

        st.divider()
        st.markdown("**Any technique, either engine** — static to keep, "
                    "interactive to handle. The tomogram turns around.")
        pairs = techniques_of(org, sample)
        labels = [f"{m} · {r}" if r else m for m, r in pairs]
        default = labels.index("tomo") if "tomo" in labels else 0
        left, middle, right = st.columns([2, 1, 1])
        picked = left.selectbox("Technique", labels, index=default,
                                key="nano_demo_vis_m")
        modality, role = pairs[labels.index(picked)]
        engine = middle.radio("Engine", ["static", "interactive"],
                              key="nano_demo_vis_engine", horizontal=True)
        options = {}
        if modality == "tomo":
            if engine == "interactive":
                options["mode"] = right.selectbox(
                    "Render", list(interactive.VOLUME_MODES),
                    key="nano_demo_vis_mode")
                voxel = org.measurement(sample, modality="tomo").meta.get(
                    "voxel_size_nm")
                if voxel:
                    options.update(voxel_size=float(voxel), unit="nm")
                options["title"] = f"{sample} tomogram"
            else:
                options.update(slab=16, cmap="bone")
        try:
            if engine == "interactive":
                st.plotly_chart(org.plot(sample, modality, role=role,
                                         engine="interactive", **options),
                                use_container_width=True)
            else:
                figure, ax = plt.subplots(figsize=(8.0, 4.8))
                org.plot(sample, modality, role=role, ax=ax, **options)
                show_figure(figure)
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        with_waxs = samples_with(org, "waxs1d")
        if with_waxs:
            st.divider()
            st.markdown("**`overlay()`** — one curve per sample. The (111) "
                        "reflection walks to lower q as gold opens the "
                        "lattice: Vegard, by eye.")
            chosen = st.multiselect(
                "Samples to overlay", with_waxs,
                default=[s for s in ("CuAu01", "CuAu03", "CuAu05", "CuAu08")
                         if s in with_waxs] or with_waxs[:4],
                key="nano_demo_overlay")
            if chosen:
                try:
                    figure, ax = plt.subplots(figsize=(8.5, 4.2))
                    org.overlay("waxs1d", sample_ids=chosen, ax=ax,
                                verbose=False, xlim=(2.6, 3.06))
                    show_figure(figure)
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    same_in_python('''
import matplotlib.pyplot as plt

fig, axes = plt.subplots(2, 4, figsize=(16, 7.6))
org.plot("CuAu01", "uvvis", ax=axes[0, 0])              # coloured by time
org.plot("CuAu01", "waxs1d", ax=axes[0, 1])
org.plot("CuAu01", "saxs1d", ax=axes[0, 2])             # log-log, from the registry
org.plot("CuAu01", "ec", role="co2-rr-fe", ax=axes[0, 3])
org.plot("CuAu01", "tem", ax=axes[1, 0], cmap="gray")   # on nanometre axes
org.plot("CuAu01", "sem", ax=axes[1, 1], cmap="gray")
org.plot("CuAu01", "tomo", ax=axes[1, 2], slab=16)      # a slab projection
org.plot("CuAu01", "xpcs_g2", ax=axes[1, 3])

org.plot("CuAu01", "tomo", engine="interactive", mode="isosurface",
         voxel_size=2.0, unit="nm").show()              # turn it around

fig, ax = plt.subplots()
org.overlay("waxs1d", sample_ids=["CuAu01", "CuAu03", "CuAu05", "CuAu08"],
            ax=ax, xlim=(2.6, 3.06))                      # the (111), moving
''')

# ---------------------------------------------------------------------------
# 5 · Analyze — notebook 12, part D
# ---------------------------------------------------------------------------

with analyze:
    st.caption("Mirrors `notebook/12_use_organizer` part **D** — the kernel "
               "on arrays first, a look at the segmentation, *then* the "
               "batches. Fitting and drawing are always two separate calls.")
    with_waxs = samples_with(org, "waxs1d") if ready else []
    if not with_waxs:
        st.info("Build the organizer first — tab **2 · Build**.", icon="👈")
    else:
        truth = pd.read_csv(TRUTH).set_index("sample_id") if TRUTH.exists() \
            else None

        st.markdown("**The kernel** — `fit_peaks(x, y, …)` takes two arrays "
                    "and nothing else. The (111) position gives the lattice "
                    "parameter, and Vegard's law run backwards gives the "
                    "composition.")
        controls = st.columns([1, 2, 1, 1, 1])
        sample = controls[0].selectbox(
            "Sample", with_waxs,
            index=with_waxs.index("CuAu05") if "CuAu05" in with_waxs else 0,
            key="nano_demo_fit_s")
        q, intensity, info = org.data(sample, "waxs1d")
        window = controls[1].slider(
            "Fit window (Å⁻¹)", float(np.floor(q.min() * 10) / 10),
            float(np.ceil(q.max() * 10) / 10), WAXS_FIT["x_range"], 0.05,
            key="nano_demo_fit_window")
        n_peaks = int(controls[2].number_input("Peaks", 1, 4,
                                               WAXS_FIT["n_peaks"],
                                               key="nano_demo_fit_n"))
        shape = controls[3].selectbox(
            "Shape", SHAPES, index=SHAPES.index(WAXS_FIT["shape"]),
            key="nano_demo_fit_shape")
        background = controls[4].selectbox(
            "Background", BACKGROUNDS,
            index=BACKGROUNDS.index(WAXS_FIT["background"]),
            key="nano_demo_fit_bg")
        params = dict(x_range=tuple(window), n_peaks=n_peaks, shape=shape,
                      background=background)

        fit = None
        try:
            fit = fit_peaks(q, intensity[0], **params)       # the analysis
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        if fit is not None:
            plot_col, numbers_col = st.columns([3, 2])
            with plot_col:
                figure, ax = plt.subplots(figsize=(7.5, 5.2))
                plots.plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, ax=ax,
                               xlabel="q (Å$^{-1}$)", ylabel="I(q)",
                               title=f"{sample} — R² = {fit.r2:.4f}")
                show_figure(figure)                           # the picture
            with numbers_col:
                centre = fit.params["peak1_center"]
                lattice = mat.lattice_from_q(centre)
                x_au = mat.fraction_from_lattice(lattice)
                st.metric("R²", f"{fit.r2:.4f}")
                cells = st.columns(2)
                cells[0].metric("(111) at", f"{centre:.4f} Å⁻¹",
                                f"± {fit.errors.get('peak1_center', 0):.1e}",
                                delta_color="off")
                cells[1].metric("Lattice parameter", f"{lattice:.4f} Å")
                true_x = (float(truth.loc[sample, "x_Au"])
                          if truth is not None and sample in truth.index
                          else None)
                st.metric("x(Au) from Vegard", f"{x_au:.3f}",
                          f"{x_au - true_x:+.3f} vs the answer key"
                          if true_x is not None else None,
                          delta_color="off")
                st.dataframe(pd.DataFrame({
                    "value": fit.params,
                    "± 1σ": {k: fit.errors.get(k) for k in fit.params},
                }), width="stretch", height=240)
                st.caption("Try one peak across both reflections: the sharp "
                           "(111) still pins the centre, so the composition "
                           "barely moves — but R² drops and the residual "
                           "grows a second peak. The residual is the tell, "
                           "not the headline number.")

        st.divider()
        with_tem = samples_with(org, "tem")
        if with_tem:
            st.markdown("**Look before you trust a size** — the outlines one "
                        "TEM frame was segmented into. A histogram looks "
                        "plausible whether these were right or not.")
            left, right, notes = st.columns([1, 2, 1])
            seg_sample = left.selectbox(
                "Micrograph of", with_tem,
                index=with_tem.index("CuAu05") if "CuAu05" in with_tem else 0,
                key="nano_demo_seg_s")
            n_frames = len(org.measurement(seg_sample, modality="tem")
                           .resolve(org.resolver))
            frame = int(left.number_input("Frame", 0, max(n_frames - 1, 0), 0,
                                          key="nano_demo_seg_frame"))
            try:
                segmentation = org.segment(seg_sample, "tem",
                                           image_index=frame)  # the analysis
                left.metric("Particles", segmentation.n_particles)
                with right:
                    figure, ax = plt.subplots(figsize=(6.0, 6.0))
                    org.plot_segmentation(segmentation, ax=ax)  # the picture
                    show_figure(figure, dpi=90)
                notes.caption("Outlines should trace whole particles. A line "
                              "cutting through one means the seeds are too "
                              "close; specks on the support mean the contrast "
                              "floor is too low. The TEM batch below pools "
                              "every frame of every sample into sizes — this "
                              "is the frame-by-frame check behind it.")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        st.divider()
        st.markdown("**The batches** — happy with the parameters, spend them "
                    "on every sample. Nine analyses; each writes its numbers "
                    "back as `derived.*` columns, and `link=True` also stores "
                    "the two peak fits' curves beside cuau.json so tab 6 can "
                    "redraw them without refitting.")
        st.dataframe(pd.DataFrame(
            [{"what": label, "call": call_text(analysis, options)}
             for label, analysis, options in BATCHES]),
            hide_index=True, width="stretch")
        if st.button("Run the campaign's analyses", type="primary",
                     key="nano_demo_batch"):
            outcomes = []
            try:
                with st.spinner("Fitting, measuring and sizing…"):
                    for label, analysis, options in BATCHES:
                        frame_ = org.batch(analysis, verbose=False, **options)
                        ok = int(frame_["ok"].sum()) if "ok" in frame_ else 0
                        failed = (frame_.loc[~frame_["ok"], "message"]
                                  .dropna().unique()
                                  if "ok" in frame_ and "message" in frame_
                                  else [])
                        outcomes.append({"analysis": label,
                                         "succeeded": f"{ok}/{len(frame_)}",
                                         "why not": "; ".join(failed)})
                    org.save()
                st.session_state[OUTCOMES] = outcomes
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        outcomes = st.session_state.get(OUTCOMES)
        if outcomes:
            total = sum(int(o["succeeded"].split("/")[0]) for o in outcomes)
            runs = sum(int(o["succeeded"].split("/")[1]) for o in outcomes)
            st.success(f"{total}/{runs} analyses succeeded across "
                       f"{len(outcomes)} batches; saved to {STORE.name}")
            st.dataframe(pd.DataFrame(outcomes), hide_index=True,
                         width="stretch")

    batch_lines = "\n".join(call_text(analysis, options)
                            for _, analysis, options in BATCHES)
    same_in_python(f'''
import matplotlib.pyplot as plt
from NanoOrganizer.analysis import fit_peaks
from NanoOrganizer.demo import materials as mat
from NanoOrganizer.viz.plots import plot_fit

q, I, info = org.data("CuAu05", "waxs1d")
fit = fit_peaks(q, I[0], n_peaks=2, x_range=(2.5, 3.6),
                shape="pseudo_voigt", background="linear")   # the analysis

fig, ax = plt.subplots()
plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, ax=ax)       # the picture

a = mat.lattice_from_q(fit.params["peak1_center"])           # Å
x_au = mat.fraction_from_lattice(a)                          # Vegard, backwards

seg = org.segment("CuAu05", "tem")                           # the analysis
org.plot_segmentation(seg)                                   # the picture

{batch_lines}
org.save()
''')

# ---------------------------------------------------------------------------
# 6 · Compare — notebook 12, parts E and F
# ---------------------------------------------------------------------------

with compare:
    st.caption("Mirrors `notebook/12_use_organizer` parts **E** (ids → table "
               "→ plot) and **F** (reload the stored fits, no refitting).")
    columns = (org.table(all_samples=True).columns if ready else [])
    if not all(name in columns for name in NEEDED) or not TRUTH.exists():
        st.info("Run the campaign's analyses first — tab **5 · Analyze**. "
                "That is what puts recovered values into the table.",
                icon="👈")
    else:
        # E · ids → table → numbers, all before anything is drawn.
        ids = org.ids("`synthesis.status` == 'done'")
        table = org.table(sample_ids=ids)
        truth = pd.read_csv(TRUTH).set_index("sample_id")
        check = composition_check(table, truth)

        worst_eds = float((check["x_EDS"] - check["x_true"]).abs().max())
        worst_waxs = float((check["x_WAXS"] - check["x_true"]).abs().max())
        worst_band = float((check["band_nm"] - check["band_true_nm"])
                           .abs().max())
        volcano = table.set_index("sample_id")[
            "testing.performance.j_CO_mA_cm2"]
        best = str(volcano.idxmax())
        numbers = st.columns(4)
        numbers[0].metric("EDS composition within", f"± {worst_eds:.3f}")
        numbers[1].metric("WAXS composition within", f"± {worst_waxs:.3f}")
        numbers[2].metric("Plasmon band within", f"{worst_band:.1f} nm")
        numbers[3].metric("Most CO", best,
                          f"x(Au) = {truth.loc[best, 'x_Au']:.2f}",
                          delta_color="off")

        st.markdown("**Composition three ways** — an X-ray detector on an "
                    "electron microscope and a diffractometer in another room "
                    "land on the same number; XPS, which sees only the top "
                    "nanometres, lands above it, because gold segregates out.")
        figure, axes = plt.subplots(1, 3, figsize=(14.0, 4.4))
        draw_composition(check, ax=axes)
        figure.tight_layout()
        show_figure(figure, dpi=100)

        sizes_col, volcano_col = st.columns(2)
        with sizes_col:
            st.markdown("**Three sizes, an order of magnitude apart, all "
                        "right** — each technique sees a different object.")
            figure, ax = plt.subplots(figsize=(6.5, 4.6))
            draw_sizes(check, ax)
            show_figure(figure)
        with volcano_col:
            st.markdown("**The volcano, straight off the table** — "
                        "`plot_compare` on an authored and a computed "
                        "column.")
            try:
                figure, ax = plt.subplots(figsize=(6.5, 4.6))
                plots.plot_compare(table, "computation.descriptors.E_ads_CO_eV",
                                   "testing.performance.j_CO_mA_cm2", ax=ax,
                                   title="Sabatier volcano",
                                   xlabel="CO binding energy (eV)",
                                   ylabel="CO partial current (mA cm$^{-2}$)")
                show_figure(figure)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        with st.expander("The table behind the figures", expanded=False):
            st.dataframe(check.round(3), width="stretch")

        # F · reload — off disk, nothing refitted.
        st.divider()
        st.markdown("**Reload, and go round again** — a fresh `Organizer` "
                    "from the saved file; the fitted curves come off disk, "
                    "nothing is refitted.")
        stored = org.results()
        fitted_samples = (sorted(stored["sample_id"].unique())
                          if not stored.empty else [])
        if fitted_samples:
            left, middle, right = st.columns([1, 1, 2])
            sample = left.selectbox(
                "Sample", fitted_samples,
                index=fitted_samples.index("CuAu05")
                if "CuAu05" in fitted_samples else 0,
                key="nano_demo_reload_s")
            modality = middle.selectbox("Fit of", ["waxs1d", "uvvis"],
                                        key="nano_demo_reload_m")
            if left.button("Reload from disk and redraw",
                           key="nano_demo_reload", width="stretch"):
                try:
                    later = Organizer(STORE)
                    result = later.result(sample, "peak_fit",
                                          modality=modality)    # no refit
                    with right:
                        figure, ax = plt.subplots(figsize=(6.5, 4.6))
                        plots.plot_peak_fit(result, ax=ax)      # drawn
                        show_figure(figure)
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    same_in_python('''
import pandas as pd
import matplotlib.pyplot as plt
from NanoOrganizer import Organizer
from NanoOrganizer.demo import materials as mat
from NanoOrganizer.demo.signals import EDS_K_FACTOR_AU_CU, XPS_RSF
from NanoOrganizer.viz.plots import plot_compare, plot_peak_fit

ids = org.ids("`synthesis.status` == 'done'")          # CuAu09 failed
table = org.table(sample_ids=ids)
truth = pd.read_csv(ROOT / "truth.csv").set_index("sample_id")
t = table.set_index("sample_id").reindex(truth.index)

x_waxs = mat.fraction_from_lattice(mat.lattice_from_q(t["derived.waxs1d_peak1_center"]))
x_eds = mat.fraction_from_signals(t["derived.eds_au_area"], t["derived.eds_cu_area"],
                                  gold_factor=EDS_K_FACTOR_AU_CU)
x_xps = mat.fraction_from_signals(t["derived.xps_au_area"], t["derived.xps_cu_area"],
                                  gold_factor=XPS_RSF["Au 4f7/2"],
                                  copper_factor=XPS_RSF["Cu 2p3/2"])

fig, ax = plt.subplots()
plot_compare(table, "computation.descriptors.E_ads_CO_eV",
             "testing.performance.j_CO_mA_cm2", ax=ax,
             title="Sabatier volcano")                    # the volcano

later = Organizer(ROOT / "cuau.json")                     # F: no refitting
result = later.result("CuAu05", "peak_fit", modality="waxs1d")
fig, ax = plt.subplots()
plot_peak_fit(result, ax=ax)
''')

# ---------------------------------------------------------------------------
# Hand over to the workflow pages
# ---------------------------------------------------------------------------

st.divider()
if ready:
    left, right = st.columns([3, 1])
    left.caption("The workflow pages — Explore & Filter, Visualize, Analyze, "
                 "Compare — work on one shared organizer. Hand them this one "
                 "and carry on with buttons.")
    if right.button("Use this organizer in the workflow pages",
                    key="nano_demo_handover", width="stretch"):
        set_workbench(org)
        # The sidebar is drawn before the page: rerun so it names the
        # organizer it now holds.
        st.rerun()
    if get_workbench() is org:
        st.success("This organizer is open in the workflow pages — "
                   "**🔎 Explore & Filter**, **📈 Visualize**, **🧪 Analyze** "
                   "and **📊 Compare** in the sidebar all work on it now.",
                   icon="✅")
else:
    st.caption("Once the organizer is built, it can be handed to the workflow "
               "pages from here.")
