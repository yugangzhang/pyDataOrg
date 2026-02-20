# Release Policy (Viz Base / Viz Adv)

This document defines how to manage:

1. version numbers
2. git tags
3. branch synchronization between `viz-base` and `viz-adv`

## 1. Version Source Of Truth

- Canonical package version in code:
  - `NanoOrganizer/version.py`
- Human-readable release marker:
  - `VERSION`

For each release, both files must match.

Version scheme:

- `viz-base`: standard semver `MAJOR.MINOR.PATCH` (example: `1.1.0`)
- `viz-adv`: semver plus local suffix `+adv.N` (example: `1.1.0+adv.1`)

Notes:

- Base/public releases should avoid `+local` suffixes.
- Adv/private releases should include `+adv.N` to make branch intent explicit.

## 2. Git Tag Rules

Tag format by branch:

- `viz-base` releases:
  - `viz-vMAJOR.MINOR.PATCH`
  - example: `viz-v1.1.0`
- `viz-adv` releases:
  - `viz-adv-vMAJOR.MINOR.PATCH+adv.N`
  - example: `viz-adv-v1.1.0+adv.1`

Tag commands:

```bash
# on viz-base
git tag -a viz-v1.1.0 -m "Viz base 1.1.0"
git push upstream viz-v1.1.0

# on viz-adv
git tag -a viz-adv-v1.1.0+adv.1 -m "Viz advanced 1.1.0+adv.1"
git push origin viz-adv-v1.1.0+adv.1
```

## 3. Branch Sync Rules

Direction of shared-code flow:

- `viz-base` -> `viz-adv` (allowed, expected)
- `viz-adv` -> `viz-base` (only for generic fixes that do not reintroduce adv-only modules)

Recommended sync cycle:

1. land stable/shared changes in `viz-base`
2. merge or cherry-pick them into `viz-adv`
3. keep adv-only modules isolated to adv branch/package surface

Hard boundaries for `viz-base`:

- no fitting workbench page
- no fitting adapters/engine registry internals
- no private advanced modality workflows

## 4. Pre-Release Checklist

Run before tagging:

```bash
python scripts/release/check_release_state.py --track base --require-clean
pytest -q
```

For adv:

```bash
python scripts/release/check_release_state.py --track adv --require-clean
pytest -q
```

Then create tag and push.

## 5. Push Targets

- `viz-base` branch and tags -> `upstream` (public repo)
- `viz-adv` branch and tags -> `origin` (private repo)

