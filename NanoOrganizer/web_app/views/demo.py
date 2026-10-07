#!/usr/bin/env python3
"""
Demo — notebooks 10 → 11 → 12, with buttons.

The three workflow notebooks walk one small campaign from raw files to a
structure–property plot. This page is the same walk in six tabs, calling the
same package functions in the same order:

1 · Simulate    ``notebook/10`` — a rig writes files into three folder trees
2 · Build       ``notebook/11`` — ``Organizer(lab.json)``, ingest the dict,
                link the rest by hand, save
3 · Look        ``notebook/12`` A/B — describe, tree, catalog, ids, frames,
                data eager and lazy
4 · Visualize   ``notebook/12`` C — ``plot`` and ``overlay``
5 · Analyze     ``notebook/12`` D — the kernel on arrays, *then* the batch
6 · Compare     ``notebook/12`` E/F — check against the answer key, reload
                the stored fits without refitting

Every tab ends with **The same in Python**: the calls it just made, so nothing
here is a GUI-only path. Analysing and drawing are always two calls — the page
composes them; no function on it does both.

The organizer built here is the page's own (``nano_demo_org``), separate from
the workflow pages' workbench until **Use this organizer in the workflow
pages** hands it over.
"""

import contextlib
import io
import json
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from NanoOrganizer import Organizer, structure
from NanoOrganizer.analysis import fit_peaks
from NanoOrganizer.analysis.peaks import BACKGROUNDS
from NanoOrganizer.demo import lab
from NanoOrganizer.viz import plots
from NanoOrganizer.web_app.components.security import (
    format_allowed_roots, is_path_allowed,
)
from NanoOrganizer.web_app.state import set_workbench

ORG = "nano_demo_org"

#: ``peak1_width`` is the Gaussian σ; FWHM = 2√(2 ln 2) σ.
FWHM_PER_SIGMA = 2.3548
#: Scherrer, as the generator uses it: FWHM = K·2π / D with D in Å.
SCHERRER_SLOPE = lab.SCHERRER_K * 2 * np.pi / 10.0
#: The UV-Vis band window notebook 12 batches with.
UVVIS_PARAMS = dict(x_range=(450.0, 700.0), n_peaks=1, background="linear")


def show_figure(figure) -> None:
    """Render a matplotlib figure and release it."""
    st.pyplot(figure, width="stretch")
    plt.close(figure)


def same_in_python(code: str) -> None:
    """The calls a tab just made, as code to paste into a notebook."""
    with st.expander("The same in Python", expanded=False):
        st.code(code.strip(), language="python")


def has_modality(org, modality: str) -> bool:
    return bool(org is not None and org.project.measurements(modality=modality))


def has_fits(org) -> bool:
    if org is None:
        return False
    columns = org.table(all_samples=True).columns
    return ("derived.uvvis_peak1_center" in columns
            and "derived.waxs1d_peak1_width" in columns)


st.title("🎓 Demo")
st.caption(
    "The three workflow notebooks — **10** simulate, **11** build, **12** use — "
    "as six tabs. Same package calls, same order, same files; each tab shows "
    "its code under *The same in Python*."
)

# ---------------------------------------------------------------------------
# Where the lab lives
# ---------------------------------------------------------------------------

root = st.text_input(
    "Lab folder", value=str(lab.lab_paths().root), key="nano_demo_root",
    help="Raw data is written here and the organizer saved as lab.json beside "
         "it. Defaults under demo_root() — ~/Repos/OrgDemo — or "
         "$NANOORGANIZER_DEMO_ROOT.")
paths = lab.lab_paths(root.strip() or None)

if not is_path_allowed(paths.root, allow_nonexistent=True):
    st.error(f"{paths.root} is outside the folders this session may write "
             f"to: {format_allowed_roots()}", icon="🚫")
    st.stop()

