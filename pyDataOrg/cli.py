#!/usr/bin/env python3
"""
dataorg — one command for everything outside a notebook.

    dataorg gui [PORT] [PASSWORD] [--app NAME] [--local]   the web app
    dataorg adduser USERS_FILE NAME [--admin] [--root P]   a multi-user account
    dataorg demo [--campaign | --quick] [ROOT]             generate example data
    dataorg tree ADDRESS [--depth N]                       a folder, file or record
    dataorg plugins                                        installed project packages
    dataorg ops [NAME] [--json ARGS] [--store FILE]        the agent operations
    dataorg mcp STORE [--allow-writes]                     serve an organizer over MCP
    dataorg features STORE OUT [--campaign NAME]           a samples × features table
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional


def _open(store: str, server: str = ""):
    from pyDataOrg import Organizer, plugins

    plugins.load_plugins()
    return Organizer(store, server=server or None)


def _tree(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="dataorg tree",
                                     description="Print the structure of a "
                                     "folder, a data file, or a record.")
    parser.add_argument("address", help="a path, or path::inside/path")
    parser.add_argument("--depth", type=int, default=2)
    args = parser.parse_args(argv)
    from pyDataOrg.structure import tree

    print(tree(args.address, depth=args.depth))
    return 0


def _plugins(argv: List[str]) -> int:
    argparse.ArgumentParser(prog="dataorg plugins",
                            description="List installed plugins.").parse_args(argv)
    from pyDataOrg import plugins

    print(plugins.describe())
    return 0


def _ops(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dataorg ops",
        description="List the agent operations, show one's schema, or call "
                    "one on an organizer.")
    parser.add_argument("name", nargs="?", default="")
    parser.add_argument("--store", default="",
                        help="the organizer file to call the operation on")
    parser.add_argument("--json", default="{}", help="arguments, as JSON")
    parser.add_argument("--server", default="")
    parser.add_argument("--allow-writes", action="store_true")
    args = parser.parse_args(argv)
    from pyDataOrg import agent

    if not args.name:
        for name in agent.list_operations():
            op = agent.OPERATIONS[name]
            mark = " (writes)" if op.writes else ""
            print(f"{name}{mark}\n    {op.description}")
        return 0
    if not args.store:
        op = agent.OPERATIONS.get(args.name)
        if op is None:
            print(f"no operation {args.name!r}", file=sys.stderr)
            return 2
        print(json.dumps({"name": op.name, "description": op.description,
                          "input_schema": op.schema(), "writes": op.writes},
                         indent=1))
        return 0
    org = _open(args.store, args.server)
    out = agent.call(org, args.name, args.json, allow_writes=args.allow_writes)
    print(json.dumps(out, indent=1, default=str))
    return 1 if isinstance(out, dict) and set(out) == {"error"} else 0


def _mcp(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dataorg mcp",
        description="Serve an organizer to an MCP client over stdio.")
    parser.add_argument("store", help="the organizer file")
    parser.add_argument("--server", default="",
                        help="which machine this is (pyDataOrg.servers)")
    parser.add_argument("--allow-writes", action="store_true",
                        help="let the client keep results and save")
    args = parser.parse_args(argv)
    from pyDataOrg import agent

    agent.serve_mcp(_open(args.store, args.server),
                    allow_writes=args.allow_writes)
    return 0


def _features(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dataorg features",
        description="Write the numeric samples × features table of an "
                    "organizer (.csv, .parquet or .json).")
    parser.add_argument("store")
    parser.add_argument("out")
    parser.add_argument("--campaign", default="")
    parser.add_argument("--min-coverage", type=float, default=0.0)
    parser.add_argument("--server", default="")
    args = parser.parse_args(argv)
    from pyDataOrg.core.pathmap import display_path
    from pyDataOrg.export import feature_table, write_table

    org = _open(args.store, args.server)
    frame = feature_table(org, campaign=args.campaign or None,
                          min_coverage=args.min_coverage)
    path = write_table(frame, args.out)
    print(f"{frame.shape[0]} samples × {frame.shape[1]} features → "
          f"{display_path(path)}")
    return 0


COMMANDS = {
    "tree": _tree, "plugins": _plugins, "ops": _ops, "mcp": _mcp,
    "features": _features,
}


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    command, rest = argv[0], argv[1:]
    if command == "gui":
        from pyDataOrg.web_app.app_cli import main_secure

        return main_secure(rest) or 0
    if command == "adduser":
        from pyDataOrg.web_app.app_cli import main_adduser

        return main_adduser(rest) or 0
    if command == "demo":
        from pyDataOrg.demo.__main__ import main as demo_main

        return demo_main(rest)
    if command in COMMANDS:
        return COMMANDS[command](rest)
    print(f"dataorg: unknown command {command!r}\n\n{__doc__.strip()}",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
