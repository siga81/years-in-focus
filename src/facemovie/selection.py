"""Zeitbasierte, bewusst einfache Auswahl von Serienbildern."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from facemovie.models import ImageAnalysis

_EXIF_IFD = 34665  # ExifOffset: nested camera metadata
_EXIF_CAPTURE_TIME = 36867  # DateTimeOriginal
_EXIF_DIGITIZED_TIME = 36868  # DateTimeDigitized


def parse_capture_time(value: str | None) -> datetime | None:
    """Accept analysis timestamps written by YiF and older localized projects."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    for pattern in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return None


def capture_time_with_source(path: Path) -> tuple[datetime | None, str | None]:
    """Read capture/digitization time; generic DateTime is not an acquisition date."""
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            try:
                camera_exif = exif.get_ifd(_EXIF_IFD)
            except (AttributeError, KeyError, TypeError, ValueError):
                camera_exif = {}
            values = (
                (camera_exif.get(_EXIF_CAPTURE_TIME), "DateTimeOriginal"),
                (exif.get(_EXIF_CAPTURE_TIME), "DateTimeOriginal"),
                (camera_exif.get(_EXIF_DIGITIZED_TIME), "DateTimeDigitized"),
                (exif.get(_EXIF_DIGITIZED_TIME), "DateTimeDigitized"),
            )
    except (OSError, ValueError):
        return None, None
    for value, source in values:
        if not isinstance(value, str):
            continue
        try:
            return datetime.strptime(value, "%Y:%m:%d %H:%M:%S"), source
        except ValueError:
            continue
    return None, None


def capture_time(path: Path) -> datetime | None:
    """Compatibility helper for callers needing only the timestamp."""
    return capture_time_with_source(path)[0]


def _quality_key(item: ImageAnalysis) -> tuple[float, float, float, str]:
    """Höhere Landmarkensicherheit und Gesichtsgröße gewinnen innerhalb einer Serie."""
    return (
        float(item.metrics.get("yunet_score", 0.0)),
        float(item.metrics.get("face_height_ratio", 0.0)),
        -abs(float(item.metrics.get("pose_yaw_degrees", 0.0))),
        # Bei ansonsten gleichem Ergebnis ist die alphabetische Wahl reproduzierbar.
        "".join(chr(0x10FFFF - ord(char)) for char in item.filename),
    )


def reduce_series(items: list[ImageAnalysis], minimum_gap_minutes: float, keep: int = 1) -> None:
    """Stellt überzählige, zeitlich nahe akzeptierte Bilder als ``deferred`` zurück.

    Bilder ohne EXIF-Aufnahmezeit und alle Review-/Ausschlussfälle bleiben unverändert.
    Die Funktion verändert keine Original- oder gerenderten Bilddateien.
    """
    if minimum_gap_minutes <= 0:
        return
    candidates = [item for item in items if item.status == "accepted" and item.capture_time]
    candidates.sort(key=lambda item: parse_capture_time(item.capture_time) or datetime.max)
    groups: list[list[ImageAnalysis]] = []
    maximum_gap_seconds = minimum_gap_minutes * 60
    for item in candidates:
        if not groups:
            groups.append([item])
            continue
        previous = groups[-1][-1]
        previous_time = parse_capture_time(previous.capture_time)
        current_time = parse_capture_time(item.capture_time)
        if previous_time is None or current_time is None:
            continue
        if (current_time - previous_time).total_seconds() <= maximum_gap_seconds:
            groups[-1].append(item)
        else:
            groups.append([item])

    for cluster_index, group in enumerate(groups, start=1):
        pinned = [item for item in group if item.manual_decision == "accept"]
        if len(group) <= keep:
            continue
        automatic = [item for item in group if item.manual_decision != "accept"]
        additional = max(0, keep - len(pinned))
        selected = {id(item) for item in pinned}
        selected.update(id(item) for item in sorted(automatic, key=_quality_key, reverse=True)[:additional])
        for rank, item in enumerate(sorted(group, key=_quality_key, reverse=True), start=1):
            item.metrics["series_cluster"] = float(cluster_index)
            item.metrics["series_rank"] = float(rank)
            if id(item) not in selected:
                item.status = "deferred"
                item.warnings.append(
                    f"Zeitlich nahe Serienaufnahme; Auswahl auf {keep} Bild(er) pro "
                    f"{minimum_gap_minutes:g}-Minuten-Cluster begrenzt."
                )
