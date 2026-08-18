"""Local preferences store for machine-specific Years in Focus settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

RECENT_PROJECT_LIMIT = 5


def settings_path() -> Path:
    """Use the Windows per-user app-data directory, never the digiKam database."""
    base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return base / "YearsInFocus" / "settings.json"


def legacy_settings_path() -> Path:
    """Location used by releases before the Years in Focus naming migration."""
    base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return base / "FaceMovie" / "settings.json"


def load_settings() -> dict[str, Any]:
    for source in (settings_path(), legacy_settings_path()):
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return {}


def save_settings(settings: dict[str, Any]) -> None:
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def load_digikam_profile() -> dict[str, Any]:
    profile = load_settings().get("digikam")
    return profile if isinstance(profile, dict) else {}


def save_digikam_profile(profile: dict[str, Any]) -> None:
    settings = load_settings()
    settings["digikam"] = profile
    save_settings(settings)


def load_language() -> str:
    language = load_settings().get("language", "de")
    return language if language in {"de", "en"} else "de"


def save_language(language: str) -> None:
    settings = load_settings()
    settings["language"] = language if language in {"de", "en"} else "de"
    save_settings(settings)


def load_show_quick_guide() -> bool:
    """Whether the short guide should open automatically on application start."""
    return bool(load_settings().get("show_quick_guide", True))


def save_show_quick_guide(enabled: bool) -> None:
    settings = load_settings()
    settings["show_quick_guide"] = bool(enabled)
    save_settings(settings)


def load_recent_projects() -> list[str]:
    """Return the most recently used project files, newest first."""
    items = load_settings().get("recent_projects")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, str)][:RECENT_PROJECT_LIMIT]


def save_recent_project(path: Path) -> None:
    """Record a successfully opened or saved project without storing duplicates."""
    resolved = str(path.resolve())
    items = [item for item in load_recent_projects() if Path(item) != Path(resolved)]
    settings = load_settings()
    settings["recent_projects"] = [resolved, *items][:RECENT_PROJECT_LIMIT]
    save_settings(settings)
