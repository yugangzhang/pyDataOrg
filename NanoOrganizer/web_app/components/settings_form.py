#!/usr/bin/env python3
"""
A form for an analysis' settings, built from the analysis itself.

Settings are what a person chooses and keeps the same for every sample — a
width, a window, a method (:meth:`Analysis.settings_for`). The form offers a
control for each, starting from *current* (say, the settings the kept results
were made with, ``wb.kept_settings(key)``) and the analysis' defaults
otherwise, and returns the whole settings dict — the one ``wb.run_method``,
``wb.run`` and ``wb.batch`` take. A newly registered analysis gets a working
form with no page change.

The control follows the value:

=====================  ==================================================
bool                   a toggle
int, float             a number
str                    a text box, or a choice when *choices* names them
a list of numbers      one text box, ``316, 400``; blank is ``None`` when
                       the setting may be ``None``
``None``               a "set" toggle and a number; left off, the analysis
                       decides (``Optional[bool]``: auto / yes / no)
=====================  ==================================================
"""

from __future__ import annotations

import collections.abc
import math
import typing
from typing import Any, Dict, Optional, Sequence

import streamlit as st

from NanoOrganizer.analysis import get_analysis


def _hints(spec) -> Dict[str, Any]:
    """The type hints of the function the settings come from, if readable."""
    function = spec.kernel if spec.kernel is not None else spec.func
    try:
        return typing.get_type_hints(function)
    except Exception:                        # unresolvable hints: go by value
        return {}


def _optional(hint) -> bool:
    return type(None) in getattr(hint, "__args__", ())


def _inner(hint):
    """``Optional[X]`` → ``X``."""
    args = [a for a in getattr(hint, "__args__", ()) if a is not type(None)]
    return args[0] if len(args) == 1 else hint


def _step(value: float) -> float:
    return 10.0 ** math.floor(math.log10(abs(value))) / 10.0 if value else 0.1


def _numbers(text: str):
    """``"316, 400"`` → ``(316.0, 400.0)``; ``""`` → ``None``."""
    parts = [p for p in text.replace(",", " ").split() if p]
    if not parts:
        return None
    return tuple(int(p) if p.lstrip("-").isdigit() else float(p) for p in parts)


def _show(value) -> str:
    return ", ".join(f"{v:g}" for v in value) if value is not None else ""


def _choice(value) -> str:
    if value is None:
        return "auto"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def setting_widget(name: str, value: Any, default: Any, key: str, *,
                   hint=None, choices: Optional[Sequence] = None,
                   help: Optional[str] = None) -> Any:
    """One control for one setting; returns the value chosen."""
    nullable = default is None or _optional(hint)
    kind = _inner(hint) if hint is not None else None
    if choices is None and kind is bool and value is None:
        choices = (None, True, False)

    if choices is not None:
        options = list(choices)
        if value not in options:
            options.insert(0, value)
        return st.selectbox(name, options, index=options.index(value),
                            key=key, help=help, format_func=_choice)
    if isinstance(value, bool):
        return st.toggle(name, value=value, key=key, help=help)
    if isinstance(value, int):
        return int(st.number_input(name, value=value, step=1, key=key, help=help))
    if isinstance(value, float):
        return float(st.number_input(name, value=value, step=_step(value),
                                     format="%g", key=key, help=help))
    if isinstance(value, str):
        return st.text_input(name, value=value, key=key, help=help)
    origin = typing.get_origin(kind)
    if isinstance(value, (list, tuple)) or isinstance(default, (list, tuple)) \
            or origin in (tuple, list, collections.abc.Sequence):
        text = st.text_input(
            name, value=_show(value), key=key,
            help=(help or "numbers, comma-separated")
            + (" — blank for none" if nullable else ""))
        try:
            chosen = _numbers(text)
            if chosen is not None and isinstance(default, (list, tuple)) \
                    and any(isinstance(v, float) for v in default):
                chosen = tuple(float(v) for v in chosen)
        except ValueError:
            st.caption(f"⚠️ {name}: not numbers — kept {_show(value)!r}")
            return value
        if chosen is None and not nullable:
            st.caption(f"⚠️ {name} cannot be blank — kept {_show(value)!r}")
            return value
        return chosen
    if value is None and kind in (None, int, float):
        number = int if kind is int else float
        on = st.toggle(f"set {name}", value=False, key=f"{key}_on",
                       help=help or "Left off, the analysis decides this itself.")
        if not on:
            return None
        return number(st.number_input(name, value=number(0), key=key,
                                      format="%d" if number is int else "%g"))
    st.caption(f"{name} = {value!r} (not editable here)")
    return value


def settings_form(analysis: str, key: str,
                  current: Optional[Dict[str, Any]] = None, *,
                  only: Sequence[str] = (), choices: Optional[Dict[str, Sequence]] = None,
                  help: Optional[Dict[str, str]] = None,
                  columns: int = 3) -> Dict[str, Any]:
    """Controls for *analysis*' settings; returns the whole settings dict.

    *current* overrides the defaults the controls start from; *only* limits
    the controls to those names (the others keep their current value);
    *choices* names the allowed values of a setting (``{"method": ("avg",
    "fit", "both")}``); *help* is a tooltip per setting. Widget keys are
    ``f"{key}_{name}"``.
    """
    spec = get_analysis(analysis)
    defaults = spec.settings_for()
    hints = _hints(spec)
    values = {**defaults, **{k: v for k, v in (current or {}).items()
                             if k in defaults}}
    for name, value in values.items():          # 3 kept for a 3.0 setting
        if isinstance(defaults[name], float) and isinstance(value, int) \
                and not isinstance(value, bool):
            values[name] = float(value)
    shown = [name for name in defaults if not only or name in only]
    if not shown:
        st.caption("No settings.")
        return values

    slots = st.columns(columns)
    chosen = dict(values)
    for index, name in enumerate(shown):
        with slots[index % columns]:
            chosen[name] = setting_widget(
                name, values[name], defaults[name], f"{key}_{name}",
                hint=hints.get(name), choices=(choices or {}).get(name),
                help=(help or {}).get(name))
    return chosen


def forget_settings(analysis: str, key: str) -> None:
    """Drop the form's widget state, so it starts again from *current*."""
    for name in get_analysis(analysis).settings_for():
        for suffix in ("", "_on"):
            st.session_state.pop(f"{key}_{name}{suffix}", None)


def settings_code(name: str, settings: Dict[str, Any],
                  defaults: Optional[Dict[str, Any]] = None,
                  width: int = 72) -> str:
    """``name = dict(...)`` for a notebook, wrapped at *width*; with
    *defaults*, only what differs from them."""
    def text(value):
        if isinstance(value, list):
            value = tuple(value)
        return repr(value)

    items = [f"{k}={text(v)}" for k, v in settings.items()
             if defaults is None or _differs(v, defaults.get(k))]
    head = f"{name} = dict("
    lines, line = [], head
    for index, item in enumerate(items):         # a setting is never split
        item += ")" if index == len(items) - 1 else ","
        if line.strip() and not line.endswith("(") \
                and len(line) + 1 + len(item) > width:
            lines.append(line)
            line = " " * len(head) + item
        else:
            line += ("" if line.endswith("(") else " ") + item
    lines.append(line if items else head + ")")
    return "\n".join(lines)


def _differs(a, b) -> bool:
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) != list(b)
    return a != b


__all__ = ["settings_form", "setting_widget", "forget_settings", "settings_code"]
