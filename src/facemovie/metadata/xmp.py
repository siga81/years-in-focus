"""Lesender Zugriff auf eingebettete XMP-Gesichtsregionen."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from facemovie.models import FaceRegion

XMP_BLOCK = re.compile(r"<x:xmpmeta\b[\s\S]*?</x:xmpmeta>")
MP_NAME = "{http://ns.microsoft.com/photo/1.2/t/Region#}PersonDisplayName"
MP_RECTANGLE = "{http://ns.microsoft.com/photo/1.2/t/Region#}Rectangle"
MWG_NAME = "{http://www.metadataworkinggroup.com/schemas/regions/}Name"
MWG_AREA = "{http://www.metadataworkinggroup.com/schemas/regions/}Area"
AREA_X = "{http://ns.adobe.com/xmp/sType/Area#}x"
AREA_Y = "{http://ns.adobe.com/xmp/sType/Area#}y"
AREA_W = "{http://ns.adobe.com/xmp/sType/Area#}w"
AREA_H = "{http://ns.adobe.com/xmp/sType/Area#}h"


def _matching_name(value: str, requested: str) -> bool:
    return value.casefold().strip() == requested.casefold().strip()


def _parse_rectangle(value: str) -> tuple[float, float, float, float]:
    values = [float(item.strip()) for item in value.split(",")]
    if len(values) != 4:
        raise ValueError(f"Ungültiges Microsoft-Photo-Rechteck: {value!r}")
    return tuple(values)  # type: ignore[return-value]


def regions_from_xmp_text(text: str, person_name: str) -> list[FaceRegion]:
    """Find marked regions for a person in Microsoft Photo and MWG XMP text.

    Microsoft Photo rectangles are interpreted as normalized left/top/width/height.
    MWG areas use normalized centre/centre/width/height and are converted to left/top.
    """

    regions: list[FaceRegion] = []
    for block in XMP_BLOCK.findall(text):
        try:
            root = ET.fromstring(block)
        except ET.ParseError:
            continue

        for element in root.iter():
            name = element.find(MP_NAME)
            rectangle = element.find(MP_RECTANGLE)
            if name is not None and rectangle is not None and name.text:
                if _matching_name(name.text, person_name) and rectangle.text:
                    x, y, width, height = _parse_rectangle(rectangle.text)
                    regions.append(
                        FaceRegion(
                            person_name, x, y, width, height,
                            "normalized_left_top", "microsoft_photo",
                        )
                    )

            # digiKam writes the MWG name as a child element.  Some other tools
            # store it as an attribute, therefore both forms are supported.
            mwg_name = element.attrib.get(MWG_NAME) or element.findtext(MWG_NAME)
            area = element.find(MWG_AREA)
            if mwg_name and area is not None and _matching_name(mwg_name, person_name):
                try:
                    cx, cy = float(area.attrib[AREA_X]), float(area.attrib[AREA_Y])
                    width, height = float(area.attrib[AREA_W]), float(area.attrib[AREA_H])
                except (KeyError, ValueError):
                    continue
                regions.append(
                    FaceRegion(
                        person_name, cx - width / 2, cy - height / 2, width, height,
                        "normalized_center", "mwg",
                    )
                )
    return regions


def person_names_from_xmp_text(text: str) -> list[str]:
    """Return all distinct person names contained in supported XMP region formats."""
    names: list[str] = []
    seen: set[str] = set()
    for block in XMP_BLOCK.findall(text):
        try:
            root = ET.fromstring(block)
        except ET.ParseError:
            continue
        for element in root.iter():
            candidates = [
                element.text if element.tag in {MP_NAME, MWG_NAME} else None,
                element.attrib.get(MWG_NAME),
            ]
            for candidate in candidates:
                if candidate and candidate.strip() and candidate.casefold() not in seen:
                    names.append(candidate.strip())
                    seen.add(candidate.casefold())
    return names


def person_names(path: Path) -> list[str]:
    """Read distinct XMP person names from an image without modifying it."""
    return person_names_from_xmp_text(path.read_bytes().decode("utf-8", errors="replace"))


def find_regions(path: Path, person_name: str) -> list[FaceRegion]:
    """Find marked regions in an image without changing the source file."""
    text = path.read_bytes().decode("utf-8", errors="replace")
    return regions_from_xmp_text(text, person_name)


def find_region(path: Path, person_name: str) -> FaceRegion | None:
    regions = find_regions(path, person_name)
    if not regions:
        return None
    # Multiple entries for the same person are unusual. Prefer the largest instead
    # of silently selecting an arbitrary XML block.
    return max(regions, key=lambda region: region.width * region.height)
