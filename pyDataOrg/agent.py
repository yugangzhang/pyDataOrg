#!/usr/bin/env python3
"""
The organizer's operations, described for an AI agent — or any other caller.

An agent that helps run a campaign needs to ask the same questions a person
asks in a notebook: what is in this project, which samples match, what does
this record say, what can be run on it, what came out. This module lists
those operations once, each with a JSON-schema description, so they can be

* called from Python — :func:`call` (``call(org, "list_samples", query=…)``);
* handed to a model as tools — :func:`tool_specs` in the Anthropic or
  OpenAI shape;
* served to any MCP client (Claude Code, Claude Desktop, …) —
  :func:`serve_mcp`, or ``dataorg mcp project.json`` from a shell.

Every result is plain JSON (NaN as ``null``, paths shown relative). Errors
come back as ``{"error": "..."}`` rather than exceptions, because a model
reads the error and tries again.

**Read-only unless allowed.** Operations that change the organizer or write
files (``writes=True``: keeping results, saving) are refused unless the
caller passes ``allow_writes=True`` — an agent should be granted write
access deliberately, not have it by default.

Project packages add their own operations with :func:`register_operation`.
"""

from __future__ import annotations

import contextlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from pyDataOrg.export import _plain, jsonable_records


@dataclass(frozen=True)
class Operation:
    """One thing a caller can ask of an open organizer."""

    name: str
    description: str
    func: Callable[..., Any]                  # func(org, **arguments)
    parameters: Mapping[str, Any] = field(default_factory=dict)  # properties
    required: tuple = ()
    writes: bool = False

    def schema(self) -> Dict[str, Any]:
        """The JSON schema of the arguments."""
        return {"type": "object", "properties": dict(self.parameters),
                "required": list(self.required)}


OPERATIONS: Dict[str, Operation] = {}


def register_operation(operation: Operation) -> Operation:
    OPERATIONS[operation.name] = operation
    return operation


def operation(name: str, description: str, *, parameters=None,
              required=(), writes: bool = False):
    """Decorator form of :func:`register_operation`."""
    def wrap(func):
        register_operation(Operation(name, description, func,
                                     dict(parameters or {}), tuple(required),
                                     writes))
        return func
    return wrap


# ---------------------------------------------------------------------------
# Argument shapes used more than once
# ---------------------------------------------------------------------------

_STR = {"type": "string"}
_INT = {"type": "integer"}
_IDS = {"type": "array", "items": {"type": "string"}}
_QUERY = {"type": "string", "description":
          "a pandas query over the sample table; dotted column names need "
          "backticks, e.g. \"`synthesis.conditions.temperature_C` > 90\""}
_SETTINGS = {"type": "object", "description":
             "the analysis' settings (see analysis_settings); omitted ones "
             "take their defaults"}


def _shown(path) -> str:
    from pyDataOrg.core.pathmap import display_path

    return display_path(path)


# ---------------------------------------------------------------------------
# Looking
# ---------------------------------------------------------------------------

@operation("describe_project",
           "What this organizer contains: samples, stages, techniques, "
           "analyses run, derived columns. Start here.")
def _describe(org):
    info = dict(org.overview())
    info["store"] = _shown(info["store"])
    info["sample_ids"] = info["sample_ids"][:200]
    return info


@operation("list_columns",
           "Column names of the sample table, optionally only those "
           "containing some text. The table is wide: search it.",
           parameters={"contains": _STR})
def _columns(org, contains: str = ""):
    return org.columns(contains)


@operation("list_samples",
           "Sample ids, optionally only those matching a query. Does not "
           "change the selection.",
           parameters={"query": _QUERY})
def _samples(org, query: str = ""):
    if query:
        return org.ids(query)
    return org.project.sample_ids()


