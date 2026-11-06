#!/usr/bin/env python3
"""
Ask the records: a question in plain words, answered by an AI model from an
organizer's records — what one sample is, how it was made and measured,
what has been done, what is missing.

pyDataOrg holds no model. It uses the command-line AI tools configured on
the machine it runs on, for the user who runs it (:func:`backends`):

==========  ==============================================================
``codex``   the user's Codex configuration (``$CODEX_HOME/config.toml``):
            its model and provider
``claude``  Claude Code, all tools off
``gemini``  Gemini CLI, read-only (plan) mode
``ollama``  one backend per local model (``ollama list``), if its server runs
==========  ==============================================================

Which models a user is offered is theirs to say, outside any repository, in
``~/.config/pyDataOrg/ask.json`` (or the file ``PYDATAORG_ASK_CONFIG``
names; :func:`user_config`)::

    {"models": [{"tool": "codex", "model": "<a model>"},
                {"tool": "claude", "model": "<another>", "note": "fast"},
                {"tool": "command", "title": "llm", "argv": ["llm", "-m", "x"]}],
     "env": {"<VARIABLE THE TOOL READS>": "$<VARIABLE IT IS IN>"}}

The models listed come first, the first the default, in place of that
tool's own default; a ``command`` is any program that reads the prompt on
stdin and writes the answer to stdout. ``env`` is passed to the tools,
``$NAME`` taken from the environment (a key is named, never written).

The records go to the model as text (:func:`organizer_context`): the
organizer's summary, what the caller adds about its project, one line per
sample, and the full records and kept results of the samples the question
names. The model is told to answer from them alone (:func:`prompt`) and runs
in an empty temporary folder. Nothing is written to the records.

A model bills the account of whoever runs the GUI, so asking is on for a
local GUI and off on a shared, password-protected one unless its owner
turns it on (``PYDATAORG_ASK=1``; :func:`enabled`).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

ASK_ENV = "PYDATAORG_ASK"
DEFAULT_ENV = "PYDATAORG_AI_DEFAULT"
MODEL_ENV = "PYDATAORG_AI_MODEL"
CONFIG_ENV = "PYDATAORG_ASK_CONFIG"
#: The user's own list of models (see the module's docstring).
USER_CONFIG = "~/.config/pyDataOrg/ask.json"
#: A GUI started with any of these is shared (see
#: :mod:`pyDataOrg.web_app.components.security`).
PASSWORD_ENV = "PYDATAORG_PASSWORD_HASH"
SECURE_ENV = "PYDATAORG_SECURE_MODE"
USERS_ENV = "PYDATAORG_USERS_FILE"
#: Samples whose full records go with a question, at most.
MAX_NAMED = 10
#: Characters of context the model is given, at most (the full records of
#: named samples are cut first).
MAX_CONTEXT = 120_000
#: Columns of the sample table left out of the one-line-per-sample list:
#: where files are, not what was found.
SKIP = ("path", "glob", "file", "dir", "manifest", "snapshot", "sha1")

ON = ("1", "true", "yes", "on")
OFF = ("0", "false", "no", "off")


# ---------------------------------------------------------------------------
# The models on this machine
# ---------------------------------------------------------------------------

@dataclass
class Backend:
    """One way of asking: a command line that reads the prompt on stdin.
    ``{out}`` in *argv* becomes a file the tool writes its answer to (when
    *output* is ``"file"``); otherwise the answer is its stdout."""

    key: str
    title: str
    argv: Tuple[str, ...]
    model: str = ""
    available: bool = True
    note: str = ""
    output: str = "stdout"                     # "stdout" | "file"
    env: Dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """``codex · <model> (<provider>)``."""
        model = f" · {self.model}" if self.model else ""
        note = f" ({self.note})" if self.note else ""
        return f"{self.title}{model}{note}"


def _top_level(path: Path) -> Dict[str, str]:
    """The top-level ``key = "value"`` pairs of a TOML file (before its
    first table), without needing a TOML reader."""
    out = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        if line.strip().startswith("["):
            break
        match = re.match(r'^\s*([A-Za-z0-9_.-]+)\s*=\s*"([^"]*)"', line)
        if match:
            out[match.group(1)] = match.group(2)
    return out


def codex_config() -> Dict[str, str]:
    """The user's Codex defaults: ``model`` and ``model_provider``."""
    home = Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser()
    return _top_level(home / "config.toml")


