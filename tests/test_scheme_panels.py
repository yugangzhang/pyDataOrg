"""The protocol scheme, the panel layout and the clickable points: what a
page relies on and cannot see in a test — every drawing renders, the
height follows the captions, a click is read once."""

import numpy as np
import pytest

from pyDataOrg.web_app.components.scheme import ICONS, scheme_height, scheme_html


def test_every_drawing_renders_with_its_title_and_lines():
    steps = [{"icon": name, "title": f"step {name}", "lines": [f"{name} line"],
              "labels": ["A", "B"], "colours": ["#e8c547", "#b23a48"]}
             for name in ICONS]
    page = scheme_html(steps, to=["Characterization: TEM", ("Performance", "#0072B2")],
                       footer="who · when")
    for name in ICONS:
        assert f"step {name}" in page and f"{name} line" in page
    assert "→ Characterization: TEM" in page and "who · when" in page
    assert "None" not in page and "nan" not in page


def test_an_unknown_drawing_leaves_the_card():
    page = scheme_html([{"icon": "nothing", "title": "Alone"}])
    assert "Alone" in page


def test_long_captions_make_the_cards_taller():
    short = [{"icon": "stocks", "title": "a", "lines": ["one"]}]
    long = [{"icon": "stocks", "title": "a", "lines": ["one", "two", "three",
                                                      "four and a much longer line"]}]
    assert scheme_height(long) > scheme_height(short)
    assert scheme_height(short, to=["x"]) > scheme_height(short)


def test_a_point_carries_its_id_and_no_value_is_open():
    pytest.importorskip("plotly")
    from pyDataOrg.viz.interactive import points_figure

    fig = points_figure([1, 2, 3], [4, 5, 6], ["S1", "S2", "S3"],
                        values=[0.5, np.nan, 0.9], value_label="conversion",
                        hover={"batch": ["a", "b", "c"]}, selected="S3")
    ids = [c[0] for trace in fig.data for c in trace.customdata]
    assert sorted(set(ids)) == ["S1", "S2", "S3"]
    open_trace = next(t for t in fig.data if t.marker.color == "white")
    assert [c[0] for c in open_trace.customdata] == ["S2"]
    ring = fig.data[-1]
    assert [c[0] for c in ring.customdata] == ["S3"] and ring.marker.size > 11


def _layout_page():
    import streamlit as st

    from pyDataOrg.web_app.components.panels import panel_grid, panel_layout

    chosen, per_row = panel_layout({"a": "A", "b": "B", "c": "C"}, "p",
                                   default=["b", "c"])
    st.session_state["chosen"] = chosen
    st.session_state["boxes"] = len(panel_grid(len(chosen), per_row))


def test_the_panels_start_as_asked_and_follow_the_reader():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_layout_page)
    at.run()
    assert not at.exception
    assert at.session_state["chosen"] == ["b", "c"]
    assert at.selectbox(key="p_1").format_func("c") == "C"
    at.number_input(key="p_n").set_value(3).run()
    assert at.session_state["chosen"] == ["b", "c", "c"]
    assert at.session_state["boxes"] == 3
    at.selectbox(key="p_2").set_value("a").run()
    assert at.session_state["chosen"] == ["b", "c", "a"]


def _click_page():
    import streamlit as st

    from pyDataOrg.web_app.components.controls import clicked

    st.session_state["got"] = clicked("plot")


def test_a_click_is_read_once():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_click_page)
    at.session_state["plot"] = {"selection": {"points": [{"customdata": ["S2", "x"]}]}}
    at.run()
    assert at.session_state["got"] == "S2"
    at.run()
    assert at.session_state["got"] is None             # the same selection, again
