#!/usr/bin/env python3
"""
Next experiments — a surrogate model of the campaign, and what to try next.

Composes :mod:`pyDataOrg.optimize` (propose, cross-validate, save) and
:mod:`pyDataOrg.viz.campaign` (the figures). Proposals are suggestions for a
person to approve; nothing is sent anywhere.
"""

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from pyDataOrg import campaign as C
from pyDataOrg import optimize
from pyDataOrg.core.pathmap import display_path
from pyDataOrg.viz import campaign as figures
from pyDataOrg.web_app.components.campaign_picker import pick_campaign
from pyDataOrg.web_app.state import require_workbench

st.title("🎯 Next experiments")
st.caption(
    "One model per goal learns inputs → results from the samples so far, and "
    "an engine proposes the batch expected to improve on them. Proposals are "
    "suggestions for a person to approve — nothing is sent anywhere.")
workbench = require_workbench()
spec, frame = pick_campaign(workbench)
if spec is None:
    st.stop()
labels = spec.labels

goals_all = [n for n in spec.names("objective")
             if n in frame and frame[n].notna().any()]
if not spec.inputs or not goals_all:
    st.info("This campaign needs at least one input and one goal with values.",
            icon="📭")
    st.stop()


def show(figure):
    figure.tight_layout()
    st.pyplot(figure, width="stretch")
    plt.close(figure)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

left, right = st.columns(2)
with left:
    st.markdown("**Goals**")
    defaults = [o.name for o in spec.objectives if o.name in goals_all][:2] \
        or goals_all[:1]
    chosen = st.multiselect("Goals", goals_all, default=defaults,
                            key="org_next_goals",
                            format_func=lambda n: spec.objective(n).label(labels))
    a, b, c = st.columns(3)
    n = a.slider("Proposals", 1, 8, 4, key="org_next_n")
    seed = b.number_input("Seed", 0, 9999, 0, key="org_next_seed")
    engine = c.selectbox("Engine", optimize.list_engines(), key="org_next_engine")
with right:
    st.markdown("**Search space**")
    bounds = {}
    for name in spec.inputs:
        values = frame[name].astype(float)
        lo, hi = spec.bounds.get(name, (float(np.nanmin(values)),
                                        float(np.nanmax(values))))
        a, b = st.columns(2)
        bounds[name] = (
            a.number_input(f"{labels.get(name, name)} from", value=float(lo),
                           key=f"org_next_{name}_lo"),
            b.number_input("to", value=float(hi), key=f"org_next_{name}_hi"))
    protocol = C.majority(frame, spec.protocol)
    same = st.checkbox("Train only on rows measured like most", value=True,
                       key="org_next_same", disabled=not protocol)

if not chosen:
    st.info("Pick at least one goal.", icon="👆")
    st.stop()
goals = [spec.objective(name) for name in chosen]
rows = spec.comparable(frame, chosen, protocol=None if same else {})
st.caption(f"Training on **{int(rows.sum())}** samples: "
           + ", ".join(map(str, frame.loc[rows, "sample"])))

settings = {"campaign": spec.name, "goals": chosen, "n": int(n),
            "seed": int(seed), "engine": engine, "bounds": bounds,
            "same_protocol": bool(same),
            "samples": list(frame.loc[rows, "sample"])}
if st.button("Propose", type="primary", key="org_next_go"):
    with st.spinner("Fitting the surrogate and choosing the batch …"):
        try:
            st.session_state["org_next_plan"] = (settings, optimize.propose(
                frame, variables=spec.inputs, objectives=goals, bounds=bounds,
                n=int(n), rows=rows, seed=int(seed), rounding=spec.rounding,
                engine=engine))
        except Exception as exc:
            st.session_state.pop("org_next_plan", None)
            st.error(f"Could not propose: {exc}", icon="🚫")

stored = st.session_state.get("org_next_plan")
if stored is None:
    st.stop()
used, plan = stored
if used != settings:
    st.info("Settings changed since this proposal — press **Propose** again.",
            icon="🔁")
    st.stop()