def user_config() -> Dict:
    """The user's own models and environment for asking (``ask.json``,
    outside the repository): ``{"models": [...], "env": {...}}``, empty when
    there is none or it cannot be read."""
    path = Path(os.environ.get(CONFIG_ENV) or USER_CONFIG).expanduser()
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def _env(config: Mapping) -> Dict[str, str]:
    """``env`` of the user's config, ``$NAME`` taken from the environment;
    a variable that is not set is left out."""
    out = {}
    for name, value in (config.get("env") or {}).items():
        value = os.path.expandvars(str(value))
        if value and "$" not in value:
            out[str(name)] = value
    return out


def _codex(model: str = "", note: str = "") -> Backend:
    config = codex_config()
    model = model or os.environ.get(MODEL_ENV, "")
    argv = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral",
            "--color", "never", "-c", 'model_reasoning_effort="low"', "-o", "{out}"]
    if model:
        argv += ["-c", f'model="{model}"']
    provider = config.get("model_provider", "")
    return Backend(f"codex:{model}" if model else "codex", "codex", tuple(argv + ["-"]),
                   model=model or config.get("model", ""),
                   available=shutil.which("codex") is not None,
                   note=", ".join(n for n in (provider, note) if n), output="file")


def _claude(model: str = "", note: str = "") -> Backend:
    argv = ["claude", "-p", "--tools", "", "--output-format", "text",
            "--no-session-persistence"]
    if model:
        argv += ["--model", model]
    return Backend(f"claude:{model}" if model else "claude", "claude", tuple(argv),
                   model=model or os.environ.get("ANTHROPIC_MODEL", ""), note=note,
                   available=shutil.which("claude") is not None)


def _gemini(model: str = "", note: str = "") -> Backend:
    settings = Path("~/.gemini/settings.json").expanduser()
    found_model = ""
    try:
        found = json.loads(settings.read_text(encoding="utf-8")).get("model", "")
        found_model = found.get("name", "") if isinstance(found, dict) else str(found)
    except (OSError, ValueError, AttributeError):
        pass
    argv = ["gemini", "-p", "Answer the question above, as instructed.",
            "--approval-mode", "plan", "-o", "text"]
    if model:
        argv += ["-m", model]
    return Backend(f"gemini:{model}" if model else "gemini", "gemini", tuple(argv),
                   model=model or found_model, note=note,
                   available=shutil.which("gemini") is not None)


_TOOLS = {"codex": _codex, "claude": _claude, "gemini": _gemini}


def _command(entry: Mapping) -> Optional[Backend]:
    """A ``{"tool": "command", "argv": [...]}`` entry: any program that
    reads the prompt on stdin and answers on stdout."""
    argv = [str(a) for a in entry.get("argv") or []]
    if not argv:
        return None
    title = str(entry.get("title") or Path(argv[0]).name)
    return Backend(f"command:{title}", title, tuple(argv),
                   model=str(entry.get("model", "")), note=str(entry.get("note", "")),
                   available=shutil.which(argv[0]) is not None)


def _configured(config: Mapping) -> List[Backend]:
    """The models the user listed, as backends."""
    out = []
    for entry in config.get("models") or []:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("tool") == "command":
            found = _command(entry)
            if found is not None:
                out.append(found)
        elif entry.get("tool") in _TOOLS:
            out.append(_TOOLS[entry["tool"]](str(entry.get("model", "")),
                                             str(entry.get("note", ""))))
    return out


def _ollama() -> List[Backend]:
    if shutil.which("ollama") is None:
        return []
    try:
        listed = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.SubprocessError):
        return []
    if listed.returncode != 0:
        return []
    names = [line.split()[0] for line in listed.stdout.splitlines()[1:] if line.strip()]
    return [Backend(f"ollama:{name}", "ollama", ("ollama", "run", name), model=name,
                    note="local") for name in names]


