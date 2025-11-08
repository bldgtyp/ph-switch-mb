"""Console entry point for the toolbar application."""

from __future__ import annotations

from .app import ToolbarApp


def main() -> None:
    """Launch the toolbar application."""

    ToolbarApp().run()


if __name__ == "__main__":
    main()
