"""The Campaign and Next-experiments pages, and a plugin mounted as the app,
driven through ``AppTest`` on the generated Cu-Au library."""

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

from pathlib import Path  # noqa: E402

from pyDataOrg import Organizer, plugins  # noqa: E402

VIEWS = Path(__file__).resolve().parents[1] / "pyDataOrg" / "web_app" / "views"
HOME = VIEWS.parent / "Home.py"


@pytest.fixture(scope="module")
def cuau(tmp_path_factory):
    from pyDataOrg.demo import build_showcase_project

    root = build_showcase_project(tmp_path_factory.mktemp("w") / "CuAu",
                                  with_images=False, with_tomography=False)
    org = Organizer(root / "cuau.json")
    for stage in ("Synthesis", "Characterization", "Testing", "Computation"):
        org.ingest(f"MetaData/{stage}_dict.py")
    return org


def page(name, workbench, **state):
    app = AppTest.from_file(str(VIEWS / name), default_timeout=300)
    app.session_state["org_workbench"] = workbench
    for key, value in state.items():
        app.session_state[key] = value
    return app


def clean(app):
    assert not app.exception, app.exception[0].value if app.exception else ""
    assert not app.error, [e.value for e in app.error]


@pytest.mark.parametrize("name", ["campaign.py", "next.py"])
def test_campaign_pages_without_a_project_point_to_project(name):
    app = AppTest.from_file(str(VIEWS / name), default_timeout=120)
    app.run()
    assert not app.exception
    assert any("Project" in item.value for item in app.info)


def test_campaign_page_draws_every_tab(cuau):
    app = page("campaign.py", cuau)
    app.run()
    clean(app)
    assert app.sidebar.selectbox[0].value == "CuAu-CO2RR"
    assert any("9 samples" in c.value or "of 9 samples" in c.value
               for c in app.caption)
    ranking = app.dataframe[0].value
    assert {"sample", "x_Au", "score", "pareto"} <= set(ranking.columns)
    assert ranking["pareto"].any()


def test_campaign_page_builds_a_campaign_from_columns(cuau):
    app = page("campaign.py", cuau,
               org_campaign_name="➕ build from columns",
               org_campaign_inputs=["synthesis.composition.nominal_x_Au"],
               org_campaign_goals=["testing.performance.j_CO_mA_cm2",
                                   "testing.performance.FE_CO_pct"])
    app.run()
    clean(app)
    assert len(app.dataframe) >= 1


def test_next_page_proposes_and_checks_itself(cuau):
    pytest.importorskip("sklearn")
    app = page("next.py", cuau)
    app.run()
    clean(app)
    app.button(key="org_next_go").click().run()
    clean(app)
    proposals = app.dataframe[0].value
    assert len(proposals) == 4 and "x_Au" in proposals
    assert proposals["x_Au"].between(0, 1).all()
    app.button(key="org_next_cv").click().run()
    clean(app)
    assert any("LOO error" in block.value for block in app.code)


def test_a_plugin_runs_as_the_app(tmp_path, monkeypatch, cuau):
    view = tmp_path / "welcome.py"
    view.write_text("import streamlit as st\nst.title('Plugin home')\n")
    monkeypatch.setattr(plugins, "PLUGINS", {})
    monkeypatch.setattr(plugins, "_LOADED", True)
    seen = []
    plugins.register_plugin(plugins.Plugin(
        "testproj", title="Test project", icon="⚗️",
        pages=[plugins.Page(view, "Welcome", "⚗️", default=True)],
        on_page=lambda: seen.append(1)))
    monkeypatch.setenv("PYDATAORG_APP", "testproj")
    app = AppTest.from_file(str(HOME), default_timeout=300)
    app.run()
    clean(app)
    assert [t.value for t in app.title] == ["Plugin home"]
    assert seen


def test_the_general_app_still_opens_on_its_overview(monkeypatch):
    monkeypatch.setattr(plugins, "PLUGINS", {})
    monkeypatch.setattr(plugins, "_LOADED", True)
    monkeypatch.delenv("PYDATAORG_APP", raising=False)
    app = AppTest.from_file(str(HOME), default_timeout=300)
    app.run()
    clean(app)
    assert [t.value for t in app.title] == ["🔬 pyDataOrg"]
