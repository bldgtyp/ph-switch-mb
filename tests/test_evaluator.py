import pytest

from ph_switch_mb.calculator import render_results


def _as_float(text: str) -> float:
    return float(text.replace(",", ""))


def test_render_results_requires_target_unit() -> None:
    assert render_results(["10 kwh"]) == [""]


def test_render_results_requires_source_unit() -> None:
    assert render_results(["10 to ft"]) == [""]


def test_render_results_rejects_unknown_units() -> None:
    assert render_results(["10 apples to oranges"]) == [""]


def test_render_results_strips_trailing_punctuation() -> None:
    output = render_results(["12 inches to mm."])
    assert _as_float(output[0]) == pytest.approx(304.8, rel=1e-6)