@operation("sample_table",
           "Rows of the sample table — chosen columns (default: all) for "
           "chosen samples (default: all, or those matching a query).",
           parameters={"columns": _IDS, "sample_ids": _IDS, "query": _QUERY,
                       "limit": {"type": "integer", "default": 50}})
def _table(org, columns=(), sample_ids=(), query: str = "", limit: int = 50):
    ids = list(sample_ids) or (org.ids(query) if query else [])
    frame = org.table(all_samples=not ids, sample_ids=ids)
    if columns:
        missing = [c for c in columns if c not in frame]
        if missing:
            raise KeyError(f"no columns {', '.join(missing)}; "
                           f"find names with list_columns")
        frame = frame[["sample_id"] + [c for c in columns if c != "sample_id"]]
    return jsonable_records(frame.reset_index(drop=True), limit)


@operation("sample_record",
           "Everything recorded about one sample, optionally one stage "
           "(synthesis, characterization, testing …).",
           parameters={"sample_id": _STR, "stage": _STR},
           required=("sample_id",))
def _record(org, sample_id: str, stage: str = ""):
    return json.loads(json.dumps(org.metadata(sample_id, stage), default=str))


@operation("list_measurements",
           "The data linked to one sample: technique, stage, files, and "
           "whether they are readable on this machine.",
           parameters={"sample_id": _STR}, required=("sample_id",))
def _measurements(org, sample_id: str):
    sample = org.project.get_sample(sample_id)
    if sample is None:
        raise KeyError(f"unknown sample {sample_id!r}")
    rows = []
    for m in sample.measurements:
        paths = m.resolve(org.resolver)
        rows.append({"measurement_id": m.measurement_id,
                     "modality": m.modality, "stage": m.stage, "role": m.role,
                     "n_files": len(paths), "readable": bool(paths)})
    return rows


# ---------------------------------------------------------------------------
# Analysing
# ---------------------------------------------------------------------------

@operation("list_analyses",
           "Registered analyses — all, or those that can run on one sample — "
           "with what each does.",
           parameters={"sample_id": _STR})
def _analyses(org, sample_id: str = ""):
    from pyDataOrg import analysis as A

    keys = org.analyses(sample_id) if sample_id else \
        [a.key for a in A.list_analyses()]
    return [{"key": k, "label": A.get_analysis(k).label,
             "description": A.get_analysis(k).description,
             "runs_on_results_of": list(A.get_analysis(k).results_of)}
            for k in keys]


@operation("analysis_settings",
           "An analysis' settings and their defaults — the dict run_analysis "
           "takes.", parameters={"key": _STR}, required=("key",))
def _settings(org, key: str):
    from pyDataOrg import analysis as A

    return A.get_analysis(key).settings_for({})


@operation("run_analysis",
           "Run one analysis on one sample and return its values. Kept "
           "results with the same settings load instead of running. With "
           "keep=true the result is saved and linked (needs write access).",
           parameters={"key": _STR, "sample_id": _STR, "settings": _SETTINGS,
                       "modality": _STR, "keep": {"type": "boolean",
                                                  "default": False}},
           required=("key", "sample_id"))
def _run(org, key: str, sample_id: str, settings=None, modality: str = "",
         keep: bool = False):
    result = org.run(key, sample_id, settings=dict(settings or {}),
                     modality=modality, link=keep, verbose=False)
    return {"ok": result.ok, "message": result.message,
            "values": {k: _plain(v) for k, v in result.values.items()},
            "errors": {k: _plain(v) for k, v in result.errors.items()}}


@operation("batch_analysis",
           "Run one analysis over many samples (default: every sample it "
           "applies to); one row per sample with status ran/loaded/failed. "
           "With keep=true results are saved and linked (needs write access).",
           parameters={"key": _STR, "sample_ids": _IDS, "settings": _SETTINGS,
                       "keep": {"type": "boolean", "default": False}},
           required=("key",))
