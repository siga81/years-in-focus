"""Kompakter Kontaktbogen für die manuelle Sichtprüfung."""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from facemovie.models import ImageAnalysis


def _contact_sheet_items(items: list[ImageAnalysis], maximum: int) -> list[ImageAnalysis]:
    """Return a chronological, representative subset for a compact overview."""
    if len(items) <= maximum:
        return items
    # Keep the first and last image and spread the remaining samples evenly
    # through the import.  A contact sheet is only a visual aid; the project
    # itself always retains every card.
    return [items[round(index * (len(items) - 1) / (maximum - 1))] for index in range(maximum)]


def write_contact_sheet(
    items: list[ImageAnalysis],
    output_path: Path,
    *,
    maximum_items: int = 200,
    progress: Callable[[int, int], None] | None = None,
) -> None:
    """Write a compact overview without creating impractically tall JPEGs."""
    selected_items = _contact_sheet_items(items, maximum_items)
    thumb_size = (320, 180)
    label_height = 44
    columns = 4
    rows = max(1, math.ceil(len(selected_items) / columns))
    sheet = Image.new("RGB", (columns * thumb_size[0], rows * (thumb_size[1] + label_height)), "#202124")
    draw = ImageDraw.Draw(sheet)

    total = len(selected_items)
    for index, item in enumerate(selected_items, start=1):
        slot = index - 1
        x = (slot % columns) * thumb_size[0]
        y = (slot // columns) * (thumb_size[1] + label_height)
        source = Path(item.output_path or item.path)
        try:
            with Image.open(source) as image:
                thumb = ImageOps.fit(image.convert("RGB"), thumb_size, method=Image.Resampling.LANCZOS)
        except OSError:
            thumb = Image.new("RGB", thumb_size, "#5f2120")
        sheet.paste(thumb, (x, y))
        color = {
            "accepted": "#66bb6a",
            "review": "#ffb74d",
            "deferred": "#64b5f6",
            "excluded": "#ef5350",
        }.get(item.status, "#ef5350")
        label = f"{item.filename[:36]}\n{item.status}"
        draw.text((x + 6, y + thumb_size[1] + 5), label, fill=color)
        if progress is not None:
            progress(index, total)
    sheet.save(output_path, quality=92)
