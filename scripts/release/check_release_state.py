#!/usr/bin/env python3
"""Validate version/tag/branch release state for viz-base or viz-adv."""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def read_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_code_version(repo_root: Path) -> str:
    path = repo_root / "NanoOrganizer" / "version.py"
    text = read_file_text(path)
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not parse __version__ from NanoOrganizer/version.py")
    return match.group(1)


def read_version_file(repo_root: Path) -> str:
    return read_file_text(repo_root / "VERSION").strip()


def git_output(args, repo_root: Path) -> str:
    return subprocess.check_output(["git"] + args, cwd=repo_root, text=True).strip()


def ensure_clean_worktree(repo_root: Path) -> None:
    status = git_output(["status", "--porcelain"], repo_root)
    if status:
        raise RuntimeError("Working tree is not clean. Commit/stash changes before release.")


def expected_tag(track: str, version: str) -> str:
    if track == "base":
        return f"viz-v{version}"
    return f"viz-adv-v{version}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check NanoOrganizer release state.")
    parser.add_argument("--track", choices=["base", "adv"], required=True)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    branch = git_output(["branch", "--show-current"], repo_root)
    code_version = read_code_version(repo_root)
    file_version = read_version_file(repo_root)

    if code_version != file_version:
        raise RuntimeError(
            f"Version mismatch: NanoOrganizer/version.py={code_version} vs VERSION={file_version}"
        )

    if args.track == "base":
        if "+adv." in code_version:
            raise RuntimeError(
                "Base track version must not contain '+adv.'. "
                f"Current version: {code_version}"
            )
        if branch != "viz-base":
            print(
                f"Warning: track=base but current branch is '{branch}' (expected 'viz-base').",
                file=sys.stderr,
            )
    else:
        if "+adv." not in code_version:
            raise RuntimeError(
                "Advanced track version must contain '+adv.N'. "
                f"Current version: {code_version}"
            )
        if branch != "viz-adv":
            print(
                f"Warning: track=adv but current branch is '{branch}' (expected 'viz-adv').",
                file=sys.stderr,
            )

    if args.require_clean:
        ensure_clean_worktree(repo_root)

    print(f"track={args.track}")
    print(f"branch={branch}")
    print(f"version={code_version}")
    print(f"suggested_tag={expected_tag(args.track, code_version)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