def _batch(org, key: str, sample_ids=(), settings=None, keep: bool = False):
    frame = org.batch(key, list(sample_ids) or org.project.sample_ids(),
                      settings=dict(settings or {}), link=keep, write=False,
                      verbose=False)
    keep_cols = [c for c in frame.columns if c not in ("measurement_id",)]
    return jsonable_records(frame[keep_cols])


@operation("kept_results",
           "Results kept as files (saved and linked), with their values — "
           "optionally one analysis only.",
           parameters={"analysis": _STR, "limit": {"type": "integer",
                                                   "default": 200}})
def _results(org, analysis: str = "", limit: int = 200):
    return jsonable_records(org.results(all_samples=True, analysis=analysis),
                            limit)


@operation("analysis_status",
           "For each kept analysis: samples with data, kept, and new (not "
           "analysed yet).")
def _status(org):
    return jsonable_records(org.status(org.kept_analyses()))


@operation("analyse_new",
           "Run every kept analysis on the samples that have no kept result "
           "yet, with the settings the others were kept with (needs write "
           "access).", writes=True)
def _analyse_new(org):
    done = org.analyse_new(org.kept_analyses())
    return {key: int(len(frame)) for key, frame in done.items()}


@operation("save", "Write the organizer to its file (needs write access).",
           writes=True)
def _save(org):
    return {"saved": _shown(org.save())}


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@operation("list_campaigns",
           "Registered campaigns — named tables of inputs, results and goals.")
def _campaigns(org):
    from pyDataOrg import campaign as C

    return [C.get_campaign(n).to_dict() for n in C.list_campaigns()]


@operation("campaign_table",
           "A campaign's table: one row per sample, short column names, kept "
           "results joined in.",
           parameters={"name": _STR, "limit": {"type": "integer",
                                               "default": 200}},
           required=("name",))
def _campaign_table(org, name: str, limit: int = 200):
    from pyDataOrg import campaign as C

    return jsonable_records(C.get_campaign(name).table(org), limit)


@operation("propose_next",
           "Fit a surrogate to a campaign and propose the next inputs to "
           "try, with predicted mean ± sd for each goal. Writes nothing.",
           parameters={"name": _STR, "goals": _IDS,
                       "n": {"type": "integer", "default": 4},
                       "seed": {"type": "integer", "default": 0},
                       "engine": {"type": "string", "default": "gp"}},
           required=("name",))
def _propose(org, name: str, goals=(), n: int = 4, seed: int = 0,
             engine: str = "gp"):
    from pyDataOrg import campaign as C
    from pyDataOrg import optimize

    spec = C.get_campaign(name)
    frame = spec.table(org)
    objectives = [spec.objective(g) for g in goals] or None
    plan = optimize.propose_for(spec, frame, objectives=objectives, n=n,
                                seed=seed, engine=engine)
    return {"proposals": jsonable_records(plan.suggestions),
            "trained_on": plan.samples, "notes": plan.notes,
            "engine": plan.engine_name}


# ---------------------------------------------------------------------------
# Calling
# ---------------------------------------------------------------------------

def list_operations(allow_writes: bool = True) -> List[str]:
    return [n for n, op in OPERATIONS.items() if allow_writes or not op.writes]


