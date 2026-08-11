# JupyterLab scattering viewers

These notebooks are the Python/Jupyter twin of the scattering-data GUI:

- `01_giwaxs_qimage_diagnostic.ipynb` focuses on q-image geometry, masks,
  robust color limits, q-space cropping, and line cuts.
- `02_scattering_products_explorer.ipynb` pairs `qc`, `q_image`, `qphi`, and
  `cir_avg` products for one frame and compares several frame indices.

Start JupyterLab from the repository root:

```bash
jupyter lab
```

Then edit `DATA_ROOT` near the top of either notebook. For the current
off-beamline example it is:

```text
/home/user/Facility_Link/beamline_a_remote/2026-2/pass-000000/projects/microbeam_Kim/Results/giwaxs
```

For another computer, replace that value with the local `giwaxs`, `gisaxs`,
or equivalent reduction folder. The notebooks do not depend on the GUI
session or its access mode; the user must already have filesystem access to
the selected path.

The helper implementation is
`NanoOrganizer/viz/scattering_notebook.py`, and can also be used from an
ordinary Python script. It treats rows of `qimg` as qz and columns as qx,
uses `origin="lower"`, hides non-positive remesh pixels, and converts the
SMI `qimg_mask=True` valid-data convention into a standard invalid-pixel mask.
This last detail is important for the current dataset: interpreting that mask
as a no-data mask makes the q-image appear blank.

Optional dependencies for the notebooks are already part of the package's
normal scientific stack; QC image display additionally uses Pillow. If
needed:

```bash
python -m pip install -e '.[image]'
```
