#!/usr/bin/env python3
"""
A protocol as an animated scheme: one card per step — a small drawing, a
title, a few short lines — arrows between them, and where the results go.

It only draws. The steps come from the caller, as plain mappings, so a
project can read them off its own records::

    steps = [{"icon": "stocks", "title": "Stocks",
              "lines": ["HAuCl₄ 2 mM · 666 µL"], "labels": ["Au"],
              "colours": ["#e8c547"]},
             {"icon": "heat", "title": "Grow", "lines": ["95 °C, 40 min"]}]
    show_scheme(steps, to=["Characterization: TEM"])

``icon`` is a key of :data:`ICONS` (an unknown one draws nothing); ``labels``
and ``colours`` are what the drawing shows (the bottles' names and liquids,
a colour change). The drawings are generic laboratory ones; nothing here
knows a chemistry.
"""

from __future__ import annotations

import html
import textwrap
from typing import Mapping, Sequence, Tuple, Union

INK = "#1d2433"
MUTED = "#5b6475"
WATER = "#cfe6f7"
W = 1200
CARD_W, GAP = 172, 30
ICON_H = 96
LINE_H = 17
WRAP = 24                      # characters per caption line

Chip = Union[str, Tuple[str, str]]


def _esc(text) -> str:
    return html.escape(str(text))


def _pick(colours: Sequence[str], i: int, default: str) -> str:
    return colours[i] if i < len(colours) and colours[i] else default


# --- the drawings, each in a ~150 × 90 box below (cx, y) --------------------

def _stocks(cx, y, labels=(), colours=()):
    n = max(1, min(len(labels) or 3, 4))
    step = 40 if n <= 3 else 34
    out = []
    for i in range(n):
        x = cx - step * (n - 1) / 2 + step * i - 10
        fill = _pick(colours, i, WATER)
        out.append(f'<rect x="{x}" y="{y + 8}" width="20" height="62" rx="9" fill="white" '
                   f'stroke="{INK}" stroke-width="1.6"/>'
                   f'<rect x="{x + 2}" y="{y + 32}" width="16" height="36" rx="7" '
                   f'fill="{fill}"/>')
        if i < len(labels):
            out.append(f'<text x="{x + 10}" y="{y + 86}" text-anchor="middle" '
                       f'class="el">{_esc(labels[i])}</text>')
    return "".join(out)


def _pump(cx, y, labels=(), colours=()):
    drop = _pick(colours, 0, "#56B4E9")
    return (f'<rect x="{cx - 62}" y="{y + 22}" width="74" height="22" rx="4" fill="white" '
            f'stroke="{INK}" stroke-width="1.6"/>'
            f'<rect x="{cx - 60}" y="{y + 25}" width="44" height="16" rx="2" fill="{drop}" '
            f'opacity="0.55"/>'
            f'<rect x="{cx - 76}" y="{y + 28}" width="14" height="10" fill="{INK}">'
            f'<animate attributeName="x" values="{cx - 76};{cx - 66};{cx - 76}" dur="2s" '
            f'repeatCount="indefinite"/></rect>'
            f'<path d="M {cx + 12} {y + 33} L {cx + 40} {y + 33} L {cx + 40} {y + 50}" '
            f'fill="none" stroke="{INK}" stroke-width="2"/>'
            f'<circle cx="{cx + 40}" cy="{y + 54}" r="4.5" fill="{drop}">'
            f'<animate attributeName="cy" values="{y + 52};{y + 74};{y + 74}" dur="1.6s" '
            f'repeatCount="indefinite"/><animate attributeName="opacity" values="1;1;0" '
            f'dur="1.6s" repeatCount="indefinite"/></circle>'
            f'<path d="M {cx + 22} {y + 70} L {cx + 22} {y + 88} L {cx + 58} {y + 88} '
            f'L {cx + 58} {y + 70}" fill="none" stroke="{INK}" stroke-width="1.6"/>')


def _flask(cx, y, fill, *, animate_to: str = ""):
    colour = (f'<animate attributeName="fill" values="{fill};{animate_to};{animate_to}" '
              f'dur="5s" repeatCount="indefinite"/>' if animate_to else "")
    return (f'<path d="M {cx - 8} {y + 4} L {cx - 8} {y + 26} C {cx - 34} {y + 34}, '
            f'{cx - 34} {y + 70}, {cx} {y + 72} C {cx + 34} {y + 70}, {cx + 34} {y + 34}, '
            f'{cx + 8} {y + 26} L {cx + 8} {y + 4} Z" fill="white" stroke="{INK}" '
            f'stroke-width="1.8"/>'
            f'<path d="M {cx - 26} {y + 46} C {cx - 26} {y + 66}, {cx + 26} {y + 66}, '
            f'{cx + 26} {y + 46} Z" fill="{fill}">{colour}</path>')


