# NanoOrganizer Viz (Base / Public Track)

NanoOrganizer Viz is the **public base visualization/data-management package**.
It focuses on secure data browsing, plotting, and project organization.

Advanced analysis modules (fitting, XPCS, XANES, XAFS, etc.) are developed in the private `viz-adv` branch/package.

## Branch Model

- `viz-base` branch: public-safe base stack (this branch)
- `viz-adv` branch: private advanced extensions

## Install

```bash
pip install -e . --no-build-isolation
```

## Launch

Secure launcher:

```bash
viz [port] [password]
```

Example:

```bash
viz 5647 mypass
```

This command provides:

- password gate before app usage
- per-user folder restrictions (launcher-defined allowed roots)
- custom port per user

## Included Web Pages (Viz Base)

1. CSV Plotter
2. Image Viewer
3. Multi Axes
4. 3D Plotter
5. Data Viewer
6. Data Manager
7. Test Data Generator
8. Universal Plotter

## Not Included In Base

The following are intentionally excluded from `viz-base`:

- 1D Fitting Workbench page
- fitting adapters/engine registry internals
- fitting export tests and related private advanced workflows

Use `viz-adv` branch/package for those capabilities.

## Legacy Commands

These commands are still available:

- `nanoorganizer`
- `nanoorganizer_user`
- `nanoorganizer-viz`
- `nanoorganizer-csv`
- `nanoorganizer-csv-enhanced`
- `nanoorganizer-manage`
- `nanoorganizer-3d`
- `nanoorganizer-img`
- `nanoorganizer-multi`
- `nanoorganizer-hub`

## Push Workflow

Push base/public branch:

```bash
git push -u upstream viz-base:main
```

Push private advanced branch (`viz-adv`):

```bash
git push -u origin viz-adv
```

## Version And Tagging

Release governance lives in:

- `docs/RELEASE_POLICY.md`

Quick checks:

```bash
python scripts/release/check_release_state.py --track base --require-clean
```

## License

MIT
