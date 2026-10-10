#!/usr/bin/env python3
"""
Campaign — inputs → results → objectives, across every sample.

The page composes :mod:`pyDataOrg.campaign` (the table, ranking, Pareto
front, progress) and :mod:`pyDataOrg.viz.campaign` (the figures); it
computes nothing itself.
"""

import matplotlib.pyplot as plt
import streamlit as st

from pyDataOrg import campaign as C
from pyDataOrg.viz import campaign as figures
from pyDataOrg.web_app.components.campaign_picker import pick_campaign
from pyDataOrg.web_app.state import require_workbench

st.title("🏁 Campaign")
workbench = require_workbench()
spec, frame = pick_campaign(workbench)
if spec is None:
    st.stop()
labels = spec.labels


def show(figure):
    figure.tight_layout()
    st.pyplot(figure, width="stretch")
    plt.close(figure)


# ---------------------------------------------------------------------------
# Which rows
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("**Rows**")
    protocol = C.majority(frame, spec.protocol)
    same = st.checkbox(
        "Only rows measured like most"
        + (" (" + ", ".join(f"{labels.get(k, k)} = {v}"
                            for k, v in protocol.items()) + ")"
           if protocol else ""),
        value=bool(protocol), key="org_camp_protocol", disabled=not protocol,
        help="Rows measured another way are not on the same scale.")
    finished = st.checkbox("Only finished rows", value=spec.done is not None,
                           key="org_camp_done", disabled=spec.done is None)

rows = C.comparable(frame, (), protocol=None if same else {},
                    protocol_columns=spec.protocol,
                    done=spec.done if finished else None)
shown = frame[rows]
reference = spec.references(shown)
goal_names = [o.name for o in spec.objectives]
references = shown[reference & C.usable(shown, goal_names)]
rows_in = shown[~reference]

numeric = [n for n in spec.names(*C.NUMERIC_KINDS)
           if n in frame and frame[n].notna().any()]
goals = [n for n in spec.names("objective") if n in numeric] or \
    [n for n in goal_names if n in numeric]

st.caption(f"**{len(shown)}** of {len(frame)} samples shown"
           + (f", {int(reference.sum())} of them references (no inputs)"
              if reference.any() else "") + ".")

tab_map, tab_pair, tab_pareto, tab_progress, tab_table = st.tabs(
    ["Input map", "Any pairing", "Pareto & ranking", "Progress", "Table"])

with tab_map:
    if not spec.inputs or not numeric:
        st.info("This campaign has no input or no numeric column yet.", icon="📭")
    else:
        colour = st.selectbox("Colour by", goals + [n for n in numeric
                                                    if n not in goals],
                              key="org_camp_map_colour",
                              format_func=lambda n: labels.get(n, n))
        figure, ax = plt.subplots(figsize=(8, 5.2))
        figures.plot_design_map(
            rows_in, spec.inputs[0],
            spec.inputs[1] if len(spec.inputs) > 1 else "", ax=ax,
            color=colour, labels=labels)
        show(figure)
        st.caption("Open circles were made but have no value for this column "
                   "yet — usually a measurement still to run.")

with tab_pair:
    if len(numeric) < 2:
        st.info("Needs two numeric columns.", icon="📭")
    else:
        a, b, c = st.columns(3)
        x = a.selectbox("x", numeric, key="org_camp_x",
                        format_func=lambda n: labels.get(n, n))
        y = b.selectbox("y", numeric, index=min(1, len(numeric) - 1),
                        key="org_camp_y", format_func=lambda n: labels.get(n, n))
        colour = c.selectbox("colour", [""] + numeric, key="org_camp_c",
                             format_func=lambda n: labels.get(n, n) or "—")
        figure, ax = plt.subplots(figsize=(8, 5.2))
        figures.plot_by_sample(rows_in, y, x=x, ax=ax, color=colour,
                               labels=labels)
        show(figure)

with tab_pareto:
    if len(goals) < 2:
        st.info("A trade-off needs two goals.", icon="📭")
    else:
        a, b = st.columns(2)
        first = a.selectbox("Goal 1", goals, key="org_camp_o1",
                            format_func=lambda n: spec.objective(n).label(labels))
        second = b.selectbox("Goal 2", goals, index=1, key="org_camp_o2",
                             format_func=lambda n: spec.objective(n).label(labels))
        pair = [spec.objective(first), spec.objective(second)]
        names = [g.name for g in pair]
        scored = rows_in[C.usable(rows_in, spec.inputs + names)]
        front = C.pareto_mask(scored[names].to_numpy(float),
                              [g.maximize for g in pair]) if len(scored) else []
        figure, ax = plt.subplots(figsize=(8, 5.2))
        figures.plot_pareto(scored, pair, ax=ax, front=front,
                            references=references, labels=labels)
        show(figure)
        ranked = spec.rank(rows_in, pair)
        st.markdown("**Ranking** — each goal rescaled 0–1 over these samples, "
                    "then averaged; `pareto` marks the samples nothing beats "
                    "on both.")
        st.dataframe(ranked[["sample"] + spec.inputs + names
                            + ["score", "pareto"]],
                     hide_index=True, width="stretch")

with tab_progress:
    if not spec.when or not goals:
        st.info("Progress needs a time column and a goal.", icon="📭")
    else:
        goal = st.selectbox("Goal", goals, key="org_camp_progress",
                            format_func=lambda n: spec.objective(n).label(labels))
        timeline = C.chronological(rows_in[C.usable(rows_in, [goal])], spec.when)
        values = timeline[goal].to_numpy(float)
        figure, ax = plt.subplots(figsize=(9, 4.2))
        figures.plot_progress(values,
                              C.best_so_far(values, spec.objective(goal).maximize),
                              ax=ax, name=goal,
                              sample_labels=list(timeline["sample"]),
                              labels=labels)
        show(figure)
        st.caption("In the order the samples were measured. A flat red line "
                   "over many samples is a campaign that has stopped learning.")

with tab_table:
    st.dataframe(shown, hide_index=True, width="stretch")
    st.download_button("Download CSV", shown.to_csv(index=False).encode(),
                       file_name=f"{spec.name}_campaign.csv", mime="text/csv",
                       key="org_camp_csv")
    st.caption("Short names; every recorded field is on **Explore & Filter**.")