def _heat(cx, y, labels=(), colours=()):
    start = _pick(colours, 0, "#f2d16b")
    end = _pick(colours, 1, "")
    waves = "".join(
        f'<path d="M {cx + dx} {y + 82} q 5 -6 0 -12 q -5 -6 0 -12" fill="none" '
        f'stroke="#D55E00" stroke-width="2" stroke-linecap="round" class="heat" '
        f'style="animation-delay:{d}s"/>' for dx, d in ((-50, 0), (50, 0.4)))
    return (_flask(cx, y, start, animate_to=end) + waves
            + f'<rect x="{cx - 44}" y="{y + 76}" width="88" height="12" rx="3" '
              f'fill="#3a3f47"/>'
            + (f'<text x="{cx}" y="{y + 86}" text-anchor="middle" class="tiny" '
               f'fill="white">{_esc(labels[0])}</text>' if labels else ""))


def _spectrum(cx, y, peak_x, colour):
    return (f'<path d="M {cx + 10} {y + 80} C {cx + 22} {y + 78}, {peak_x - 8} {y + 40}, '
            f'{peak_x} {y + 40} C {peak_x + 8} {y + 40}, {peak_x + 14} {y + 74}, '
            f'{cx + 66} {y + 78}" fill="none" stroke="{colour}" stroke-width="2.4"/>'
            f'<line x1="{cx + 8}" y1="{y + 82}" x2="{cx + 68}" y2="{y + 82}" '
            f'stroke="{MUTED}" stroke-width="1.2"/>')


def _spectrometer(cx, y, labels=(), colours=()):
    sample = _pick(colours, 0, "#b23a48")
    return (f'<circle cx="{cx - 60}" cy="{y + 30}" r="9" fill="#ffe08a" stroke="{INK}"/>'
            f'<path d="M {cx - 50} {y + 30} L {cx - 6} {y + 30}" stroke="#E69F00" '
            f'stroke-width="2.2" class="dash"/>'
            f'<rect x="{cx - 36}" y="{y + 12}" width="20" height="40" rx="2" fill="{sample}" '
            f'fill-opacity="0.7" stroke="{INK}" stroke-width="1.4"/>'
            f'<rect x="{cx - 6}" y="{y + 20}" width="12" height="20" rx="2" fill="{INK}"/>'
            + _spectrum(cx, y, cx + 38, sample))


def _collect(cx, y, labels=(), colours=()):
    fill = _pick(colours, 0, "#b23a48")
    return (f'<line x1="{cx}" y1="{y}" x2="{cx}" y2="{y + 40}" stroke="{INK}" '
            f'stroke-width="2.2"><animate attributeName="y2" values="{y + 30};{y + 58};'
            f'{y + 30}" dur="2.4s" repeatCount="indefinite"/></line>'
            f'<path d="M {cx - 22} {y + 36} L {cx - 22} {y + 84} Q {cx - 22} {y + 90} '
            f'{cx - 16} {y + 90} L {cx + 16} {y + 90} Q {cx + 22} {y + 90} {cx + 22} '
            f'{y + 84} L {cx + 22} {y + 36}" fill="none" stroke="{INK}" stroke-width="1.8"/>'
            f'<rect x="{cx - 20}" y="{y + 62}" width="40" height="26" rx="4" fill="{fill}"/>'
            f'<rect x="{cx - 26}" y="{y + 30}" width="52" height="7" rx="2" fill="#7d8597"/>')


def _trigger(cx, y, labels=(), colours=()):
    drop = _pick(colours, 0, "#b23a48")
    cell = _pick(colours, 1, "#f2d16b")
    return (f'<path d="M {cx - 6} {y + 2} L {cx + 6} {y + 2} L {cx + 2} {y + 18} '
            f'L {cx - 2} {y + 18} Z" fill="white" stroke="{INK}" stroke-width="1.4"/>'
            f'<circle cx="{cx}" cy="{y + 22}" r="5" fill="{drop}">'
            f'<animate attributeName="cy" values="{y + 22};{y + 50};{y + 50}" dur="1.8s" '
            f'repeatCount="indefinite"/><animate attributeName="opacity" values="1;1;0" '
            f'dur="1.8s" repeatCount="indefinite"/></circle>'
            f'<rect x="{cx - 22}" y="{y + 40}" width="44" height="48" rx="3" fill="{cell}" '
            f'fill-opacity="0.75" stroke="{INK}" stroke-width="1.6"/>')


