# LLM Agent Context

This repository follows a modern Python "src" layout and relies on the following tooling:

- Environment: managed with [`uv`](https://github.com/astral-sh/uv). Always install dependencies and run python modules via `uv` (e.g., `uv run`, `uv pip install`).
- Tests: executed with `pytest` (`uv run pytest`).
- Static analysis: `mypy` for type checking (`uv run mypy`).
- Linting: `ruff` (`uv run ruff check`).
- Formatting: `black` (`uv run black`) and import sorting with `isort` (`uv run isort`).
- Source layout: production code in `src/ph_switch_mb/`; tests in `tests/`.

LLM agents should respect these conventions, keep code style tools aligned, and prefer ASCII in new files unless the existing file uses non-ASCII characters.