org = st.session_state.get(ORG)
if org is not None and org.path != paths.organizer:
    # A different lab folder was typed: the old organizer is not this one.
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
    st.caption("Mirrors `notebook/10_simulate_data` — a rig writing files. "
               "Nothing here involves an organizer yet.")
    st.markdown(
        "Three instruments, three folder trees, three naming conventions, "
        "none agreeing — and none laid out as `<Modality>Data/<SampleID>/`. "
        "The operator's metadata dict names **only the spectra**; the "
        "micrographs and the diffraction are linked by hand in tab 2, which "
        "is what actually happens. **The hidden control variable is the "
        "synthesis temperature**, and tab 6 checks what the pipeline recovers.")

    simulated = paths.synthesis_dict.exists()
    left, right = st.columns([3, 1])
    left.caption(f"Writes into `{paths.root}`. Re-running overwrites the same "
                 f"files with the same numbers; nothing else there is touched.")
    if right.button("Simulate again" if simulated else "Simulate the lab data",
                    type="secondary" if simulated else "primary",
                    width="stretch", key="nano_demo_simulate"):
        try:
            with st.spinner("Writing spectra, micrographs and diffraction…"):
                lab.simulate_lab(paths.root)
            simulated = True
            st.success(f"Wrote the lab under {paths.root}")
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    if simulated:
        counts = st.columns(4)
        counts[0].metric("Spectra", len(list(paths.spectra.glob("*.csv"))))
        counts[1].metric("Micrographs", len(list(paths.scope.glob("*/*.tif"))))
        counts[2].metric("Patterns", len(list(paths.xrd.glob("*.dat"))))
        counts[3].metric("Samples", len(lab.TEMPERATURE_C))

        tree_col, physics_col = st.columns([1, 1])
        with tree_col:
            st.markdown("**What landed on disk**")
            st.code(structure.tree(str(paths.raw), depth=2, limit=4),
                    language=None)
        with physics_col:
            st.markdown("**One hidden number per sample**")
            st.markdown(
                "- diameter = 6 + 0.16 · (T − 60) nm — `diameter_nm(T)`\n"
                "- plasmon band = 512 + 1.9 · d nm — `band_nm(d)`\n"
                "- WAXS line width ∝ 1/d — Scherrer")
            st.dataframe(pd.read_csv(paths.truth), hide_index=True,
                         width="stretch")

        st.markdown("**What the operator wrote down** — `S01`'s record; the "
                    "`uvvis_growth` block names files, so it becomes a "
                    "measurement on ingest")
        st.json(json.loads(paths.synthesis_dict.read_text())["S01"],
                expanded=1)

    same_in_python(f'''
from NanoOrganizer.demo.lab import simulate_lab

lab = simulate_lab("{paths.root}")    # spectra, micrographs, diffraction,
                                      # the metadata dict and the answer key

# notebook 10 runs the instruments one at a time, to look in between:
# from NanoOrganizer.demo.lab import (write_spectra, write_micrographs,
#     write_diffraction, synthesis_dict, write_synthesis_dict)
''')

# ---------------------------------------------------------------------------
# 2 · Build — notebook 11
# ---------------------------------------------------------------------------

