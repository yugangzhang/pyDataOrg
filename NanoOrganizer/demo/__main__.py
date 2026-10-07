#!/usr/bin/env python3
"""
Generate example data from the command line.

    python -m NanoOrganizer.demo --campaign     # the data for notebooks 10-12
    python -m NanoOrganizer.demo                # the same campaign, as a project
    python -m NanoOrganizer.demo --quick        # the small two-technique project
    python -m NanoOrganizer.demo ~/elsewhere/Showcase --no-images

Without a path, everything goes under ``demo_root()`` — ``~/Repos/OrgDemo`` by
default, ``$NANOORGANIZER_DEMO_ROOT`` to move it.

``--campaign`` writes the Cu–Au showcase as **raw data only** — the files and
the four metadata dicts, plus the answer key — under ``CuAu/``, because
building the organizer from it is the part worth doing yourself (notebook 11,
or the web app's Demo page). Without it the same campaign is written to
``Showcase/`` and opened as a project.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m NanoOrganizer.demo",
        description="Generate example data to explore.")
    parser.add_argument("root", type=Path, nargs="?", default=None,
                        help="where to write it (default: under demo_root())")
    kind = parser.add_mutually_exclusive_group()
    kind.add_argument("--campaign", action="store_true",
                      help="the Cu-Au campaign as raw data for notebooks "
                           "10-12 and the Demo page: <root>/Campaign plus "
                           "<root>/truth.csv, no organizer")
    kind.add_argument("--quick", action="store_true",
                      help="the small two-technique demo project instead of "
                           "the fifteen-technique showcase")
    parser.add_argument("--no-images", action="store_true",
                        help="skip micrographs and tomography (projects only)")
    parser.add_argument("--seed", type=int, default=None,
                        help="random seed (default: the generator's own)")
    args = parser.parse_args(argv)

    from NanoOrganizer.demo import demo_root

    if args.campaign:
        from NanoOrganizer.demo import build_showcase_project, showcase_truth

        root = (args.root or demo_root("CuAu")).expanduser()
        options = {"with_images": not args.no_images,
                   "with_tomography": not args.no_images}
        if args.seed is not None:
            options["seed"] = args.seed
        campaign = build_showcase_project(root / "Campaign", **options)
        showcase_truth().to_csv(root / "truth.csv", index=False)
        print(f"Campaign data written to {campaign}")
        print(f"Answer key written to    {root / 'truth.csv'}")
        print("Next: notebook/11_build_organizer, or the web app's Demo page.")
        return 0

    from NanoOrganizer.demo import build_demo_project, build_showcase_project

    options = {"with_images": not args.no_images}
    if args.seed is not None:
        options["seed"] = args.seed

    if args.quick:
        root = build_demo_project(args.root or demo_root("Quick"), **options)
    else:
        root = build_showcase_project(
            args.root or demo_root("Showcase"),
            with_tomography=not args.no_images, **options)

    from NanoOrganizer import open_project

    workbench = open_project(root)
    print(workbench.summary())
    print(f"\nProject written to {root}")
    print("Open it with:  viz          (then Project → Open → paste the path)")
    print("           or:  open_project(r'%s')" % root)
    return 0


if __name__ == "__main__":       # pragma: no cover - console entry point
    raise SystemExit(main())
