import pytest

from ph_switch_mb.app import update_results
from ph_switch_mb.calculator import render_results


def _as_float(text: str) -> float:
    return float(text.replace(",", ""))


def test_render_results_converts_units() -> None:
    outputs = render_results(["5 m to ft"])
    assert len(outputs) == 1
    assert _as_float(outputs[0]) == pytest.approx(16.4041995, rel=1e-6)


def test_render_results_accepts_as_connector() -> None:
    outputs = render_results(["12 inches as mm"])
    assert len(outputs) == 1
    assert _as_float(outputs[0]) == pytest.approx(304.8, rel=1e-6)


def test_render_results_suppresses_errors() -> None:
    assert render_results(["bad input"]) == [""]


def test_update_results_preserves_line_structure() -> None:
    text = "5 m to ft\n\ninvalid\n12 in to mm"
    outputs = update_results(text)
    assert len(outputs) == 4
    assert _as_float(outputs[0]) == pytest.approx(16.4041995, rel=1e-6)
    assert outputs[1] == ""
    assert outputs[2] == ""
    assert _as_float(outputs[3]) == pytest.approx(304.8, rel=1e-6)