def backends(*, include_missing: bool = False) -> List[Backend]:
    """The AI tools configured here, the default first: the models the user
    listed (:func:`user_config`), then codex, claude, gemini — each tool's
    own default unless the user listed models of it — and the local ollama
    models; or first the one named by ``PYDATAORG_AI_DEFAULT``. Tools not
    installed are left out unless *include_missing*."""
    config = user_config()
    listed = _configured(config)
    own = {b.title for b in listed}
    found = listed + [make() for tool, make in _TOOLS.items() if tool not in own] + _ollama()
    env = _env(config)
    for b in found:
        b.env = {**env, **b.env}
    if not include_missing:
        found = [b for b in found if b.available]
    first = os.environ.get(DEFAULT_ENV, "")
    if first:
        found.sort(key=lambda b: first not in (b.key, b.title, b.model))
    return found


def enabled() -> bool:
    """Whether this GUI may ask: ``PYDATAORG_ASK`` on or off; unset, only a
    GUI without a password (a local one) asks — on a shared server the model
    would bill its owner's account."""
    wanted = os.environ.get(ASK_ENV, "").strip().lower()
    if wanted in ON:
        return True
    if wanted in OFF:
        return False
    shared = (os.environ.get(PASSWORD_ENV, "").strip()
              or os.environ.get(SECURE_ENV, "").strip().lower() in ON
              or os.environ.get(USERS_ENV, "").strip())
    return not shared


# ---------------------------------------------------------------------------
# What the model is given
# ---------------------------------------------------------------------------

def _number(sample_id: str) -> Optional[int]:
    match = re.search(r"(\d+)$", sample_id)
    return int(match.group(1)) if match else None


def mentioned(question: str, ids: Sequence[str], *, limit: int = MAX_NAMED) -> List[str]:
    """The samples a question names, in the order it names them, at most
    *limit*: by their id (``Sample000055``, any case), or by number —
    ``sample 55``, ``samples 3, 5 and 7``, ``#55``, ``S55`` — when exactly
    one id ends in that number."""
    ids = [str(s) for s in ids]
    hits: List[Tuple[int, str]] = []
    for sid in ids:
        match = re.search(rf"(?<![\w]){re.escape(sid)}(?![\w])", question, flags=re.I)
        if match:
            hits.append((match.start(), sid))
    by_number: Dict[int, List[str]] = {}
    for sid in ids:
        n = _number(sid)
        if n is not None:
            by_number.setdefault(n, []).append(sid)
    numbers: List[Tuple[int, str]] = []
    for match in re.finditer(r"samples?[\s_#-]*((?:#?\d{1,6}(?!\d)(?:\s*(?:,|and|&)\s*)?)+)",
                             question, flags=re.I):
        numbers += [(match.start(1) + m.start(), m.group())
                    for m in re.finditer(r"\d{1,6}", match.group(1))]
    numbers += [(m.start(), m.group(1))
                for m in re.finditer(r"(?:#|(?<![\w])S)(\d{1,6})(?!\d)", question)]
    for where, text in numbers:
        same = by_number.get(int(text), [])
        if len(same) == 1:
            hits.append((where, same[0]))
    found: List[str] = []
    for _, sid in sorted(hits):
        if sid not in found:
            found.append(sid)
    return found[:limit]


def _home(text: str) -> str:
    """*text* with the home folder not spelled out."""
    home = str(Path.home())
    return text.replace(home, "~") if home not in ("", "/") else text


