"""Helpers that convert free-form text into unit conversion results."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from typing import Final

from ph_units.converter import UnitTypeNameNotFound, convert
from ph_units.parser import parse_input

_CONNECTOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(?:to|as)\b", re.IGNORECASE)
_FORMAT_SPEC: Final[str] = ",.12g"


def render_results(lines: Iterable[str]) -> Sequence[str]:
    """Convert each provided line and return printable results."""

    outputs: list[str] = []
    for line in lines:
        expression = line.strip()
        if not expression:
            outputs.append("")
            continue

        try:
            value = _convert_expression(expression)
        except (ValueError, UnitTypeNameNotFound):
            outputs.append("")
            continue
        except Exception:
            # Defensive: PH_units can raise generic exceptions for bad inputs.
            outputs.append("")
            continue

        outputs.append(_format_value(value))
    return outputs


def _convert_expression(expression: str) -> float:
    """Parse a single conversion request and return the converted value."""

    parts = _CONNECTOR_PATTERN.split(expression, maxsplit=1)
    if len(parts) != 2:
        raise ValueError("Conversion target not provided")

    source_text, target_text = parts
    source_text = source_text.strip()
    target_text = target_text.strip()
    if not source_text or not target_text:
        raise ValueError("Incomplete conversion expression")

    value_text, source_unit = parse_input(source_text)
    if not value_text or source_unit is None:
        raise ValueError("Missing value or source unit")

    source_unit = source_unit.rstrip(".,;")
    target_text = target_text.rstrip(".,;")
    if not source_unit:
        raise ValueError("Missing value or source unit")
    if not target_text:
        raise ValueError("Conversion target not provided")

    try:
        numeric_value = float(value_text)
    except ValueError as exc:
        raise ValueError("Invalid numeric value") from exc

    result = convert(numeric_value, source_unit, target_text)
    if result is None:
        raise ValueError("Conversion yielded no result")

    return float(result)


def _format_value(value: float) -> str:
    """Format numeric results for display without appending unit labels."""

    if math.isnan(value) or math.isinf(value):
        return str(value)

    formatted = format(value, _FORMAT_SPEC)
    if formatted.endswith("."):
        return formatted[:-1]
    return formatted


__all__ = ["render_results"]