with build:
    st.caption("Mirrors `notebook/11_build_organizer` — one JSON file that "
               "knows where everything is. The data never moves.")

    if not paths.synthesis_dict.exists():
        st.info("Nothing to organise yet — simulate the data first, in tab "
                "**1 · Simulate**.", icon="👈")
    else:
        st.markdown("**a · The organizer** — `Organizer(lab.json)` is empty "
                    "if the file is new, and everything is back if it is not.")
        if org is None:
            saved = paths.organizer.exists()
            if st.button("Reopen lab.json" if saved
                         else "Create Organizer(lab.json)",
                         type="primary", key="nano_demo_create"):
                try:
                    org = Organizer(paths.organizer, name="lab demo")
                    st.session_state[ORG] = org
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
            if saved:
                st.caption(f"`{paths.organizer.name}` already exists here — "
                           f"reopening it brings back its links, parameters "
                           f"and fits.")

    if org is not None:
        st.caption(f"`{org.path}` — {len(org.project)} samples, "
                   f"{len(org.project.measurements())} measurements")

        st.markdown("**b · Ingest what was written down** — the dict itself, "
                    "not a path to it. The keyword names the stage.")
        if st.button("Ingest the metadata dict", key="nano_demo_ingest",
                     type="primary" if not len(org.project) else "secondary"):
            try:
                synthesis = json.loads(paths.synthesis_dict.read_text())
                org.ingest(synthesis=synthesis)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        if len(org.project):
            wanted = ["synthesis.conditions.temperature_C", "synthesis.status",
                      "modalities", "n_measurements"]
            table = org.table(all_samples=True)
            st.dataframe(table[[c for c in wanted if c in table.columns]],
                         width="stretch")

        st.markdown("**c · Link what nobody wrote down** — one call per "
                    "measurement, by hand. A folder is listed now and "
                    "filtered by the technique's extensions, so the "
                    "`session.txt` beside the micrographs is left out.")
        linked = has_modality(org, "tem") or has_modality(org, "waxs1d")
        if st.button("Link micrographs and diffraction by hand",
                     key="nano_demo_link", disabled=not len(org.project),
                     type="primary" if len(org.project) and not linked
                     else "secondary"):
            try:
                for sample in org.project.sample_ids():
                    scope = paths.scope / sample
                    waxs = paths.xrd / f"{sample}_waxs.dat"
                    # A link to nothing is a mistake, not a feature: skip it
                    # and let the gap show in the catalog.
                    if scope.is_dir():
                        org.link(sample, "tem", str(scope),
                                 stage="characterization",
                                 instrument="LabScope", nm_per_pixel=0.5)
                    if waxs.exists():
                        org.link(sample, "waxs1d", str(waxs),
                                 stage="characterization", instrument="LabXRD")
                linked = True
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        if len(org.project):
            st.markdown("The catalog — sample × technique, files per cell")
            st.dataframe(org.catalog(counts=True), width="stretch")

        st.markdown("**d · Save** — one file: links, parameters, path aliases "
                    "and, later, derived values.")
        if st.button("Save lab.json", key="nano_demo_save",
                     disabled=not len(org.project)):
            try:
                written = org.save()
                st.success(f"Saved {written} "
                           f"({written.stat().st_size / 1024:.1f} kB)")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")
        if org.path.exists():
            with st.expander("Links table — the re-importable export",
                             expanded=False):
                st.dataframe(org.links_table(), hide_index=True,
                             width="stretch")

    if paths.synthesis_dict.exists() and (org is not None
                                          or paths.organizer.exists()):
        with st.expander("Start over", expanded=False):
            doomed = [p for p in (paths.organizer, paths.root / "results")
                      if p.exists()]
            st.caption("Removes only the organizer and the stored fits — the "
                       "simulated raw data stays. Would delete: "
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
                org = None
                st.success("Removed. Create the organizer again above.")

    same_in_python(f'''
import json
from NanoOrganizer import Organizer

org = Organizer("{paths.organizer}", name="lab demo")

Synthesis_dict = json.loads(open("{paths.synthesis_dict}").read())
org.ingest(synthesis=Synthesis_dict)          # the spectra come in with it

for sample in org.project.sample_ids():       # the rest, by hand
    scope = "{paths.scope}/" + sample
    waxs = "{paths.xrd}/" + sample + "_waxs.dat"
    org.link(sample, "tem", scope, stage="characterization",
             instrument="LabScope", nm_per_pixel=0.5)
    org.link(sample, "waxs1d", waxs, stage="characterization",
             instrument="LabXRD")

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
            "Query", value="`synthesis.conditions.temperature_C` >= 90",
            key="nano_demo_query",
            help="A pandas expression over org.table(); dotted names need "
                 "backticks.")
        try:
            st.write(org.ids(query) if query.strip() else org.ids())
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        st.divider()
        with_uvvis = [s for s in org.project.sample_ids()
                      if org.project.get_sample(s).get_measurements(
                          modality="uvvis")]
        if with_uvvis:
            sample = st.selectbox("Sample", with_uvvis, key="nano_demo_look_s")
            st.markdown("**`frames()`** — one row per file, with the time "
                        "its name admitted; `t=` selects on it by nearest "
                        "value")
            st.dataframe(org.frames(sample, "uvvis").head(6), hide_index=True,
                         width="stretch")

            st.markdown("**`data()`** — the numbers, no figure")
            try:
                x, Y, info = org.data(sample, "uvvis")
                lines = [f'x, Y, info = org.data("{sample}", "uvvis")'
                         f'   # x {x.shape}, Y {Y.shape}']
                _, Y_600, info_600 = org.data(sample, "uvvis", t=600)
                lines.append(f'org.data("{sample}", "uvvis", t=600)'
                             f'   # nearest frame: {info_600["labels"][0]}')
                if org.project.get_sample(sample).get_measurements(
                        modality="tem"):
                    frames = org.data(sample, "tem", lazy=True)
                    lines.append(f'frames = org.data("{sample}", "tem", '
                                 f'lazy=True)   # {len(frames)} files, none '
                                 f'read yet: {", ".join(frames.names)}')
                    image, meta = frames[1]
                    lines.append(f'image, meta = frames[1]'
                                 f'   # {image.shape}, '
                                 f'{meta.get("nm_per_pixel")} nm/px — one '
                                 f'file opened')
                st.code("\n".join(lines), language="python")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    same_in_python('''
from NanoOrganizer import Organizer

org = Organizer("lab.json")
org.describe()
print(org.tree(depth=2, limit=5))
org.catalog()
org.ids("`synthesis.conditions.temperature_C` >= 90")   # selection unchanged

org.frames("S01", "uvvis")                  # one row per file
x, Y, info = org.data("S01", "uvvis")       # Y: (n_frames, n_points)
x, Y, info = org.data("S01", "uvvis", t=600)
frames = org.data("S01", "tem", lazy=True)  # resolved, not read
image, meta = frames[1]                     # one file opened
''')

# ---------------------------------------------------------------------------
# 4 · Visualize — notebook 12, part C
# ---------------------------------------------------------------------------

with visualize:
    st.caption("Mirrors `notebook/12_use_organizer` part **C**. The figure "
               "follows what the data *is* — a series, a curve, an image — "
               "not which instrument made it.")
    if not ready:
        st.info("Build the organizer first — tab **2 · Build**.", icon="👈")
    else:
        left, middle, right = st.columns([2, 2, 1])
        sample = left.selectbox("Sample", org.project.sample_ids(),
                                key="nano_demo_vis_s")
        available = [m.modality for m in
                     org.project.get_sample(sample).measurements
                     if m.modality != "fit"]
        available = list(dict.fromkeys(available))
        if not available:
            st.info(f"{sample} has no data linked yet.", icon="📭")
        else:
            modality = middle.selectbox("Technique", available,
                                        key="nano_demo_vis_m")
            engine = right.radio("Engine", ["static", "interactive"],
                                 key="nano_demo_vis_engine")
            try:
                if engine == "interactive":
                    st.plotly_chart(org.plot(sample, modality,
                                             engine="interactive"),
                                    use_container_width=True)
                else:
                    figure, ax = plt.subplots(figsize=(8.0, 4.8))
                    org.plot(sample, modality, ax=ax)
                    show_figure(figure)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        with_waxs = [s for s in org.project.sample_ids()
                     if org.project.get_sample(s).get_measurements(
                         modality="waxs1d")]
        if with_waxs:
            st.markdown("**`overlay()`** — one curve per sample; an explicit "
                        "list disturbs no selection")
            chosen = st.multiselect("Samples to overlay", with_waxs,
                                    default=[s for s in ("S01", "S03", "S06")
                                             if s in with_waxs] or with_waxs[:3],
                                    key="nano_demo_overlay")
            if chosen:
                try:
                    figure, ax = plt.subplots(figsize=(8.0, 4.5))
                    org.overlay("waxs1d", sample_ids=chosen, ax=ax,
                                verbose=False)
                    show_figure(figure)
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    same_in_python('''
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 3, figsize=(16, 4))
org.plot("S01", "uvvis", ax=axes[0])     # coloured by acquisition time
org.plot("S01", "waxs1d", ax=axes[1])
org.plot("S01", "tem", ax=axes[2])       # on nanometre axes

fig, ax = plt.subplots()
org.overlay("waxs1d", sample_ids=["S01", "S03", "S06"], ax=ax)

org.plot("S01", "tem", engine="interactive").show()     # Plotly
''')

# ---------------------------------------------------------------------------
# 5 · Analyze — notebook 12, part D
# ---------------------------------------------------------------------------

params = None
with analyze:
    st.caption("Mirrors `notebook/12_use_organizer` part **D** — the kernel "
               "on arrays first, *then* the batch. Fitting and drawing are "
               "two separate calls.")
    with_waxs = ([s for s in org.project.sample_ids()
                  if org.project.get_sample(s).get_measurements(
                      modality="waxs1d")] if ready else [])
    if not with_waxs:
        st.info("Link the diffraction first — tab **2 · Build**, step c.",
                icon="👈")
    else:
        st.markdown("**The kernel** — `fit_peaks(x, y, …)` takes two arrays "
                    "and nothing else. Change a number, look again.")
        controls = st.columns([1, 2, 1, 1])
        sample = controls[0].selectbox("Sample", with_waxs,
                                       key="nano_demo_fit_s")
        x, Y, info = org.data(sample, "waxs1d")
        window = controls[1].slider(
            "Fit window (Å⁻¹)", float(np.floor(x.min() * 10) / 10),
            float(np.ceil(x.max() * 10) / 10), (2.3, 3.0), 0.05,
            key="nano_demo_fit_window")
        n_peaks = int(controls[2].number_input("Peaks", 1, 3, 1,
                                               key="nano_demo_fit_n"))
        background = controls[3].selectbox(
            "Background", BACKGROUNDS, index=BACKGROUNDS.index("linear"),
            key="nano_demo_fit_bg")
        params = dict(x_range=tuple(window), n_peaks=n_peaks,
                      background=background)

        fit = None
        try:
            fit = fit_peaks(x, Y[0], **params)        # the analysis
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        if fit is not None:
            plot_col, numbers_col = st.columns([3, 2])
            with plot_col:
                figure, ax = plt.subplots(figsize=(7.5, 5.2))
                plots.plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, ax=ax,
                               xlabel="q (Å$^{-1}$)", ylabel="intensity",
                               title=f"{sample} — R² = {fit.r2:.4f}")
                show_figure(figure)                    # the picture
            with numbers_col:
                st.metric("R²", f"{fit.r2:.4f}")
                st.dataframe(pd.DataFrame({
                    "value": fit.params,
                    "± 1σ": {k: fit.errors.get(k) for k in fit.params},
                }), width="stretch")
                st.caption("A window that reaches the next reflection drags "
                           "the centre and drops R² — the residual stops "
                           "being noise and starts having shape.")

        st.divider()
        st.markdown("**The batch** — happy with the parameters, spend them on "
                    "every sample. `link=True` also writes each fit's curves "
                    "beside lab.json and links them back, so tab 6 can redraw "
                    "them without refitting. The UV-Vis band is fitted too, "
                    f"with `{UVVIS_PARAMS}`.")
        if st.button("Batch these parameters over every sample",
                     type="primary", key="nano_demo_batch"):
            try:
                with st.spinner("Fitting…"):
                    waxs_table = org.batch("peak_fit", modality="waxs1d",
                                           link=True, verbose=False, **params)
                    uvvis_table = org.batch("peak_fit", modality="uvvis",
                                            link=True, verbose=False,
                                            **UVVIS_PARAMS)
                    org.save()
                ok = int(waxs_table["ok"].sum() + uvvis_table["ok"].sum())
                st.success(f"{ok}/{len(waxs_table) + len(uvvis_table)} fits "
                           f"succeeded; saved to {org.path.name}")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        stored = org.results()
        if not stored.empty:
            shown = [c for c in ("sample_id", "analysis", "modality", "ok",
                                 "peak1_center", "fit_r2") if c in stored]
            st.dataframe(stored[shown], hide_index=True, width="stretch")

    shown_params = params or dict(x_range=(2.3, 3.0), n_peaks=1,
                                  background="linear")
    same_in_python(f'''
import matplotlib.pyplot as plt
from NanoOrganizer.analysis import fit_peaks
from NanoOrganizer.viz.plots import plot_fit

x, Y, info = org.data("S01", "waxs1d")
params = {shown_params}

fit = fit_peaks(x, Y[0], **params)               # the analysis: arrays in
fit.params, fit.errors, fit.r2

fig, ax = plt.subplots()
plot_fit(fit.x, fit.y, fit.y_fit, fit.residual, ax=ax,   # the picture
         xlabel="q (1/Å)", title=f"S01 — R² = {{fit.r2:.4f}}")

org.batch("peak_fit", modality="waxs1d", link=True, **params)
org.batch("peak_fit", modality="uvvis", link=True, **{UVVIS_PARAMS})
org.results()
org.save()
''')

# ---------------------------------------------------------------------------
# 6 · Compare — notebook 12, parts E and F
# ---------------------------------------------------------------------------

with compare:
    st.caption("Mirrors `notebook/12_use_organizer` parts **E** (ids → table "
               "→ plot) and **F** (reload the stored fits, no refitting).")
    if not has_fits(org):
        st.info("Run the batch first — tab **5 · Analyze**. That is what puts "
                "fitted values into the table.", icon="👈")
    else:
        # E · the table — numbers first, drawn afterwards.
        ids = org.ids("`synthesis.status` == 'done'")
        truth = pd.read_csv(paths.truth).set_index("sample_id")
        table = org.table(sample_ids=ids)
        check = pd.DataFrame({
            "temperature_C": table["synthesis.conditions.temperature_C"],
            "fitted_band_nm": table["derived.uvvis_peak1_center"],
            "waxs_fwhm_invA": table["derived.waxs1d_peak1_width"]
                              * FWHM_PER_SIGMA,
        }).join(truth[["true_band_nm", "true_diameter_nm"]]).dropna()
        st.dataframe(check.round(4), width="stretch")

        if len(check) >= 2:
            inverse_d = 1.0 / check["true_diameter_nm"]
            slope, intercept = np.polyfit(inverse_d, check["waxs_fwhm_invA"], 1)
            worst = float((check["fitted_band_nm"]
                           - check["true_band_nm"]).abs().max())
            numbers = st.columns(3)
            numbers[0].metric("Band recovered within", f"{worst:.1f} nm")
            numbers[1].metric(
                f"Scherrer slope (expected {SCHERRER_SLOPE:.3f})",
                f"{slope:.3f}")
            numbers[2].metric("Intercept (expected ≈ 0)", f"{intercept:.5f}")

            figure, axes = plt.subplots(1, 2, figsize=(12.0, 4.2))
            axes[0].plot(check["true_band_nm"], check["fitted_band_nm"], "o",
                         ms=9, color=plots.CATEGORICAL[0])
            low = check["true_band_nm"].min() - 2
            high = check["true_band_nm"].max() + 2
            axes[0].plot([low, high], [low, high], "--", lw=1, color="0.5")
            plots.style(axes[0], "band the generator used (nm)",
                        "band the fit recovered (nm)",
                        "UV-Vis, against the answer key")
            axes[1].plot(inverse_d, check["waxs_fwhm_invA"], "o", ms=9,
                         color=plots.CATEGORICAL[0])
            line = np.linspace(0, float(inverse_d.max()) * 1.05, 20)
            axes[1].plot(line, slope * line + intercept, lw=1,
                         color=plots.STATUS["critical"],
                         label=f"fit, slope {slope:.3f}")
            plots.style(axes[1], "1 / true diameter (nm$^{-1}$)",
                        "fitted WAXS FWHM (Å$^{-1}$)",
                        "WAXS line width is Scherrer")
            axes[1].legend(frameon=False, fontsize=9)
            figure.tight_layout()
            show_figure(figure)

        compare_col, reload_col = st.columns(2)
        with compare_col:
            st.markdown("**`plot_compare`** — structure against property, "
                        "straight off the table")
            try:
                figure, ax = plt.subplots(figsize=(6.5, 4.6))
                plots.plot_compare(org.table(sample_ids=ids),
                                   "synthesis.conditions.temperature_C",
                                   "derived.uvvis_peak1_center", ax=ax)
                show_figure(figure)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

        # F · reload — off disk, nothing refitted.
        with reload_col:
            st.markdown("**Reload, and go round again** — a fresh "
                        "`Organizer` from the saved file; the curves come off "
                        "disk, nothing is refitted.")
            stored = org.results()
            fitted_samples = (sorted(stored["sample_id"].unique())
                              if not stored.empty else [])
            if fitted_samples:
                left, middle = st.columns(2)
                sample = left.selectbox(
                    "Sample", fitted_samples,
                    index=fitted_samples.index("S03")
                    if "S03" in fitted_samples else 0,
                    key="nano_demo_reload_s")
                modality = middle.selectbox("Fit of", ["waxs1d", "uvvis"],
                                            key="nano_demo_reload_m")
                if st.button("Reload from disk and redraw",
                             key="nano_demo_reload", width="stretch"):
                    try:
                        later = Organizer(paths.organizer)
                        result = later.result(sample, "peak_fit",
                                              modality=modality)  # no refit
                        figure, ax = plt.subplots(figsize=(6.5, 4.6))
                        plots.plot_peak_fit(result, ax=ax)         # drawn
                        show_figure(figure)
                    except Exception as exc:
                        st.error(f"{type(exc).__name__}: {exc}", icon="🚫")

    same_in_python('''
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from NanoOrganizer import Organizer
from NanoOrganizer.viz.plots import plot_compare, plot_peak_fit

ids = org.ids("`synthesis.status` == 'done'")
table = org.table(sample_ids=ids)
truth = pd.read_csv("Meta/truth.csv").set_index("sample_id")
check = pd.DataFrame({
    "temperature_C": table["synthesis.conditions.temperature_C"],
    "fitted_band_nm": table["derived.uvvis_peak1_center"],
    "waxs_fwhm_invA": table["derived.waxs1d_peak1_width"] * 2.3548,
}).join(truth[["true_band_nm", "true_diameter_nm"]]).dropna()

slope, intercept = np.polyfit(1 / check["true_diameter_nm"],
                              check["waxs_fwhm_invA"], 1)  # expect 0.565, 0

fig, ax = plt.subplots()
plot_compare(table, "synthesis.conditions.temperature_C",
             "derived.uvvis_peak1_center", ax=ax)

later = Organizer("lab.json")                      # F: reload, no refitting
result = later.result("S03", "peak_fit", modality="waxs1d")
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
        st.success("Done — open **🔎 Explore & Filter**, **📈 Visualize**, "
                   "**🧪 Analyze** or **📊 Compare** in the sidebar.",
                   icon="✅")
else:
    st.caption("Once the organizer is built, it can be handed to the workflow "
               "pages from here.")
