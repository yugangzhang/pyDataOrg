#!/usr/bin/env python3
"""Render the figures the README shows, from the generated Cu–Au campaign.

Nothing here is special-cased for the documentation: the campaign is written
into a temporary folder, the organizer is built with the very calls the README
walkthrough shows — ingest the four metadata dicts, link the four bare folders
by hand, batch the analyses — and every panel is drawn by the package's own
plot functions into axes made here. If a figure stops reproducing, the
pipeline changed; if the README's code changes, change this file with it.

    python scripts/make_readme_figures.py                    # everything
    python scripts/make_readme_figures.py --only campaign    # the walkthrough
    python scripts/make_readme_figures.py --only tomogram    # the 3D still

Writes PNGs into ``docs/images/``:

``campaign_gallery.png``   step C — eight techniques, all four groups
``campaign_fit.png``       step D — the WAXS fit and the segmentation check
``campaign_compare.png``   step E — composition three ways, the plasmon band,
                           three sizes, and the volcano off the table
``demo_tomogram.png``      the interactive tomogram as a still (docs/web_app.md)

The tomogram is a Plotly figure, so writing it to PNG needs ``kaleido``
(``pip install kaleido``). It is not a dependency of the package: without it
that one figure is skipped and the rest still build.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
DPI = 110
SURFACE = "#fcfcfb"


def save(figure, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    figure.patch.set_facecolor(SURFACE)
    figure.savefig(OUT / name, dpi=DPI, bbox_inches="tight",
                   facecolor=SURFACE)
    plt.close(figure)
    shrink(OUT / name)
    print(f"  wrote docs/images/{name}  "
          f"({(OUT / name).stat().st_size // 1024} KB)")


def shrink(path: Path) -> None:
    """Re-encode in place. These images live in git for the life of the repo."""
    try:
        from PIL import Image
    except ImportError:
        return
    Image.open(path).convert("RGB").save(path, optimize=True)


# ---------------------------------------------------------------------------
# Steps 0 and 1 — exactly as the README does them
# ---------------------------------------------------------------------------

def build(base: Path):
    """Write the campaign under *base* and build the organizer from it."""
    # demo_root() reads the variable, so the README's own ROOT line lands in
    # the scratch folder rather than in somebody's working demo.
    os.environ["NANOORGANIZER_DEMO_ROOT"] = str(base)

    from NanoOrganizer import Organizer
    from NanoOrganizer.demo import (
        build_showcase_project, demo_root, showcase_truth,
    )

    ROOT = demo_root("CuAu")
    CAMPAIGN = ROOT / "Campaign"
    # step 0 — what `python -m NanoOrganizer.demo --campaign` does
    build_showcase_project(CAMPAIGN)
    showcase_truth().to_csv(ROOT / "truth.csv", index=False)

    # step 1 — ingest what was written down, link what was not
    org = Organizer(ROOT / "cuau.json", name="Cu-Au CO2RR library")
    for stage in ("Synthesis", "Characterization", "Testing", "Computation"):
        org.ingest(CAMPAIGN / "MetaData" / f"{stage}_dict.py")

    BY_HAND = {"tem": "TEMData", "sem": "SEMData", "dls": "DLSData",
               "tomo": "TomoData"}
    for sample in org.ids():
        for modality, folder in BY_HAND.items():
            source = CAMPAIGN / folder / sample
            if source.is_dir():
                extra = {"voxel_size_nm": 2.0} if modality == "tomo" else {}
                org.link(sample, modality, str(source),
                         stage="characterization", **extra)
    org.save()
    return org, ROOT


# ---------------------------------------------------------------------------
# Step C — every group, drawn from arrays into one figure
# ---------------------------------------------------------------------------

def gallery(org) -> None:
    from NanoOrganizer.viz.plots import plot_curves, plot_image, plot_series
    from NanoOrganizer.viz.show import project_volume

    # -- the README's step C, verbatim --------------------------------------
    done = org.ids("`synthesis.status` == 'done'")
    x_nominal = org.table(sample_ids=done)["synthesis.composition.nominal_x_Au"]

    x, Y, info = org.data("CuAu05", "uvvis")
    q = org.data("CuAu01", "waxs1d")[0]                 # one q grid for all
    waxs = [org.data(s, "waxs1d")[1][0] for s in done]

    eds, g2 = [], []
    for s in ("CuAu01", "CuAu05", "CuAu08"):
        energy, counts, _ = org.data(s, "eds")
        eds.append((s, energy, counts[0]))
    for s in ("CuAu01", "CuAu04", "CuAu08"):            # XPCS got three samples
        tau, G, _ = org.data(s, "xpcs_g2")
        g2.append((s, tau, G[0]))

    potential, FE, fe = org.data("CuAu06", "ec", role="co2-rr-fe")
    products = [(name[3:-4], potential, row)
                for name, row in zip(fe["labels"], FE)]

    tem, tem_info = org.data("CuAu05", "tem", frame=0)
    sem, sem_info = org.data("CuAu05", "sem", frame=0)
    volume, _ = org.data("CuAu01", "tomo")
    voxel = org.measurement("CuAu01", modality="tomo").meta["voxel_size_nm"]
    slab, detail = project_volume(volume, projection="max projection", slab=16)

    tem_nm = tem.shape[0] * tem_info["nm_per_pixel"]    # square frames
    sem_nm = sem.shape[0] * sem_info["nm_per_pixel"]
    slab_nm = slab.shape[0] * voxel

    fig, axes = plt.subplots(2, 4, figsize=(21, 9))
    plot_series(x, Y, info["t_s"], ax=axes[0, 0], xlabel="wavelength (nm)",
                ylabel="absorbance", colorbar_label="time (s)",
                title="UV-Vis · CuAu05 growth, coloured by time")
    plot_series(q, waxs, x_nominal.values, ax=axes[0, 1], xlim=(2.5, 3.25),
                xlabel="q (Å⁻¹)", ylabel="intensity", colorbar_label="x(Au)",
                title="WAXS (111) · walks left as gold enters")
    plot_curves(eds, ax=axes[0, 2], logy=True, xlim=(0.5, 11.0),
                xlabel="energy (keV)", ylabel="counts",
                title="EDS · Cu Kα 8.05, Au Lα 9.71 keV")
    plot_curves(products, ax=axes[0, 3], marker="o", markersize=5,
                xlabel="potential (V vs RHE)",
                ylabel="Faradaic efficiency (%)",
                title="CO₂RR · CuAu06, where the charge goes")
    plot_image(tem, ax=axes[1, 0], cmap="gray", colorbar=False,
               extent=(0, tem_nm, tem_nm, 0), xlabel="nm", ylabel="nm",
               title="TEM · primary particles, dark on film")
    plot_image(sem, ax=axes[1, 1], cmap="gray", colorbar=False,
               extent=(0, sem_nm, sem_nm, 0), xlabel="nm", ylabel="nm",
               title="SEM · agglomerates, bright on support")
    plot_image(slab, ax=axes[1, 2], cmap="magma", colorbar=False,
               extent=(0, slab_nm, slab_nm, 0), xlabel="nm", ylabel="nm",
               title=f"Tomography · CuAu01, {detail}")
    plot_curves(g2, ax=axes[1, 3], logx=True, marker="o", markersize=4,
                xlabel="lag τ (s)", ylabel="g₂(τ)",
                title="XPCS · decay rate → aggregate size")
    fig.tight_layout()
    # -----------------------------------------------------------------------
    save(fig, "campaign_gallery.png")


# ---------------------------------------------------------------------------
# Step D — the kernel on arrays, then the segmentation check
# ---------------------------------------------------------------------------

def fit_and_segment(org) -> None:
    from NanoOrganizer.analysis import fit_peaks, segment_micrograph
    from NanoOrganizer.demo import materials as mat
    from NanoOrganizer.viz.plots import plot_fit, plot_segmentation

    q, W, _ = org.data("CuAu05", "waxs1d")

    # -- the README's step D, verbatim --------------------------------------
    fit = fit_peaks(q, W[0], n_peaks=2, x_range=(2.5, 3.6),
                    shape="pseudo_voigt", background="linear")
    lattice = mat.lattice_from_q(fit.params["peak1_center"])
    x_au = mat.fraction_from_lattice(lattice)

    seg = segment_micrograph(org.measurement("CuAu05", modality="tem"),
                             org.resolver)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6),
                             gridspec_kw={"width_ratios": [1.35, 1]})
    plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, ax=axes[0],
             xlabel="q (Å⁻¹)", ylabel="intensity",
             title=f"CuAu05 · R² = {fit.r2:.4f} → x(Au) = {x_au:.3f}")
    plot_segmentation(seg, ax=axes[1])
    # -----------------------------------------------------------------------
    save(fig, "campaign_fit.png")


# ---------------------------------------------------------------------------
# Step D (batch) and E — the table, against the answer key
# ---------------------------------------------------------------------------

def batch(org) -> None:
    quiet = dict(verbose=False)
    org.batch("peak_fit", modality="waxs1d", link=True, x_range=(2.5, 3.6),
              n_peaks=2, shape="pseudo_voigt", background="linear", **quiet)
    org.batch("peak_fit", modality="uvvis", link=True, x_range=(470.0, 800.0),
              reduce="last_decile", background="linear", **quiet)
    org.batch("curve_metrics", modality="eds", prefix="eds_cu_",
              x_min=7.7, x_max=8.4, **quiet)
    org.batch("curve_metrics", modality="eds", prefix="eds_au_",
              x_min=9.4, x_max=10.0, **quiet)
    org.batch("curve_metrics", modality="xps", role="cu2p", prefix="xps_cu_",
              x_min=929, x_max=937, **quiet)
    org.batch("curve_metrics", modality="xps", role="au4f", prefix="xps_au_",
              x_min=81.5, x_max=86.0, **quiet)
    org.batch("particle_sizing", modality="tem", **quiet)
    org.batch("particle_sizing", modality="sem", max_diameter_nm=500,
              min_circularity=0.5, **quiet)
    org.batch("curve_metrics", modality="dls", x_min=5, x_max=120, **quiet)
    org.save()


def compare(org, ROOT: Path) -> None:
    from NanoOrganizer.demo import materials as mat
    from NanoOrganizer.demo.signals import EDS_K_FACTOR_AU_CU, XPS_RSF
    from NanoOrganizer.viz.plots import plot_compare

    table = org.table(sample_ids=org.ids("`synthesis.status` == 'done'"))
    truth = pd.read_csv(ROOT / "truth.csv").set_index("sample_id")

    check = pd.DataFrame({
        "x_true": truth["x_Au"],
        "EDS (bulk)": mat.fraction_from_signals(
            table["derived.eds_au_area"], table["derived.eds_cu_area"],
            gold_factor=EDS_K_FACTOR_AU_CU),
        "WAXS (Vegard)": mat.fraction_from_lattice(
            mat.lattice_from_q(table["derived.waxs1d_peak1_center"])),
        "XPS (surface)": mat.fraction_from_signals(
            table["derived.xps_au_area"], table["derived.xps_cu_area"],
            gold_factor=XPS_RSF["Au 4f7/2"], copper_factor=XPS_RSF["Cu 2p3/2"]),
        "band_true_nm": truth["true_lspr_nm"],
        "band_fitted_nm": table["derived.uvvis_peak1_center"],
        "TEM": table["derived.tem_d_mean"],
        "DLS": table["derived.dls_x_at_max"],
        "SEM": table["derived.sem_d_mean"],
    }).reset_index()

    composition = check.melt(
        id_vars=["sample_id", "x_true"], var_name="technique",
        value_vars=["EDS (bulk)", "WAXS (Vegard)", "XPS (surface)"],
        value_name="x_measured")
    sizes = check.melt(id_vars=["sample_id", "x_true"], var_name="technique",
                       value_vars=["TEM", "DLS", "SEM"],
                       value_name="diameter_nm")

    # -- the README's step E, verbatim -------------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(22, 5))
    plot_compare(composition, "x_true", "x_measured", color_by="technique",
                 label_points=False, ax=axes[0],
                 xlabel="x(Au) the generator used", ylabel="x(Au) measured",
                 title="Composition three ways — XPS sits above: Au segregates")
    axes[0].axline((0, 0), slope=1, linestyle="--", color="0.6")
    plot_compare(check, "band_true_nm", "band_fitted_nm", ax=axes[1],
                 xlabel="band the generator used (nm)", ylabel="fitted band (nm)",
                 title="One plasmon band that moves — an alloy")
    axes[1].axline((550, 550), slope=1, linestyle="--", color="0.6")
    plot_compare(sizes, "x_true", "diameter_nm", color_by="technique",
                 label_points=False, logy=True, ax=axes[2],
                 xlabel="x(Au)", ylabel="diameter (nm)",
                 title="Three sizes, all of them right")
    plot_compare(org.table(), "computation.descriptors.E_ads_CO_eV",
                 "testing.performance.j_CO_mA_cm2", ax=axes[3],
                 xlabel="ΔE(CO) from DFT (eV)", ylabel="CO partial current (mA cm⁻²)",
                 title="Sabatier volcano, straight off the table")
    fig.tight_layout()
    save(fig, "campaign_compare.png")

    errors = {
        "max |x_EDS - x|": (check["EDS (bulk)"] - check.x_true).abs().max(),
        "max |x_WAXS - x|": (check["WAXS (Vegard)"] - check.x_true).abs().max(),
        "max |band error| nm": (check.band_fitted_nm
                                - check.band_true_nm).abs().max(),
        "max |x_XPS - surface|": (check["XPS (surface)"]
                                  - truth["true_surface_x_Au"].values).abs().max(),
    }
    for name, value in errors.items():
        print(f"  {name:24s} {value:.3f}")


# ---------------------------------------------------------------------------
# The tomogram, as the interactive viewer draws it
# ---------------------------------------------------------------------------

def tomogram(org) -> None:
    try:
        from NanoOrganizer.viz import interactive as iv
        volume, _ = org.data("CuAu01", "tomo")
        # `volume` rather than `isosurface`: the aggregate is only ~3% solid
        # by voxel, and after striding an isosurface of it fragments.
        figure = iv.volume_figure(volume, mode="volume", level=130,
                                  voxel_size=2.0, unit="nm",
                                  colorscale="Viridis", opacity=0.9,
                                  width=760, height=700)
    except ImportError as error:        # plotly is an optional extra
        print(f"  skipping the tomogram: {error}")
        return

    figure.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
                         margin=dict(l=20, r=10, t=34, b=20),
                         scene_camera=dict(eye=dict(x=1.45, y=1.35, z=0.95)))
    target = OUT / "demo_tomogram.png"
    try:
        figure.write_image(str(target), scale=2)
    except Exception as error:          # kaleido is not a declared dependency
        print(f"  skipping the tomogram: {error}")
        return

    # A 3D scene is laid out to fit any rotation, so a still of one rotation
    # has wide empty borders. Trim them rather than guess a camera distance.
    try:
        from PIL import Image, ImageChops
        image = Image.open(target).convert("RGB")
        background = Image.new("RGB", image.size, SURFACE)
        box = ImageChops.difference(image, background).getbbox()
        if box is not None:
            pad = 16
            image.crop((max(box[0] - pad, 0), max(box[1] - pad, 0),
                        min(box[2] + pad, image.width),
                        min(box[3] + pad, image.height))).save(target)
    except ImportError:
        pass
    shrink(target)
    print(f"  wrote docs/images/demo_tomogram.png  "
          f"({target.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", choices=("campaign", "tomogram"),
                        default=None,
                        help="draw one set of figures instead of both")
    args = parser.parse_args(argv)

    # A scratch folder: the README figures must not depend on, or disturb, a
    # campaign someone is working in under ~/Repos/OrgDemo.
    with tempfile.TemporaryDirectory(prefix="nano_readme_") as scratch:
        print(f"building the campaign in {scratch} …")
        org, ROOT = build(Path(scratch))
        if args.only in (None, "campaign"):
            gallery(org)
            fit_and_segment(org)
            print("running the batches …")
            batch(org)
            compare(org, ROOT)
        if args.only in (None, "tomogram"):
            tomogram(org)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