def _cell(value) -> str:
    if value is None:
        return ""
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return ""
    except TypeError:
        pass
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def table_lines(table, columns: Sequence[str] = ()) -> List[str]:
    """A table as text for a model: a header row, then one line per row,
    ``a | b | c``. *columns* default to every column with a value that
    does not say where a file is (:data:`SKIP`)."""
    if table is None or len(table) == 0:
        return []
    if not columns:
        columns = [c for c in table.columns
                   if table[c].notna().any()
                   and not any(word in str(c).lower() for word in SKIP)]
    columns = [c for c in columns if c in table.columns]
    lines = [" | ".join(map(str, columns))]
    for _, row in table[columns].iterrows():
        lines.append(" | ".join(_cell(row[c]) for c in columns).rstrip(" |"))
    return lines


def kept_values(org, sample_id: str) -> Dict[str, Dict]:
    """``{analysis: values}`` of a sample's kept results, read from their
    files; a result whose file is not here is left out."""
    from pyDataOrg.analysis import store as _store

    sample = org.project.get_sample(sample_id)
    out: Dict[str, Dict] = {}
    if sample is None:
        return out
    for measurement in sample.get_measurements(modality="fit"):
        paths = measurement.resolve(org.resolver)
        if not paths:
            continue
        try:
            values = _store.peek(paths[0]).get("values", {})
        except Exception:                          # an unreadable file
            continue
        name = measurement.meta.get("analysis", measurement.role)
        out[name] = {k: v for k, v in values.items()
                     if isinstance(v, (int, float, str, bool))}
    return out


def dossier(org, sample_id: str) -> str:
    """One sample's full records, stage by stage, and its kept results'
    values, as compact JSON."""
    try:
        records = org.metadata(sample_id)
    except KeyError:
        return ""
    block = {"records": records, "kept results": kept_values(org, sample_id)}
    return (f"## Full records of {sample_id}\n"
            + json.dumps(block, ensure_ascii=False, separators=(",", ":"), default=str))


def organizer_context(org, *, question: str = "", table=None, columns: Sequence[str] = (),
                      sections: Sequence[Tuple[str, Sequence[str]]] = (),
                      title: str = "", max_chars: int = MAX_CONTEXT,
                      limit: int = MAX_NAMED) -> str:
    """An organizer's records as text for a model, at most *max_chars*:

    * its summary (``org.describe()``);
    * *sections* — ``(title, lines)`` the caller adds about its project:
      goals, how the numbers were made, a plan;
    * the samples the question names (:func:`mentioned`): their full records
      and kept results (:func:`dossier`), at most half of the room;
    * one line per sample of *table* (default: the organizer's sample
      table), its *columns* (default: :func:`table_lines`).

    The home folder is written ``~``.
    """
    parts = [f"# {title or org.project.config.name}"]
    try:
        with contextlib.redirect_stdout(io.StringIO()):     # it prints, too
            parts += ["", org.describe()]
    except Exception:                              # a summary is a courtesy
        pass
    for heading, lines in sections:
        lines = list(lines)
        if lines:
            parts += ["", f"## {heading}"] + lines
    if table is None:
        table = org.table(all_samples=True)
    ids = list(org.project.sample_ids())
    named, room = [], max_chars // 2
    for sid in mentioned(question, ids, limit=limit):
        full = dossier(org, sid)
        if sum(map(len, named)) + len(full) > room:
            named.append("(full records of further named samples left out for length)")
            break
        named.append(full)
    if named:
        parts += ["", "# The samples the question names"] + named
    lines = table_lines(table, columns)
    if lines:
        parts += ["", f"## Samples ({len(lines) - 1}), one line each"] + lines
    return _home("\n".join(parts))[:max_chars]


RULES = (
    "Answer only from the records below. If something is not in them, say plainly that "
    "it is not in the records — do not guess.",
    "Cite Sample IDs for every fact about samples.",
    "Be concise: Markdown, a short list or a small table, no preamble.",
    "Suggestions are welcome when asked: mark them **Suggestion**, and ground each in "
    "named records.",
    "Keep provenance apart and say it: measured on this sample, derived by an analysis "
    "from its data, or predicted by a model. Never present a prediction as a measurement.",
    "Do not run commands, read files or browse: everything you may use is below.",
)


