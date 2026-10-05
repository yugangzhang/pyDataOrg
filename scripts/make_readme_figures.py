#!/usr/bin/env python3
"""Render the figures the README shows, from the generated demo project.

Nothing here is special-cased for the documentation: every panel goes through
the same ``Workbench``, the same loaders and the same house style a notebook
would use. If a figure stops reproducing, the pipeline changed.

    python scripts/make_readme_figures.py [project_root]

Writes PNGs into ``docs/images/`` along with the two structure listings the
README quotes verbatim.

The tomogram is a Plotly figure, so writing it to PNG needs ``kaleido``
(``pip install kaleido``). It is not a dependency of the package: without it
that one figure is skipped and the rest still build.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from NanoOrganizer import open_project, structure
from NanoOrganizer.analysis.reading import load_curve_set, load_image, load_volume
from NanoOrganizer.demo import build_showcase_project, materials as mat, showcase_truth
from NanoOrganizer.demo.signals import EDS_K_FACTOR_AU_CU, XPS_RSF
from NanoOrganizer.viz import plots

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


def ramp(index: int, total: int):
    """The single-hue ramp, for curves ordered by a continuous quantity."""
    return plots.sequential_cmap()(0.28 + 0.72 * index / max(total - 1, 1))


def scale_bar(ax, nm_per_pixel: float, length_nm: float, colour: str,
              behind: str) -> None:
    """A bar drawn from the image's own calibration, not from a guess.

    ``behind`` is the contrasting outline. A micrograph has no empty corner
    reserved for annotation, so a bar in one ink alone disappears the moment a
    particle lands under it.
    """
    from matplotlib import patheffects

    outline = [patheffects.withStroke(linewidth=3.2, foreground=behind)]
    width = length_nm / nm_per_pixel
    x0, y0 = ax.get_xlim()[1] * 0.05, ax.get_ylim()[0] * 0.94
    ax.plot([x0, x0 + width], [y0, y0], color=colour, lw=4,
            solid_capstyle="butt", path_effects=outline)
    label = (f"{length_nm / 1000:g} µm" if length_nm >= 1000
             else f"{length_nm:g} nm")
    # Offset in points, not data units: an image axis runs top-down, so a
    # data-unit offset would put the label under the bar on half of them.
    ax.annotate(label, xy=(x0 + width / 2, y0), xytext=(0, 9),
                textcoords="offset points", color=colour, fontsize=9,
                ha="center", va="bottom", path_effects=outline)


# ---------------------------------------------------------------------------
# 1. One figure per visualisation group
# ---------------------------------------------------------------------------

def gallery(wb, truth) -> None:
    figure, axes = plt.subplots(2, 4, figsize=(19.5, 8.6))

    # -- curves -------------------------------------------------------------
    m = wb.measurement("CuAu05", modality="uvvis")
    x, frames, _ = load_curve_set(m, wb.resolver)
    for index, y in enumerate(frames):
        axes[0, 0].plot(x, y, lw=1.3, color=ramp(index, len(frames)))
    plots.style(axes[0, 0], "wavelength (nm)", "absorbance",
                "UV-Vis · growth series (colour = time)")

    ids = list(truth.index)
    for index, sample_id in enumerate(ids):
        q, Y, _ = load_curve_set(wb.measurement(sample_id, modality="waxs1d"),
                                 wb.resolver)
        axes[0, 1].plot(q, Y[0] / Y[0].max() + 0.55 * index, lw=1.4,
                        color=ramp(index, len(ids)))
    axes[0, 1].set_xlim(2.4, 5.4)
    axes[0, 1].set_yticks([])
    plots.style(axes[0, 1], "q (Å⁻¹)", "intensity (offset)",
                "WAXS · fcc peaks walk left as Au enters")

    for index, sample_id in enumerate(("CuAu01", "CuAu05", "CuAu08")):
        e, Y, _ = load_curve_set(wb.measurement(sample_id, modality="eds"),
                                 wb.resolver)
        axes[0, 2].plot(e, Y[0], lw=1.5, color=plots.CATEGORICAL[index],
                        label=f"{sample_id}  x={truth.loc[sample_id, 'x_Au']:.2f}")
    axes[0, 2].set_xlim(0.5, 11.0)
    axes[0, 2].set_yscale("log")
    plots.style(axes[0, 2], "energy (keV)", "counts",
                "EDS · Cu Kα 8.05, Au Lα 9.71 keV")
    axes[0, 2].legend(frameon=False, fontsize=8.5)

    m = wb.measurement("CuAu06", modality="ec", role="co2-rr-fe")
    potential, efficiencies, info = load_curve_set(m, wb.resolver)
    for label, values, colour in zip(info["labels"], efficiencies,
                                     plots.CATEGORICAL):
        name = label.replace("FE_", "").replace(".dat", "")
        axes[0, 3].plot(potential, values, "o-", ms=5, lw=1.8, color=colour,
                        label=name)
    axes[0, 3].set_ylim(-6, 122)
    plots.style(axes[0, 3], "potential (V vs RHE)", "Faradaic efficiency (%)",
                "Electrochemistry · CuAu06 product split")
    axes[0, 3].legend(frameon=False, fontsize=8.5, ncol=3, loc="upper center")

    # -- images -------------------------------------------------------------
    # The scale bars are drawn from each image's own calibration, which the
    # demo writes into the micrograph the way an instrument would.
    tem, meta = load_image(wb.measurement("CuAu05", modality="tem"), wb.resolver)
    axes[1, 0].imshow(tem, cmap="gray")
    axes[1, 0].set_xticks([]); axes[1, 0].set_yticks([])
    scale_bar(axes[1, 0], meta["nm_per_pixel"], 50, "#0b0b0b", "#fcfcfb")
    plots.style(axes[1, 0], title="TEM · primary particles, dark on film")

    sem, meta = load_image(wb.measurement("CuAu05", modality="sem"), wb.resolver)
    axes[1, 1].imshow(sem, cmap="gray")
    axes[1, 1].set_xticks([]); axes[1, 1].set_yticks([])
    scale_bar(axes[1, 1], meta["nm_per_pixel"], 200, "#fcfcfb", "#0b0b0b")
    plots.style(axes[1, 1], title="SEM · agglomerates, bright on support")

    # -- a volume -----------------------------------------------------------
    # A single slice through a packed cluster is mostly gaps; a thin slab
    # projection is what anyone actually looks at.
    volume, _ = load_volume(wb.measurement("CuAu01", modality="tomo"),
                            wb.resolver)
    middle = volume.shape[0] // 2
    slab = volume[middle - 8:middle + 8].max(axis=0)
    axes[1, 2].imshow(slab, cmap="magma")
    axes[1, 2].set_xticks([]); axes[1, 2].set_yticks([])
    scale_bar(axes[1, 2], 2.0, 50, "#fcfcfb", "#0b0b0b")
    plots.style(axes[1, 2],
                title="Tomography · 16-voxel slab, maximum projection")

    # -- correlation --------------------------------------------------------
    for index, sample_id in enumerate(("CuAu01", "CuAu04", "CuAu08")):
        tau, Y, _ = load_curve_set(wb.measurement(sample_id, modality="xpcs"),
                                   wb.resolver)
        axes[1, 3].semilogx(tau, Y[0], "o-", ms=4, lw=1.6,
                            color=plots.CATEGORICAL[index], label=sample_id)
    plots.style(axes[1, 3], "lag τ (s)", "g₂(τ)",
                "XPCS · decay rate → hydrodynamic size")
    axes[1, 3].legend(frameon=False, fontsize=8.5)

    figure.tight_layout()
    save(figure, "demo_gallery.png")


# ---------------------------------------------------------------------------
# 2. Independent techniques, brought back together
# ---------------------------------------------------------------------------

def agreement(wb, truth) -> None:
    table = wb.table().set_index("sample_id").reindex(truth.index)

    gold = table["derived.eds_au_area"] / EDS_K_FACTOR_AU_CU
    x_eds = gold / (gold + table["derived.eds_cu_area"])
    lattice = 2 * np.pi * np.sqrt(3) / table["derived.waxs1d_peak1_center"]
    x_waxs = (lattice - mat.A_CU) / (mat.A_AU - mat.A_CU)
    surface_au = table["derived.xps_au_area"] / XPS_RSF["Au 4f7/2"]
    surface_cu = table["derived.xps_cu_area"] / XPS_RSF["Cu 2p3/2"]
    x_xps = surface_au / (surface_au + surface_cu)

    figure, axes = plt.subplots(1, 3, figsize=(16.5, 4.6))

    axes[0].plot([0, 1], [0, 1], "--", lw=1.5, color="0.65", label="generator")
    for name, values, colour, marker in (
            ("EDS (Cliff–Lorimer)", x_eds, plots.CATEGORICAL[0], "o"),
            ("WAXS (Vegard)", x_waxs, plots.CATEGORICAL[1], "s")):
        axes[0].plot(truth["x_Au"], values, marker, ms=9, color=colour,
                     label=name)
    plots.style(axes[0], "x(Au) the generator used", "x(Au) recovered",
                "Two instruments, one answer")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")

    axes[1].plot(truth["x_Au"], truth["true_lspr_nm"], "--", lw=1.5,
                 color="0.65", label="generator")
    axes[1].plot(truth["x_Au"], table["derived.uvvis_peak1_center"], "o", ms=9,
                 color=plots.CATEGORICAL[2], label="fitted band")
    plots.style(axes[1], "x(Au)", "plasmon band (nm)",
                "One band that moves — so it is an alloy")
    axes[1].legend(frameon=False, fontsize=9)

    axes[2].plot(truth["x_Au"], table["derived.tem_d_mean"], "o", ms=9,
                 color=plots.CATEGORICAL[0], label="TEM · primary")
    axes[2].plot(truth["x_Au"], table["derived.dls_x_at_max"], "s", ms=9,
                 color=plots.CATEGORICAL[1], label="DLS · hydrodynamic")
    axes[2].plot(truth["x_Au"], table["derived.sem_d_mean"], "^", ms=9,
                 color=plots.CATEGORICAL[2], label="SEM · agglomerate")
    axes[2].set_yscale("log")
    plots.style(axes[2], "x(Au)", "diameter (nm)",
                "Three sizes, all of them correct")
    axes[2].legend(frameon=False, fontsize=9, loc="center left")

    figure.tight_layout()
    save(figure, "demo_agreement.png")
    return x_eds, x_xps


# ---------------------------------------------------------------------------
# 3. The structure–property chain
# ---------------------------------------------------------------------------

def volcano(wb, truth, x_eds, x_xps) -> None:
    table = wb.table().set_index("sample_id").reindex(truth.index)
    figure, axes = plt.subplots(1, 3, figsize=(16.5, 4.6))

    axes[0].plot([0, 1], [0, 1], "--", lw=1.5, color="0.65",
                 label="no segregation")
    axes[0].plot(truth["x_Au"], x_eds, "o", ms=9, color=plots.CATEGORICAL[0],
                 label="EDS · bulk")
    # Slots 0–5 are spoken for by the six products in the middle panel, so the
    # two panels either side take hues from outside that set.
    axes[0].plot(truth["x_Au"], x_xps, "s", ms=9, color=plots.CATEGORICAL[7],
                 label="XPS · surface")
    plots.style(axes[0], "x(Au) bulk", "x(Au) measured",
                "Gold segregates — the gap is the information")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")

    products = ("H2", "CO", "HCOO-", "CH4", "C2H4", "EtOH")
    bottom = np.zeros(len(truth))
    for index, product in enumerate(products):
        values = np.array([mat.faradaic_efficiency(x)[product]
                           for x in truth["x_Au"]])
        axes[1].bar(np.arange(len(truth)), values, bottom=bottom, width=0.72,
                    color=plots.CATEGORICAL[index], label=product,
                    edgecolor=SURFACE, linewidth=2)
        bottom += values
    axes[1].set_xticks(np.arange(len(truth)))
    axes[1].set_xticklabels([f"{x:.2f}" for x in truth["x_Au"]], fontsize=8.5)
    plots.style(axes[1], "x(Au)", "Faradaic efficiency (%)",
                "Selectivity switches: hydrocarbons → CO")
    axes[1].set_title("Selectivity switches: hydrocarbons → CO",
                      color=plots.INK, fontsize=11, loc="left", pad=26)
    axes[1].grid(False, axis="x")
    axes[1].legend(frameon=False, fontsize=8.5, ncol=6, loc="lower center",
                   bbox_to_anchor=(0.5, 1.0), columnspacing=1.1,
                   handlelength=1.1, handletextpad=0.5)

    binding = table["computation.descriptors.E_ads_CO_eV"]
    current = table["testing.performance.j_CO_mA_cm2"]
    order = np.argsort(binding.values)
    axes[2].plot(binding.values[order], current.values[order], "o-", ms=10,
                 lw=2, color=plots.CATEGORICAL[6])
    best = current.idxmax()
    axes[2].annotate(f"{best} · x(Au) = {truth.loc[best, 'x_Au']:.2f}",
                     xy=(binding[best], current[best]),
                     xytext=(-118, -14), textcoords="offset points", fontsize=9,
                     color=plots.INK_SOFT,
                     arrowprops=dict(arrowstyle="->", color="0.45"))
    plots.style(axes[2], "ΔE(CO) from DFT (eV)",
                "CO partial current (mA cm⁻²)",
                "Sabatier volcano — too weak, or too strong")

    figure.tight_layout()
    save(figure, "demo_volcano.png")


# ---------------------------------------------------------------------------
# 4. The tomogram, as the interactive viewer draws it
# ---------------------------------------------------------------------------

def tomogram(wb) -> None:
    try:
        from NanoOrganizer.viz import interactive as iv
    except ImportError as error:        # plotly is an optional extra
        print(f"  skipping the tomogram: {error}")
        return

    volume, _ = load_volume(wb.measurement("CuAu01", modality="tomo"),
                            wb.resolver)
    # `volume` rather than `isosurface`: the aggregate is only ~3% solid by
    # voxel, and after striding an isosurface of it fragments into speckle.
    figure = iv.volume_figure(volume, mode="volume", level=130,
                              voxel_size=2.0, unit="nm", colorscale="Viridis",
                              opacity=0.9, width=760, height=700)
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

def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "~/NanoOrganizerDemo"
    print(f"building {root} …")
    build_showcase_project(root)
    wb = open_project(root)

    print("running the analyses the figures read …")
    wb.batch("curve_metrics", modality="eds", prefix="eds_cu_",
             x_min=7.7, x_max=8.4)
    wb.batch("curve_metrics", modality="eds", prefix="eds_au_",
             x_min=9.4, x_max=10.0)
    wb.batch("peak_fit", modality="waxs1d", x_range=(2.5, 3.6), n_peaks=2,
             shape="pseudo_voigt", background="linear")
    wb.batch("peak_fit", modality="uvvis", x_range=(470.0, 800.0),
             reduce="last_decile", background="linear")
    wb.batch("particle_sizing", modality="tem")
    wb.batch("particle_sizing", modality="sem", max_diameter_nm=500,
             min_circularity=0.5)
    wb.batch("curve_metrics", modality="dls", x_min=5, x_max=120)
    wb.batch("curve_metrics", modality="xps", role="cu2p", prefix="xps_cu_",
             x_min=929, x_max=937)
    wb.batch("curve_metrics", modality="xps", role="au4f", prefix="xps_au_",
             x_min=81.5, x_max=86.0)

    truth = showcase_truth().set_index("sample_id")

    print("drawing …")
    gallery(wb, truth)
    x_eds, x_xps = agreement(wb, truth)
    volcano(wb, truth, x_eds, x_xps)
    tomogram(wb)

    # Two listings, because they show different things: the folder layout, and
    # the descent *into* a file, which is the part `ls` cannot do.
    layout = structure.tree(root, depth=1, limit=20)
    module = Path(root).expanduser() / "MetaData" / "Characterization_dict.py"
    inside = structure.tree(
        f"{module}::Characterization_dict/CuAu05", depth=2, limit=4)
    # The demo records absolute paths, as an instrument would. Whose machine
    # built the documentation is not part of the example.
    home = str(Path.home())
    layout, inside = (text.replace(home, "~") for text in (layout, inside))

    (OUT / "structure_layout.txt").write_text(layout + "\n")
    (OUT / "structure_inside.txt").write_text(inside + "\n")
    print("  wrote docs/images/structure_layout.txt, structure_inside.txt")
    print(layout)
    print()
    print(inside)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