def _react(cx, y, labels=(), colours=()):
    start = _pick(colours, 0, "#f2d16b")
    end = _pick(colours, 1, "#f7f7f2")
    return (f'<rect x="{cx - 64}" y="{y + 18}" width="36" height="64" rx="3" fill="{start}" '
            f'stroke="{INK}" stroke-width="1.6"><animate attributeName="fill" '
            f'values="{start};{end};{start}" dur="5s" repeatCount="indefinite"/></rect>'
            f'<line x1="{cx - 10}" y1="{y + 84}" x2="{cx + 66}" y2="{y + 84}" '
            f'stroke="{MUTED}" stroke-width="1.2"/>'
            f'<line x1="{cx - 10}" y1="{y + 84}" x2="{cx - 10}" y2="{y + 14}" '
            f'stroke="{MUTED}" stroke-width="1.2"/>'
            f'<path d="M {cx - 8} {y + 22} C {cx + 8} {y + 64}, {cx + 30} {y + 76}, '
            f'{cx + 64} {y + 78}" fill="none" stroke="#D55E00" stroke-width="2.4" '
            f'class="dash"/>')


def _rinse(cx, y, labels=(), colours=()):
    return (f'<g><path d="M {cx - 26} {y + 46} A 26 26 0 1 1 {cx + 22} {y + 60}" '
            f'fill="none" stroke="#0072B2" stroke-width="3" marker-end="url(#a-blue)"/>'
            f'<animateTransform attributeName="transform" type="rotate" '
            f'from="0 {cx} {y + 46}" to="360 {cx} {y + 46}" dur="4s" '
            f'repeatCount="indefinite"/></g>'
            + "".join(f'<circle cx="{cx + dx}" cy="{y + 46}" r="3.5" fill="#56B4E9">'
                      f'<animate attributeName="cy" values="{y + 30};{y + 86}" dur="1.6s" '
                      f'begin="{d}s" repeatCount="indefinite"/></circle>'
                      for dx, d in ((-6, 0), (8, 0.6))))


def _grid(cx, y, labels=(), colours=()):
    lines = "".join(f'<line x1="{cx - 38}" y1="{y + 46 + d}" x2="{cx + 38}" y2="{y + 46 + d}" '
                    f'stroke="#b8860b" stroke-width="1"/>'
                    f'<line x1="{cx + d}" y1="{y + 8}" x2="{cx + d}" y2="{y + 84}" '
                    f'stroke="#b8860b" stroke-width="1"/>' for d in (-24, -8, 8, 24))
    dots = "".join(f'<circle cx="{cx + dx}" cy="{y + 46 + dy}" r="3" fill="{INK}"/>'
                   for dx, dy in ((-14, -16), (4, -4), (18, 10), (-6, 18), (12, -20)))
    return (f'<defs><clipPath id="g{cx:.0f}"><circle cx="{cx}" cy="{y + 46}" r="38"/>'
            f'</clipPath></defs><circle cx="{cx}" cy="{y + 46}" r="40" fill="#f3e6c4" '
            f'stroke="#b8860b" stroke-width="2"/><g clip-path="url(#g{cx:.0f})">{lines}</g>'
            + dots)


def _beam(cx, y, labels=(), colours=()):
    wells = "".join(f'<circle cx="{cx - 4 + 13 * k}" cy="{y + 50 + 13 * r}" r="4.5" '
                    f'fill="{_pick(colours, 0, "#b23a48") if (r + k) % 2 == 0 else WATER}"/>'
                    for r in range(3) for k in range(5))
    rings = "".join(f'<circle cx="{cx + 22}" cy="{y + 62}" r="{r}" fill="none" '
                    f'stroke="#0072B2" stroke-width="1.2" opacity="0.6" class="pulse" '
                    f'style="animation-delay:{d}s"/>' for r, d in ((18, 0), (30, 0.5)))
    return (f'<rect x="{cx - 14}" y="{y + 40}" width="80" height="46" rx="4" '
            f'fill="#2b2f36"/>{wells}'
            f'<path d="M {cx - 72} {y + 12} L {cx + 16} {y + 58}" stroke="#0072B2" '
            f'stroke-width="2.4" class="dash"/>{rings}'
            f'<text x="{cx - 56}" y="{y + 8}" class="tiny">X-ray</text>')