def call(org, name: str, arguments: Optional[Mapping[str, Any]] = None, /, *,
         allow_writes: bool = False, **kwargs) -> Any:
    """Run operation *name* on *org*; returns plain JSON, or
    ``{"error": ...}``. Arguments come as a dict (or JSON text) and/or
    keywords."""
    if isinstance(arguments, str):
        arguments = json.loads(arguments or "{}")
    arguments = {**dict(arguments or {}), **kwargs}
    op = OPERATIONS.get(name)
    if op is None:
        return {"error": f"no operation {name!r}; known: "
                         f"{', '.join(OPERATIONS)}"}
    keep = bool(arguments.get("keep"))
    if (op.writes or keep) and not allow_writes:
        return {"error": f"{name}{' with keep' if keep else ''} changes the "
                         f"organizer or writes files, and write access was "
                         f"not granted"}
    unknown = sorted(set(arguments) - set(op.parameters))
    if unknown:
        return {"error": f"{name} takes no {', '.join(unknown)}; it takes "
                         f"{', '.join(op.parameters) or 'nothing'}"}
    missing = [r for r in op.required if r not in arguments]
    if missing:
        return {"error": f"{name} needs {', '.join(missing)}"}
    try:
        # Nothing a tool does may print to stdout: under MCP that is the wire.
        with contextlib.redirect_stdout(sys.stderr):
            return op.func(org, **arguments)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def tool_specs(style: str = "anthropic", *, allow_writes: bool = False
               ) -> List[Dict[str, Any]]:
    """Every operation as a model tool definition.

    ``"anthropic"``: ``{name, description, input_schema}``;
    ``"openai"``: ``{type: "function", function: {name, description,
    parameters}}``; ``"mcp"``: ``{name, description, inputSchema}``.
    Writing operations are left out unless *allow_writes*.
    """
    specs = []
    for name in list_operations(allow_writes):
        op = OPERATIONS[name]
        if style == "anthropic":
            specs.append({"name": name, "description": op.description,
                          "input_schema": op.schema()})
        elif style == "openai":
            specs.append({"type": "function", "function": {
                "name": name, "description": op.description,
                "parameters": op.schema()}})
        elif style == "mcp":
            specs.append({"name": name, "description": op.description,
                          "inputSchema": op.schema()})
        else:
            raise ValueError("style is 'anthropic', 'openai' or 'mcp'")
    return specs


# ---------------------------------------------------------------------------
# MCP over stdio — no dependency beyond the standard library
# ---------------------------------------------------------------------------

def handle_mcp(org, message: Mapping[str, Any], *,
               allow_writes: bool = False) -> Optional[Dict[str, Any]]:
    """Answer one MCP (JSON-RPC 2.0) message; ``None`` for a notification.

    Tools only: ``initialize``, ``ping``, ``tools/list``, ``tools/call``.
    """
    from pyDataOrg import __version__

    method = message.get("method", "")
    ident = message.get("id")
    if ident is None:                         # a notification: no reply
        return None

    def reply(result):
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    if method == "initialize":
        version = (message.get("params") or {}).get("protocolVersion",
                                                    "2025-06-18")
        return reply({"protocolVersion": version,
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "pyDataOrg",
                                     "version": __version__}})
    if method == "ping":
        return reply({})
    if method == "tools/list":
        return reply({"tools": tool_specs("mcp", allow_writes=allow_writes)})
    if method == "tools/call":
        params = message.get("params") or {}
        out = call(org, params.get("name", ""), params.get("arguments") or {},
                   allow_writes=allow_writes)
        failed = isinstance(out, dict) and set(out) == {"error"}
        return reply({"content": [{"type": "text",
                                   "text": json.dumps(out, default=str,
                                                      indent=1)}],
                      "isError": failed})
    return {"jsonrpc": "2.0", "id": ident,
            "error": {"code": -32601, "message": f"no method {method!r}"}}


def serve_mcp(org, *, allow_writes: bool = False, stdin=None,
              stdout=None) -> None:
    """Serve *org* to an MCP client over stdio until the input closes.

    Register it with a client as a command, e.g.::

        claude mcp add dataorg -- dataorg mcp path/to/project.json
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            answer = {"jsonrpc": "2.0", "id": None,
                      "error": {"code": -32700, "message": "parse error"}}
        else:
            answer = handle_mcp(org, message, allow_writes=allow_writes)
        if answer is not None:
            stdout.write(json.dumps(answer, default=str) + "\n")
            stdout.flush()


__all__ = ["Operation", "OPERATIONS", "register_operation", "operation",
           "list_operations", "call", "tool_specs", "handle_mcp", "serve_mcp"]
