"""Shared command line defaults and console."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from healthy.adapters.storage import StorageCompression

console = Console()

DEFAULT_TOKENSTORE = Path("~/.garminconnect")
DEFAULT_ACTIVITY_DIR = Path("~/Documents/Activities")
DEFAULT_STORAGE_COMPRESSION = StorageCompression.XZ
DEFAULT_AUTORUN_STATE = Path("~/Library/Application Support/healthy/autorun-state.json")
DEFAULT_AUTORUN_LOG = Path("~/Library/Logs/healthy/autorun.log")