def _chart(cx, y, labels=(), colours=()):
    pts = ((-46, 70), (-30, 58), (-16, 62), (0, 44), (14, 36), (30, 26), (46, 20))
    dots = "".join(f'<circle cx="{cx + dx}" cy="{y + dy}" r="4" '
                   f'fill="{_pick(colours, 0, "#0072B2")}"/>' for dx, dy in pts)
    return (f'<line x1="{cx - 60}" y1="{y + 84}" x2="{cx + 62}" y2="{y + 84}" '
            f'stroke="{MUTED}" stroke-width="1.4"/>'
            f'<line x1="{cx - 60}" y1="{y + 84}" x2="{cx - 60}" y2="{y + 6}" '
            f'stroke="{MUTED}" stroke-width="1.4"/>'
            f'<path d="M {cx - 50} {y + 72} C {cx - 10} {y + 60}, {cx + 10} {y + 30}, '
            f'{cx + 56} {y + 16}" fill="none" stroke="#D55E00" stroke-width="2" '
            f'class="dash"/>{dots}')


def _target(cx, y, labels=(), colours=()):
    colour = _pick(colours, 0, "#D55E00")
    return (f'<circle cx="{cx}" cy="{y + 46}" r="38" fill="white" stroke="{colour}" '
            f'stroke-width="2.4"/><circle cx="{cx}" cy="{y + 46}" r="24" fill="none" '
            f'stroke="{colour}" stroke-width="2.4"/><circle cx="{cx}" cy="{y + 46}" r="9" '
            f'fill="{colour}" class="pulse"/>')


#: The drawings a step can have, by name.
ICONS = {"stocks": _stocks, "pump": _pump, "heat": _heat, "spectrometer": _spectrometer,
         "collect": _collect, "trigger": _trigger, "react": _react, "rinse": _rinse,
         "grid": _grid, "beam": _beam, "chart": _chart, "target": _target}


def _lines(step: Mapping) -> list:
    out = []
    for line in step.get("lines") or ():
        out += textwrap.wrap(str(line), WRAP) or [""]
    return out


def card_height(steps: Sequence[Mapping]) -> int:
    """The cards' height: the tallest caption decides."""
    most = max((len(_lines(s)) for s in steps), default=0)
    return ICON_H + 52 + LINE_H * max(most, 2) + 10


def scheme_height(steps: Sequence[Mapping], to: Sequence[Chip] = (),
                  footer: str = "") -> int:
    """The height, in pixels, :func:`scheme_html` needs at full width."""
    return 20 + card_height(steps) + (70 if to else 10) + (34 if footer else 0) + 6


