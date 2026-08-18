"""Safe, local helpers for repairing moved original-image paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

SUPPORTED_SUFFIXES = {".jpg", ".jpeg"}


def normalised_path(value: str | Path) -> str:
    """Produce the same stable key for existing and currently missing paths."""
    return str(Path(value).resolve()).casefold()


@dataclass(frozen=True)
class RelinkSearch:
    """The only safe bulk candidates beneath a user-selected directory."""

    matches: dict[str, Path]
    ambiguous: tuple[str, ...]
    unresolved: tuple[str, ...]


def _image_size(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, ValueError):
        return None


def find_unique_matches(
    missing_paths: list[str], root: Path, expected_sizes: dict[str, tuple[int, int]],
) -> RelinkSearch:
    """Find only unambiguous same-name candidates with matching saved dimensions.

    The caller must still present the result and obtain user confirmation.  A filename
    alone never qualifies if a saved source size is available.
    """
    by_name: dict[str, list[Path]] = {}
    try:
        files = root.rglob("*")
        for candidate in files:
            if candidate.is_file() and candidate.suffix.casefold() in SUPPORTED_SUFFIXES:
                by_name.setdefault(candidate.name.casefold(), []).append(candidate)
    except OSError:
        # Existing candidates remain useful when an unreadable subfolder is met.
        pass

    matches: dict[str, Path] = {}
    ambiguous: list[str] = []
    unresolved: list[str] = []
    for old_path in missing_paths:
        candidates = by_name.get(Path(old_path).name.casefold(), [])
        expected = expected_sizes.get(normalised_path(old_path))
        if expected is not None:
            candidates = [candidate for candidate in candidates if _image_size(candidate) == expected]
        if len(candidates) == 1:
            matches[old_path] = candidates[0].resolve()
        elif candidates:
            ambiguous.append(old_path)
        else:
            unresolved.append(old_path)
    return RelinkSearch(matches, tuple(ambiguous), tuple(unresolved))
