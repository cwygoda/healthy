"""healthy: a CLI-driven Garmin activity downloader."""

from __future__ import annotations

from healthy.cli import app

__all__ = ["app", "main"]


def main() -> None:
    app()