def scheme_html(steps: Sequence[Mapping], *, to: Sequence[Chip] = (),
                footer: str = "", colour: str = "#E69F00",
                height: int = 0) -> str:
    """The steps as a self-contained animated page.

    *to* are where the results go — a chip each, ``"label"`` or
    ``("label", colour)`` — drawn under the last card; *footer*, a line
    under everything (who, when, which protocol). *height* defaults to
    :func:`scheme_height`.
    """
    n = max(len(steps), 1)
    card_w = min(CARD_W, (W - 40 - (n - 1) * GAP) / n)
    x0 = (W - (n * card_w + (n - 1) * GAP)) / 2
    top = 20
    card_h = card_height(steps)
    parts = []
    for i, step in enumerate(steps):
        x = x0 + i * (card_w + GAP)
        cx = x + card_w / 2
        draw = ICONS.get(step.get("icon", ""))
        icon = draw(cx, top + 22, tuple(step.get("labels") or ()),
                    tuple(step.get("colours") or ())) if draw else ""
        caption = "".join(
            f'<text x="{cx}" y="{top + ICON_H + 60 + LINE_H * k}" text-anchor="middle" '
            f'class="cap">{_esc(t)}</text>' for k, t in enumerate(_lines(step)))
        parts.append(
            f'<g class="card"><rect x="{x}" y="{top}" width="{card_w}" height="{card_h}" '
            f'rx="16" fill="white" stroke="#e1e5ec" filter="url(#sh)"/>'
            f'<rect x="{x}" y="{top}" width="{card_w}" height="6" rx="3" fill="{colour}"/>'
            f'{icon}'
            f'<circle cx="{cx}" cy="{top + 3}" r="13" fill="{colour}" stroke="white" '
            f'stroke-width="2"/>'
            f'<text x="{cx}" y="{top + 8}" text-anchor="middle" class="num">{i + 1}</text>'
            f'<text x="{cx}" y="{top + ICON_H + 36}" text-anchor="middle" class="step">'
            f'{_esc(step.get("title", ""))}</text>{caption}</g>')
        if i < n - 1:
            ax = x + card_w + 4
            parts.append(f'<path d="M {ax} {top + card_h / 2} L {ax + GAP - 8} '
                         f'{top + card_h / 2}" stroke="{colour}" stroke-width="2.6" '
                         f'class="dash" marker-end="url(#a-stage)"/>')
    y = top + card_h + 26
    if to:
        last = x0 + (n - 1) * (card_w + GAP) + card_w / 2
        right = x0 + n * card_w + (n - 1) * GAP
        for chip in reversed(list(to)):
            label, tint = (chip, colour) if isinstance(chip, str) else chip
            label = f"→ {label}"
            width = 7.4 * len(label) + 28
            right -= width
            parts.append(f'<g><rect x="{right}" y="{y}" width="{width}" height="34" rx="17" '
                         f'fill="{tint}" fill-opacity="0.12" stroke="{tint}"/>'
                         f'<text x="{right + width / 2}" y="{y + 22}" text-anchor="middle" '
                         f'class="to" fill="{tint}">{_esc(label)}</text></g>')
            right -= 12
        parts.append(f'<path d="M {last} {top + card_h + 2} L {last} {y - 4}" '
                     f'stroke="{MUTED}" stroke-width="2" class="dash"/>')
        y += 34
    if footer:
        parts.append(f'<text x="{x0}" y="{y + 28}" class="who">{_esc(footer)}</text>')
        y += 34
    view_h = y + 10
    height = height or scheme_height(steps, to, footer)
    svg = f"""
<svg viewBox="0 0 {W} {view_h}" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-label="protocol">
<defs>
  <filter id="sh" x="-10%" y="-10%" width="120%" height="130%">
    <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#1d2433" flood-opacity="0.10"/>
  </filter>
  <marker id="a-stage" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7"
          orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{colour}"/></marker>
  <marker id="a-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5"
          orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#0072B2"/></marker>
</defs>
{''.join(parts)}
</svg>"""
    style = f"""
<style>
  html, body {{ margin: 0; padding: 0; background: transparent;
    font-family: "Source Sans Pro", "Source Sans 3", -apple-system, "Segoe UI", sans-serif; }}
  svg {{ width: 100%; height: {height - 6}px; display: block; }}
  .num {{ font-size: 13px; font-weight: 800; fill: white; }}
  .step {{ font-size: 17px; font-weight: 800; fill: {INK}; }}
  .cap {{ font-size: 13px; fill: {MUTED}; }}
  .el {{ font-size: 11.5px; font-weight: 800; fill: {INK}; }}
  .tiny {{ font-size: 10.5px; fill: {MUTED}; }}
  .who {{ font-size: 15px; font-weight: 700; fill: {MUTED}; }}
  .to {{ font-size: 13.5px; font-weight: 700; }}
  .dash {{ stroke-dasharray: 6 6; animation: dash 1.2s linear infinite; }}
  .heat {{ stroke-dasharray: 4 5; animation: dash 0.9s linear infinite; }}
  .pulse {{ animation: pulse 1.6s ease-in-out infinite; transform-box: fill-box;
    transform-origin: center; }}
  .card:hover rect:first-child {{ stroke: {colour}; }}
  @keyframes dash {{ to {{ stroke-dashoffset: -12; }} }}
  @keyframes pulse {{ 50% {{ opacity: 0.35; }} }}
</style>"""
    return f"<!doctype html><html><head>{style}</head><body>{svg}</body></html>"


def show_scheme(steps: Sequence[Mapping], *, to: Sequence[Chip] = (), footer: str = "",
                colour: str = "#E69F00") -> None:
    """Put the scheme on the page (an iframe of :func:`scheme_html`)."""
    import streamlit.components.v1 as components

    height = scheme_height(steps, to, footer)
    components.html(scheme_html(steps, to=to, footer=footer, colour=colour,
                                height=height), height=height)


__all__ = ["ICONS", "card_height", "scheme_height", "scheme_html", "show_scheme"]
