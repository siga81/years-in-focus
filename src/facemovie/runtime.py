"""Locate files shipped beside a frozen Years in Focus application."""

from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundled_asset_root() -> Path:
    """Return the directory containing application data files.

    PyInstaller's onedir layout places collected data below ``_internal``;
    during normal source execution the repository itself is the asset root.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", application_root()))
    return application_root()


def bundled_cli_path() -> Path:
    preferred = application_root() / "YearsInFocusCLI.exe"
    # Old portable 0.1.3 builds used this helper name. Keeping the fallback
    # costs nothing and makes mixed development folders harmless.
    return preferred if preferred.is_file() or not getattr(sys, "frozen", False) else application_root() / "FaceMovieCLI.exe"
