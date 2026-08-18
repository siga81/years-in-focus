"""Read-only preflight for importing an XMP-tagged image folder."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from facemovie.metadata.xmp import person_names

SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg"}


@dataclass(frozen=True)
class ImportScan:
    folder: Path
    image_files: tuple[Path, ...]
    person_counts: dict[str, int]
    untagged_files: tuple[Path, ...]

    @property
    def tagged_count(self) -> int:
        return len(self.image_files) - len(self.untagged_files)


def scan_import_paths(
    paths: tuple[Path, ...], *, progress: Callable[[int, int], None] | None = None,
) -> ImportScan:
    """Inspect explicitly selected JPG/JPEG paths and aggregate XMP person tags."""
    image_files = tuple(sorted(
        (path.resolve() for path in paths if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES),
        key=lambda path: path.name.casefold(),
    ))
    if not image_files:
        raise ValueError("Keine unterstützten JPG/JPEG-Dateien ausgewählt.")
    counts: Counter[str] = Counter()
    untagged: list[Path] = []
    total = len(image_files)
    for current, path in enumerate(image_files, start=1):
        names = person_names(path)
        if not names:
            untagged.append(path)
        else:
            counts.update(names)
        if progress is not None:
            progress(current, total)
    return ImportScan(image_files[0].parent, image_files, dict(counts), tuple(untagged))


def scan_import_folder(folder: Path) -> ImportScan:
    """Inspect direct JPG/JPEG children and aggregate existing XMP person tags."""
    return scan_import_paths(tuple(folder.iterdir()))


def paths_from_input_list(path: Path) -> list[Path]:
    """Read a persisted input list to avoid Windows command-line length limits."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("images", payload) if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError("Die Eingabeliste muss ein JSON-Array mit Bildpfaden enthalten.")
    paths = [Path(str(value)).resolve() for value in values]
    if not paths:
        raise ValueError("Die Eingabeliste enthält keine Bilder.")
    return paths