# ---------------------------------------------------------------------------
# The proposal
# ---------------------------------------------------------------------------

table = plan.suggestions
st.subheader("Proposed")
st.dataframe(table, hide_index=True, width="stretch",
             column_config={col: st.column_config.NumberColumn(format="%.3g")
                            for col in table.columns
                            if col.endswith(("_pred", "_sd"))})
for note in plan.notes:
    st.warning(note, icon="⚠️")

scored = frame[rows]
if len(goals) >= 2:
    names = [g.name for g in goals[:2]]
    front = C.pareto_mask(scored[names].to_numpy(float),
                          [g.maximize for g in goals[:2]])
    figure, ax = plt.subplots(figsize=(7, 5))
    figures.plot_pareto(scored, goals[:2], ax=ax, front=front, proposals=table,
                        references=frame[spec.references(frame)
                                         & C.usable(frame, names)],
                        labels=labels)
    show(figure)

st.subheader("What the model believes")
gx, gy, mean, sd = plan.surface(60 if len(plan.variables) == 1 else 45)
if gy is None:
    figure, axes = plt.subplots(1, len(goals), figsize=(6 * len(goals), 4.4),
                                squeeze=False)
    for j, goal in enumerate(goals):
        figures.plot_surrogate_line(
            gx, mean[:, j], sd[:, j], ax=axes[0, j], points=plan.X[:, 0],
            observed=plan.Y[:, j], proposals=table, x=plan.variables[0],
            name=goal.name, title=goal.label(labels), labels=labels)
else:
    figure, axes = plt.subplots(2, len(goals), figsize=(6 * len(goals), 9),
                                squeeze=False)
    for j, goal in enumerate(goals):
        figures.plot_surrogate(
            gx, gy, mean[:, j], ax=axes[0, j], points=plan.X[:, :2],
            proposals=table, x=plan.variables[0], y=plan.variables[1],
            title=f"mean — {labels.get(goal.name, goal.name)}",
            colorbar_label=goal.name, labels=labels)
        figures.plot_surrogate(
            gx, gy, sd[:, j], ax=axes[1, j], points=plan.X[:, :2],
            proposals=table, x=plan.variables[0], y=plan.variables[1],
            title="uncertainty (sd)", colorbar_label="sd", cmap="magma",
            labels=labels)
show(figure)
st.caption("Proposals sit where the predicted value is good, where the model "
           "is unsure, or both — that balance is what the engine is for.")

st.subheader("Can the model be trusted?")
st.caption(
    "Each training sample is predicted from the others. An error below ~0.8 × "
    "the spread means the model has learned that goal; at 1 or above it "
    "predicts no better than the average, and proposals for that goal are "
    "exploration rather than exploitation.")
if st.button(f"Run the leave-one-out check ({len(plan.samples)} fits)",
             key="org_next_cv"):
    with st.spinner("Refitting without each sample …"):
        st.session_state["org_next_cv_result"] = (used, optimize.cross_validate(
            frame, variables=spec.inputs, objectives=goals, bounds=bounds,
            rows=rows, seed=int(seed), engine=engine))
checked = st.session_state.get("org_next_cv_result")
if checked is not None and checked[0] == used:
    cv = checked[1]
    st.code(cv.summary(), language=None)
    figure, axes = plt.subplots(1, len(goals), figsize=(5.5 * len(goals), 5),
                                squeeze=False)
    for ax, goal in zip(axes[0], goals):
        figures.plot_parity(cv.table, goal.name, ax=ax,
                            score=cv.score[goal.name], labels=labels)
    show(figure)

# ---------------------------------------------------------------------------
# Keep it
# ---------------------------------------------------------------------------

folder = workbench.project.root / "Proposals"
if st.button(f"Save these proposals to {display_path(folder)}",
             key="org_next_save"):
    csv, _ = optimize.save_proposal(plan, folder, settings={
        "campaign": spec.name, "same_protocol": used["same_protocol"]})
    st.success(f"Saved `{display_path(csv)}` and its settings.", icon="💾")