def prompt(question: str, records_text: str,
           history: Sequence[Tuple[str, str]] = (), *, project: str = "",
           rules: Sequence[str] = ()) -> str:
    """The instructions (:data:`RULES`, then *rules*), the records and the
    question, as one prompt; the last three exchanges of *history* go too."""
    before = "".join(f"\nQ: {q}\nA: {a[:1500]}\n" for q, a in list(history)[-3:])
    told = "".join(f"- {r}\n" for r in (*RULES, *rules))
    return (
        f"You answer questions about {project or 'a research project'}'s sample records.\n"
        "Rules:\n" + told
        + "\n=== RECORDS ===\n" + records_text + "\n=== END OF RECORDS ===\n"
        + (f"\nThe conversation so far:{before}" if before else "")
        + f"\nQuestion: {question}\n")


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------

@dataclass
class Answer:
    text: str
    backend: str
    model: str
    seconds: float
    prompt_chars: int
    error: str = ""
    samples: List[str] = field(default_factory=list)
    context: str = ""

    def as_dict(self) -> Dict:
        return asdict(self)


def _shown(text: str, *paths: str) -> str:
    """*text* with temporary folders and the home folder not spelled out."""
    for path in paths:
        text = text.replace(path, "<tmp>")
    return _home(text)


def _chosen(backend) -> Optional[Backend]:
    if isinstance(backend, Backend):
        return backend
    found = backends()
    if backend:
        return next((b for b in found if backend in (b.key, b.title)), None)
    return found[0] if found else None


def ask(question: str, records_text: str, *, backend=None, timeout: float = 240,
        history: Sequence[Tuple[str, str]] = (), samples: Sequence[str] = (),
        project: str = "", rules: Sequence[str] = ()) -> Answer:
    """*question* answered by *backend* (a :class:`Backend`, a key, or the
    default of :func:`backends`) from *records_text* (see
    :func:`organizer_context`); *samples* are the ones whose full records
    it holds. Never raises: a missing tool, a timeout or a failed run comes
    back as ``Answer.error``."""
    chosen = _chosen(backend)
    full = prompt(question, records_text, history, project=project, rules=rules)
    if chosen is None:
        return Answer("", str(backend or ""), "", 0.0, len(full),
                      error="No AI model found here (codex, claude, gemini or ollama).",
                      samples=list(samples), context=records_text)
    with tempfile.TemporaryDirectory(prefix="dataorg-ask-") as tmp:
        work = Path(tmp) / "work"
        work.mkdir()
        out = Path(tmp) / "answer.md"
        argv = [a.replace("{out}", str(out)) for a in chosen.argv]
        start = time.monotonic()
        error, text = "", ""
        try:
            if shutil.which(argv[0]) is None:
                raise FileNotFoundError(argv[0])
            run = subprocess.run(argv, input=full, capture_output=True, text=True, cwd=work,
                                 timeout=timeout, env={**os.environ, **chosen.env})
            if chosen.output == "file" and out.is_file():
                text = out.read_text(encoding="utf-8")
            else:
                text = run.stdout
            if run.returncode != 0:
                tail = "\n".join((run.stderr or run.stdout).strip().splitlines()[-6:])
                error = f"{chosen.title} stopped (exit {run.returncode}): {tail}"
        except FileNotFoundError:
            error = f"{argv[0]} is not installed here."
        except subprocess.TimeoutExpired:
            error = f"{chosen.title} took longer than {timeout:.0f} s."
        except OSError as exc:
            error = f"{chosen.title} could not start: {exc}"
        seconds = time.monotonic() - start
        return Answer(_shown(text.strip(), tmp), chosen.key, chosen.model, seconds, len(full),
                      error=_shown(error, tmp), samples=list(samples), context=records_text)


__all__ = ["ASK_ENV", "DEFAULT_ENV", "MODEL_ENV", "CONFIG_ENV", "USER_CONFIG",
           "MAX_NAMED", "MAX_CONTEXT", "RULES", "Backend", "codex_config", "user_config",
           "backends", "enabled", "mentioned", "table_lines", "kept_values", "dossier",
           "organizer_context", "prompt", "Answer", "ask"]
