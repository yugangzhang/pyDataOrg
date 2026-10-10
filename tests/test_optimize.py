"""The optimiser on synthetic campaigns with a known best input."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")

from pyDataOrg import optimize  # noqa: E402
from pyDataOrg.campaign import Campaign, Column, Objective  # noqa: E402


def peak_campaign(n=9, noise=0.01, seed=0):
    """Goal a peaks at x = 0.45; goal b prefers low x."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.05, 0.95, n)
    return pd.DataFrame({
        "sample": [f"S{i}" for i in range(n)], "x": x,
        "a": np.exp(-((x - 0.45) / 0.15) ** 2) + rng.normal(0, noise, n),
        "b": 1 - x + rng.normal(0, noise, n)})


def test_one_goal_proposes_near_the_known_peak():
    plan = optimize.propose(peak_campaign(), variables=["x"],
                            objectives=[Objective("a")], bounds={"x": (0, 1)},
                            n=1, rounding={"x": 0.01})
    assert plan.suggestions["x"].iloc[0] == pytest.approx(0.45, abs=0.08)
    assert plan.samples == [f"S{i}" for i in range(9)]


def test_a_batch_is_spread_out_rounded_and_inside_the_bounds():
    plan = optimize.propose(peak_campaign(),
                            variables=["x"],
                            objectives=[Objective("a"), Objective("b")],
                            bounds={"x": (0.0, 1.0)}, n=4,
                            rounding={"x": 0.05})
    x = plan.suggestions["x"].to_numpy()
    assert ((x >= 0) & (x <= 1)).all()
    assert np.allclose(x / 0.05, np.round(x / 0.05))
    assert len(set(np.round(x, 3))) >= 3
    for name in ("a_pred", "a_sd", "b_pred", "b_sd"):
        assert name in plan.suggestions


def test_the_surrogate_predicts_in_the_objectives_units():
    plan = optimize.propose(peak_campaign(noise=0.0), variables=["x"],
                            objectives=[Objective("a")], bounds={"x": (0, 1)})
    mean, sd = plan.predict([[0.45], [0.95]])
    assert mean[0, 0] == pytest.approx(1.0, abs=0.1)
    assert mean[1, 0] < 0.2 and (sd >= 0).all()
    gx, gy, m, s = plan.surface(21)
    assert gy is None and gx.shape == (21,) and m.shape == (21, 1)


def test_a_log_objective_is_modelled_in_log10_and_returned_in_units():
    y = np.array([[1e-3], [1e-2], [1e-1]])
    model = optimize.to_model(y, [Objective("k", log=True)])
    assert model[:, 0].tolist() == pytest.approx([-3, -2, -1])
    mean, sd = optimize.from_model(model, np.full_like(model, 0.1),
                                   [Objective("k", log=True)])
    assert mean[:, 0] == pytest.approx(y[:, 0])
    assert sd[0, 0] == pytest.approx(1e-3 * np.log(10) * 0.1)


def test_two_variables_give_a_grid():
    rng = np.random.default_rng(1)
    x1, x2 = rng.random(12), rng.random(12)
    frame = pd.DataFrame({"sample": range(12), "x1": x1, "x2": x2,
                          "y": -(x1 - 0.3) ** 2 - (x2 - 0.7) ** 2})
    plan = optimize.propose(frame, variables=["x1", "x2"],
                            objectives=[Objective("y")],
                            bounds={"x1": (0, 1), "x2": (0, 1)}, n=1)
    gx, gy, mean, sd = plan.surface(10)
    assert gx.shape == gy.shape == (10, 10) and mean.shape == (100, 1)
    assert plan.suggestions[["x1", "x2"]].iloc[0].tolist() == \
        pytest.approx([0.3, 0.7], abs=0.2)


def test_too_few_samples_and_missing_bounds_are_refused():
    with pytest.raises(ValueError, match="at least 3"):
        optimize.propose(peak_campaign().head(2), variables=["x"],
                         objectives=[Objective("a")], bounds={"x": (0, 1)})
    with pytest.raises(ValueError, match="no bounds"):
        optimize.propose(peak_campaign(), variables=["x"],
                         objectives=[Objective("a")], bounds={})


def test_cross_validation_says_which_goal_is_learned():
    frame = peak_campaign(n=10)
    frame["noise"] = np.random.default_rng(3).normal(size=10)
    cv = optimize.cross_validate(frame, variables=["x"],
                                 objectives=[Objective("b"),
                                             Objective("noise")],
                                 bounds={"x": (0, 1)})
    assert cv.score["b"] < 0.5
    assert cv.score["noise"] > 0.8
    assert cv.verdict("b") == "predictive"
    assert "noise" in cv.summary()


def test_a_registered_engine_is_used_by_name():
    class Middle(optimize.Engine):
        def fit(self, X, Y, bounds, maximize, seed=0):
            self.bounds = bounds
            return self

        def predict(self, X):
            return np.zeros((len(X), 1)), np.ones((len(X), 1))

        def suggest(self, n, seed=0):
            return np.array([[np.mean(b) for b in self.bounds]] * n)

    optimize.register_engine("middle", Middle)
    try:
        plan = optimize.propose(peak_campaign(), variables=["x"],
                                objectives=[Objective("a")],
                                bounds={"x": (0.2, 0.4)}, n=2,
                                engine="middle")
        assert plan.suggestions["x"].tolist() == pytest.approx([0.3, 0.3])
        assert plan.engine_name == "middle"
        assert any("coincide" in note for note in plan.notes)
    finally:
        optimize.ENGINES.pop("middle")


def test_propose_for_uses_the_campaigns_inputs_bounds_and_rows():
    frame = peak_campaign()
    frame["status"] = ["done"] * 8 + ["running"]
    spec = Campaign("p", [Column("x", "x", kind="input"),
                          Column("a", "a", kind="objective"),
                          Column("status", "status")],
                    [Objective("a")], done=("status", "done"),
                    bounds={"x": (0, 1)}, rounding={"x": 0.1})
    plan = optimize.propose_for(spec, frame, n=1)
    assert len(plan.samples) == 8
    assert plan.suggestions["x"].iloc[0] == pytest.approx(0.4, abs=0.11)


def test_save_proposal_records_its_evidence(tmp_path):
    import json

    plan = optimize.propose(peak_campaign(), variables=["x"],
                            objectives=[Objective("a")], bounds={"x": (0, 1)},
                            n=2)
    csv, meta = optimize.save_proposal(plan, tmp_path, stamp="T",
                                       settings={"note": "test"})
    assert pd.read_csv(csv).shape[0] == 2
    record = json.loads(meta.read_text())
    assert record["trained_on"] == plan.samples and record["note"] == "test"
    assert record["engine"] == "gp"
