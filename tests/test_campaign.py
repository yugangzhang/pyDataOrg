"""Campaign kernels on plain frames with known answers, and the adapter on
the generated Cu-Au library."""

import numpy as np
import pandas as pd
import pytest

from pyDataOrg import campaign as C


def frame():
    return pd.DataFrame({
        "sample": ["a", "b", "c", "d", "ref"],
        "x": [0.1, 0.3, 0.5, 0.7, np.nan],
        "y1": [1.0, 3.0, 2.0, 0.5, 2.5],
        "y2": [4.0, 1.0, 3.0, 5.0, 0.0],
        "proto": ["p", "p", "p", "q", "p"],
        "status": ["done", "done", "done", "done", "done"],
        "t": ["2026-01-03", "2026-01-01", "2026-01-02", None, "2026-01-04"],
    })


def test_pareto_mask_finds_the_non_dominated_rows():
    values = np.array([[1, 4], [3, 1], [2, 3], [0.5, 5], [1, 1]], float)
    assert C.pareto_mask(values, [True, True]).tolist() == \
        [True, True, True, True, False]
    # minimising the second turns the front round
    assert C.pareto_mask(values, [True, False]).tolist() == \
        [False, True, False, False, False]


def test_pareto_mask_never_puts_a_nan_on_the_front():
    values = np.array([[1, np.nan], [0, 0]], float)
    assert C.pareto_mask(values, [True, True]).tolist() == [False, True]


def test_pareto_mask_checks_its_shape():
    with pytest.raises(ValueError, match="values must be"):
        C.pareto_mask(np.ones((3, 2)), [True])


def test_rank_scores_and_flags_the_front():
    ranked = C.rank(frame(), [C.Objective("y1"), C.Objective("y2")],
                    inputs=["x"])
    assert "ref" not in set(ranked["sample"])          # no input: no rank
    assert ranked["score"].between(0, 1).all()
    assert ranked["score"].is_monotonic_decreasing
    assert set(ranked.loc[ranked["pareto"], "sample"]) == {"a", "b", "c", "d"}


def test_best_so_far_carries_the_running_best_over_gaps():
    assert C.best_so_far([1, np.nan, 3, 2, 5]).tolist() == [1, 1, 3, 3, 5]
    assert C.best_so_far([3, 1, 2], maximize=False).tolist() == [3, 1, 1]


def test_chronological_orders_by_time_and_drops_the_undated():
    assert list(C.chronological(frame(), "t")["sample"]) == ["b", "c", "a", "ref"]


def test_majority_and_comparable():
    f = frame()
    assert C.majority(f, ["proto"]) == {"proto": "p"}
    rows = C.comparable(f, ["y1"], inputs=["x"], protocol_columns=["proto"],
                        done=("status", "done"))
    assert list(f.loc[rows, "sample"]) == ["a", "b", "c"]
    everyone = C.comparable(f, ["y1"], inputs=["x"], protocol={},
                            protocol_columns=["proto"])
    assert list(f.loc[everyone, "sample"]) == ["a", "b", "c", "d"]


def test_campaign_frame_renames_and_keeps_one_shape():
    table = pd.DataFrame({"sample_id": ["S1", "S2"],
                          "synthesis.x": ["0.1", "0.2"],
                          "testing.rate": [1.0, 2.0]})
    columns = [C.Column("x", "synthesis.x", kind="input"),
               C.Column("rate", "testing.rate", kind="objective"),
               C.Column("size", "derived.size", kind="result")]
    out = C.campaign_frame(table, columns)
    assert list(out.columns) == ["sample", "x", "rate", "size"]
    assert out["x"].tolist() == [0.1, 0.2]               # made numeric
    assert out["size"].isna().all()                      # not run yet: NaN


def test_campaign_spec_validates_and_describes_itself():
    with pytest.raises(ValueError, match="not columns"):
        C.Campaign("bad", [C.Column("x", "a.x", kind="input")],
                   [C.Objective("y")])
    with pytest.raises(ValueError, match="duplicate"):
        C.Campaign("bad", [C.Column("x", "a"), C.Column("x", "b")])
    with pytest.raises(ValueError, match="kind"):
        C.Column("x", "a", kind="recipe")
    spec = C.Campaign("ok", [C.Column("x", "a.x", "fraction", kind="input"),
                             C.Column("y", "a.y", "yield", "%", "objective")],
                      [C.Objective("y", maximize=False)], bounds={"x": (0, 1)})
    assert spec.inputs == ["x"]
    assert spec.labels == {"x": "fraction", "y": "yield (%)"}
    assert spec.objective("y").maximize is False
    assert spec.objective("other").maximize is True
    assert spec.to_dict()["bounds"] == {"x": [0, 1]}


def test_from_columns_builds_a_campaign_with_bounds_from_the_data():
    table = pd.DataFrame({"sample_id": ["a", "b"], "s.x": [0.2, 0.6],
                          "t.y": [1.0, 2.0]})
    spec = C.from_columns(table, ["s.x"], [C.Objective("t.y")])
    assert spec.inputs == ["s.x"] and spec.bounds == {"s.x": (0.2, 0.6)}
    assert list(spec.frame(table)["t.y"]) == [1.0, 2.0]


def test_the_demo_campaign_is_built_in():
    assert "CuAu-CO2RR" in C.list_campaigns()
    spec = C.get_campaign("CuAu-CO2RR")
    assert spec.inputs == ["x_Au"]
    with pytest.raises(KeyError, match="no campaign"):
        C.get_campaign("nope")


@pytest.fixture(scope="module")
def cuau(tmp_path_factory):
    from pyDataOrg import Organizer
    from pyDataOrg.demo import build_showcase_project

    root = build_showcase_project(tmp_path_factory.mktemp("c") / "CuAu",
                                  with_images=False, with_tomography=False)
    org = Organizer(root / "cuau.json")
    for stage in ("Synthesis", "Characterization", "Testing", "Computation"):
        org.ingest(f"MetaData/{stage}_dict.py")
    return org


def test_the_demo_campaign_table_recovers_the_volcano(cuau):
    from pyDataOrg.demo import showcase_truth

    spec = C.get_campaign("CuAu-CO2RR")
    table = spec.table(cuau)
    assert len(table) == 9                       # eight alloys + a failed run
    usable = table[C.usable(table, ["x_Au", "j_CO"])]
    assert len(usable) == 8
    best = usable.loc[usable["j_CO"].idxmax(), "x_Au"]
    truth = showcase_truth()
    assert best == pytest.approx(
        truth.loc[truth["true_j_CO_mA_cm2"].idxmax(), "x_Au"], abs=0.01)
