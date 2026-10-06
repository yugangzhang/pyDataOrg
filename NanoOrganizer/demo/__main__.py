#!/usr/bin/env python3
"""
Build a demo project from the command line.

    python -m NanoOrganizer.demo ~/Repos/OrgDemo/Showcase   # the full showcase
    python -m NanoOrganizer.demo ~/Repos/OrgDemo/Quick --quick   # the small one
    python -m NanoOrganizer.demo ~/Repos/OrgDemo/Showcase --no-images

Then point the web app or a notebook at the directory it prints.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m NanoOrganizer.demo",
        description="Generate an example project to explore.")
    parser.add_argument("root", type=Path,
                        help="where to write it (created if missing)")
    parser.add_argument("--quick", action="store_true",
                        help="the small two-technique demo instead of the "
                             "fifteen-technique showcase")
    parser.add_argument("--no-images", action="store_true",
                        help="skip micrographs and tomography")
    parser.add_argument("--seed", type=int, default=None,
                        help="random seed (default: the generator's own)")
    args = parser.parse_args(argv)

    from NanoOrganizer.demo import build_demo_project, build_showcase_project

    options = {"with_images": not args.no_images}
    if args.seed is not None:
        options["seed"] = args.seed

    if args.quick:
        root = build_demo_project(args.root, **options)
    else:
        root = build_showcase_project(
            args.root, with_tomography=not args.no_images, **options)

    from NanoOrganizer import open_project

    workbench = open_project(root)
    print(workbench.summary())
    print(f"\nProject written to {root}")
    print("Open it with:  viz          (then Project → Open → paste the path)")
    print("           or:  open_project(r'%s')" % root)
    return 0


if __name__ == "__main__":       # pragma: no cover - console entry point
    raise SystemExit(main())
